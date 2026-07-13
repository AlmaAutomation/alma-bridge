/*
 * cs_wrapper_diag.c — investigation-only wrapper (NOT installed by production).
 *
 * Same as cs_wrapper.c but does NOT rewrite --launcher-pid to the decoy PID.
 * Spawns the decoy for observability, yet forwards the original launcher PID
 * from argv so Control D can test whether decoy substitution is the failure source.
 *
 * Build (investigation script only):
 *   x86_64-w64-mingw32-gcc -municode -O2 -s -o cs_wrapper_diag.exe tools/diagnostics/cs_wrapper_diag.c
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

static const char ALMA_CS_WRAPPER_MARKER[] = "alma-cs-wrapper-diag-v1";

static void logline(const wchar_t *path, const wchar_t *wtext)
{
    HANDLE h = CreateFileW(path, FILE_APPEND_DATA,
                           FILE_SHARE_READ | FILE_SHARE_WRITE,
                           NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    char u8[40000];
    int n = WideCharToMultiByte(CP_UTF8, 0, wtext, -1, u8, sizeof(u8) - 4, NULL, NULL);
    if (n > 0) { u8[n - 1] = '\n'; DWORD wr; WriteFile(h, u8, (DWORD)n, &wr, NULL); }
    CloseHandle(h);
}

static HANDLE open_inheritable(const wchar_t *path, DWORD access, DWORD disp)
{
    SECURITY_ATTRIBUTES sa;
    sa.nLength = sizeof(sa);
    sa.lpSecurityDescriptor = NULL;
    sa.bInheritHandle = TRUE;
    return CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE,
                       &sa, disp, FILE_ATTRIBUTE_NORMAL, NULL);
}

int wmain(int argc, wchar_t **argv)
{
    if (argc >= 2 && !_wcsicmp(argv[1], L"--alma-decoy")) {
        for (;;) Sleep(60000);
        return 0;
    }

    {
        HANDLE h = CreateFileW(L"C:\\alma-cs-invoke.log", FILE_APPEND_DATA,
                               FILE_SHARE_READ | FILE_SHARE_WRITE,
                               NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (h != INVALID_HANDLE_VALUE) {
            DWORD wr;
            WriteFile(h, ALMA_CS_WRAPPER_MARKER, (DWORD)strlen(ALMA_CS_WRAPPER_MARKER), &wr, NULL);
            WriteFile(h, "\n", 1, &wr, NULL);
            CloseHandle(h);
        }
    }

    wchar_t self[MAX_PATH];
    GetModuleFileNameW(NULL, self, MAX_PATH);
    wchar_t dir[MAX_PATH] = L".";
    wchar_t base[MAX_PATH] = L"sidecar";
    wchar_t *slash = wcsrchr(self, L'\\');
    if (slash) {
        size_t len = (size_t)(slash - self);
        wcsncpy(dir, self, len); dir[len] = 0;
        wcsncpy(base, slash + 1, MAX_PATH - 1);
    } else {
        wcsncpy(base, self, MAX_PATH - 1);
    }
    size_t bl = wcslen(base);
    if (bl > 4 && !_wcsicmp(base + bl - 4, L".exe")) base[bl - 4] = 0;

    wchar_t target[MAX_PATH];
    _snwprintf(target, MAX_PATH, L"%s\\%s.real.exe", dir, base);

    wchar_t launcher_name[256];
    if (GetEnvironmentVariableW(L"ALMA_LAUNCHER_EXE_NAME", launcher_name, 256) == 0)
        wcsncpy(launcher_name, L"Ascension Launcher.exe", 256);

    wchar_t decoy_dir[MAX_PATH];
    _snwprintf(decoy_dir, MAX_PATH, L"%s\\alma-guard", dir);
    CreateDirectoryW(decoy_dir, NULL);
    wchar_t decoy_path[MAX_PATH];
    _snwprintf(decoy_path, MAX_PATH, L"%s\\%s", decoy_dir, launcher_name);

    HANDLE hNul = open_inheritable(L"NUL", GENERIC_READ | GENERIC_WRITE, OPEN_EXISTING);
    HANDLE hLog = open_inheritable(L"C:\\alma-cs-output.log",
                                   FILE_APPEND_DATA, OPEN_ALWAYS);
    if (hLog == INVALID_HANDLE_VALUE) hLog = hNul;

    DWORD decoy_pid = 0;
    HANDLE decoy_proc = NULL;
    {
        wchar_t dcmd[MAX_PATH + 32];
        _snwprintf(dcmd, MAX_PATH + 32, L"\"%s\" --alma-decoy", decoy_path);
        STARTUPINFOW dsi; PROCESS_INFORMATION dpi;
        ZeroMemory(&dsi, sizeof(dsi)); dsi.cb = sizeof(dsi);
        dsi.dwFlags = STARTF_USESTDHANDLES;
        dsi.hStdInput = hNul; dsi.hStdOutput = hNul; dsi.hStdError = hNul;
        ZeroMemory(&dpi, sizeof(dpi));
        if (CreateProcessW(NULL, dcmd, NULL, NULL, TRUE,
                          CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                          NULL, NULL, &dsi, &dpi)) {
            decoy_pid = dpi.dwProcessId;
            decoy_proc = dpi.hProcess;
            CloseHandle(dpi.hThread);
        }
    }

    /* DIAG: forward argv unchanged — do NOT rewrite --launcher-pid. */
    static wchar_t cmdline[32768];
    _snwprintf(cmdline, 32768, L"\"%s\"", target);
    for (int i = 1; i < argc; i++) {
        wcsncat(cmdline, L" ", 32767 - wcslen(cmdline));
        if (wcschr(argv[i], L' ') || wcschr(argv[i], L'\t')) {
            wcsncat(cmdline, L"\"", 32767 - wcslen(cmdline));
            wcsncat(cmdline, argv[i], 32767 - wcslen(cmdline));
            wcsncat(cmdline, L"\"", 32767 - wcslen(cmdline));
        } else {
            wcsncat(cmdline, argv[i], 32767 - wcslen(cmdline));
        }
    }

    {
        wchar_t msg[33000];
        _snwprintf(msg, 33000,
                   L"[cs-wrapper-diag] decoy_pid=%lu passthrough_cmdline=%s",
                   decoy_pid, cmdline);
        logline(L"C:\\alma-cs-invoke.log", msg);
    }

    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si)); si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = hNul; si.hStdOutput = hLog; si.hStdError = hLog;
    ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(NULL, cmdline, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        if (decoy_proc) { TerminateProcess(decoy_proc, 0); CloseHandle(decoy_proc); }
        return 1;
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    if (decoy_proc) { TerminateProcess(decoy_proc, 0); CloseHandle(decoy_proc); }
    if (hNul != INVALID_HANDLE_VALUE) CloseHandle(hNul);
    if (hLog != INVALID_HANDLE_VALUE && hLog != hNul) CloseHandle(hLog);
    {
        wchar_t m[128];
        _snwprintf(m, 128, L"[cs-wrapper-diag] sidecar exited code=%lu", code);
        logline(L"C:\\alma-cs-invoke.log", m);
    }
    return (int)code;
}
