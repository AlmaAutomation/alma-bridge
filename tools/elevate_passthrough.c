/*
 * elevate_passthrough.c
 *
 * Drop-in replacement for electron-builder's elevate.exe, for use under Wine.
 *
 * The real elevate.exe launches its target via ShellExecuteEx with the "runas"
 * (UAC) verb. Wine has no real UAC, and the runas-spawned child dies instantly,
 * so apps like Ascension Launcher hang forever waiting for their elevated
 * helper (AscensionClientServices.exe) to connect.
 *
 * Wine already runs every process with administrator rights, so elevation is
 * unnecessary. This passthrough just launches the target directly with
 * CreateProcess, preserving the child so it survives and connects back.
 *
 * elevate.exe usage it mimics:  elevate [-?|-wait|-k] prog [args...]
 *   -wait  : wait for prog to exit, then return its exit code
 *   -k     : (ignored) original runs prog inside %COMSPEC%
 *   -?     : print usage
 *
 * Build (on Linux) -- note -municode, required because we use wmain():
 *   x86_64-w64-mingw32-gcc -municode -O2 -s -o elevate.exe elevate_passthrough.c
 * or 32-bit to match the original:
 *   i686-w64-mingw32-gcc   -municode -O2 -s -o elevate.exe elevate_passthrough.c
 */

#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

static void quote_arg(const wchar_t *arg, wchar_t *out, size_t cap)
{
    /* Wrap in quotes if the arg contains whitespace and is not already quoted. */
    if (arg[0] != L'"' && (wcschr(arg, L' ') || wcschr(arg, L'\t')))
        _snwprintf(out, cap, L"\"%s\"", arg);
    else
        _snwprintf(out, cap, L"%s", arg);
}

int wmain(int argc, wchar_t **argv)
{
    int i = 1;
    int wait_for_child = 0;

    /* Skip elevate's own leading flags. */
    while (i < argc && (argv[i][0] == L'-' || argv[i][0] == L'/')) {
        if (!_wcsicmp(argv[i], L"-wait") || !_wcsicmp(argv[i], L"/wait"))
            wait_for_child = 1;
        else if (!_wcsicmp(argv[i], L"-?") || !_wcsicmp(argv[i], L"/?")) {
            wprintf(L"elevate passthrough (Wine): elevate [-wait|-k] prog [args]\n");
            return 0;
        }
        /* -k and anything else: ignore */
        i++;
    }

    if (i >= argc) {
        fwprintf(stderr, L"elevate passthrough: no program specified\n");
        return 1;
    }

    /* Build the command line: "prog" arg1 arg2 ... */
    wchar_t cmdline[32768];
    cmdline[0] = 0;

    wchar_t piece[4096];
    quote_arg(argv[i], piece, 4096);
    wcsncat(cmdline, piece, 32767);
    i++;

    for (; i < argc; i++) {
        wcsncat(cmdline, L" ", 32767 - wcslen(cmdline));
        quote_arg(argv[i], piece, 4096);
        wcsncat(cmdline, piece, 32767 - wcslen(cmdline));
    }

    /* --- Diagnostics ---
     * Log the exact command line we were asked to run (UTF-8 via WriteFile, which
     * is robust under Wine), and capture the child's stdout/stderr to a file, so
     * we can see why the elevated helper exits. Set ALMA_ELEVATE_LOG=0 to disable. */
    int do_log = 1;
    {
        wchar_t buf[8];
        if (GetEnvironmentVariableW(L"ALMA_ELEVATE_LOG", buf, 8) > 0 && buf[0] == L'0')
            do_log = 0;
    }
    /* A valid, inheritable stdin for the child. Handing a Node/Electron child an
     * INVALID/closed stdin handle makes it die under Wine with
     * "Error: open EBADF ... at new Socket", so always use the NUL device. */
    SECURITY_ATTRIBUTES sa_in;
    sa_in.nLength = sizeof(sa_in);
    sa_in.lpSecurityDescriptor = NULL;
    sa_in.bInheritHandle = TRUE;
    HANDLE child_in = CreateFileW(L"NUL", GENERIC_READ | GENERIC_WRITE,
                                  FILE_SHARE_READ | FILE_SHARE_WRITE,
                                  &sa_in, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);

    HANDLE child_out = INVALID_HANDLE_VALUE;
    if (do_log) {
        HANDLE h = CreateFileW(L"C:\\alma-elevate.log",
                               FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                               NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (h != INVALID_HANDLE_VALUE) {
            char u8[40000];
            int n = WideCharToMultiByte(CP_UTF8, 0, cmdline, -1, u8, sizeof(u8) - 16, NULL, NULL);
            if (n > 0) {
                /* overwrite trailing NUL with newline */
                u8[n - 1] = '\n';
                DWORD wr;
                const char *prefix = "[elevate] cmdline: ";
                WriteFile(h, prefix, (DWORD)strlen(prefix), &wr, NULL);
                WriteFile(h, u8, (DWORD)n, &wr, NULL);
            }
            CloseHandle(h);
        }
        SECURITY_ATTRIBUTES sa;
        ZeroMemory(&sa, sizeof(sa));
        sa.nLength = sizeof(sa);
        sa.bInheritHandle = TRUE;
        child_out = CreateFileW(L"C:\\alma-clientservices.log",
                                FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                &sa, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    }

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    BOOL inherit = FALSE;
    if (child_in != INVALID_HANDLE_VALUE) {
        /* Always provide a valid stdin (NUL). Route stdout/stderr to the log if
         * logging is on, otherwise to NUL as well -- never a closed handle. */
        si.dwFlags |= STARTF_USESTDHANDLES;
        si.hStdInput = child_in;
        si.hStdOutput = (child_out != INVALID_HANDLE_VALUE) ? child_out : child_in;
        si.hStdError = (child_out != INVALID_HANDLE_VALUE) ? child_out : child_in;
        inherit = TRUE;
    }

    /* Launch directly. No runas. Inherit environment. Detach console so the
     * child is not killed when this passthrough exits. */
    BOOL ok = CreateProcessW(
        NULL,
        cmdline,
        NULL, NULL,
        inherit,
        CREATE_NEW_PROCESS_GROUP,
        NULL,
        NULL,
        &si, &pi);

    if (!ok) {
        fwprintf(stderr, L"elevate passthrough: CreateProcess failed (%lu)\n",
                 GetLastError());
        if (do_log) {
            FILE *lf = _wfopen(L"C:\\alma-elevate.log", L"a, ccs=UTF-8");
            if (lf) {
                fwprintf(lf, L"[elevate] CreateProcess FAILED: %lu\n", GetLastError());
                fclose(lf);
            }
        }
        return 1;
    }

    DWORD code = 0;
    if (wait_for_child) {
        WaitForSingleObject(pi.hProcess, INFINITE);
        GetExitCodeProcess(pi.hProcess, &code);
    }

    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return (int)code;
}
