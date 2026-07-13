/*
 * cs_wrapper.c
 *
 * Generic guard-workaround wrapper for an Electron app's elevated sidecar under
 * Wine (e.g. AscensionClientServices.exe for the Ascension Launcher).
 *
 * Problem: the sidecar runs a "launcher_guard" that takes --launcher-pid and,
 * once per second, checks whether the launcher process is still alive. Under
 * Wine the live Electron launcher PID is misreported as exited after ~1s, so the
 * guard shuts the sidecar (and its UI API server) down and the launcher is stuck
 * on its loading splash forever. Passing the wrapper's own PID does not work
 * either: the guard ALSO validates that the PID's process *name* matches the
 * launcher ("launcher PID does not belong to the launcher").
 *
 * Fix: spawn a tiny decoy process whose executable is named exactly like the
 * launcher (default "Ascension Launcher.exe", override with ALMA_LAUNCHER_EXE_NAME)
 * and that simply sleeps. Pass the decoy's PID as --launcher-pid. The guard then
 * sees a correctly-named, reliably-enumerable, always-alive process and stops
 * misfiring. The decoy is a copy of THIS wrapper (a trivial Win32 sleeper -- NOT
 * the real Electron launcher) run with --alma-decoy.
 *
 * stdio: children are always given VALID, inheritable handles -- NUL for stdin
 * and a real log file for stdout/stderr -- via STARTF_USESTDHANDLES. This is
 * important under Wine: handing a Node/Electron child a closed/invalid stdio
 * handle makes it die with "Error: open EBADF ... at new Socket". The decoy and
 * the Rust sidecar are not Electron, but we keep their stdio valid regardless so
 * the wrapper never propagates a bad handle it may have inherited.
 *
 * Install: rename the real sidecar to <name>.real.exe and drop this in as
 * <name>.exe. The wrapper runs "<name>.real.exe" in the same directory.
 *
 * Build:
 *   x86_64-w64-mingw32-gcc -municode -O2 -s -o cs_wrapper.exe cs_wrapper.c
 */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

/* ASCII marker Alma uses to verify this is the decoy-capable wrapper build. */
static const char ALMA_CS_WRAPPER_MARKER[] = "alma-cs-wrapper-decoy-v1";

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
    /* Decoy mode: just stay alive so the launcher_guard has a stable target. */
    if (argc >= 2 && !_wcsicmp(argv[1], L"--alma-decoy")) {
        for (;;) Sleep(60000);
        return 0;
    }

    /* Touch the marker so the linker keeps it (Alma verifies the build). */
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

    /* Resolve our own directory + base name. */
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
    /* base without trailing .exe */
    size_t bl = wcslen(base);
    if (bl > 4 && !_wcsicmp(base + bl - 4, L".exe")) base[bl - 4] = 0;

    wchar_t target[MAX_PATH];
    _snwprintf(target, MAX_PATH, L"%s\\%s.real.exe", dir, base);

    /* Decoy executable named like the launcher (so the guard's name check passes). */
    wchar_t launcher_name[256];
    if (GetEnvironmentVariableW(L"ALMA_LAUNCHER_EXE_NAME", launcher_name, 256) == 0)
        wcsncpy(launcher_name, L"Ascension Launcher.exe", 256);

    wchar_t decoy_dir[MAX_PATH];
    _snwprintf(decoy_dir, MAX_PATH, L"%s\\alma-guard", dir);
    CreateDirectoryW(decoy_dir, NULL);
    wchar_t decoy_path[MAX_PATH];
    _snwprintf(decoy_path, MAX_PATH, L"%s\\%s", decoy_dir, launcher_name);
    /* Decoy is pre-installed by Alma (tools/launcher_decoy.c). Do NOT copy this
     * wrapper here: Wine would still report the wrong process name if the decoy
     * were a renamed copy of AscensionClientServices.exe. */

    /* Valid, inheritable std handles for every child we spawn (avoid EBADF). */
    HANDLE hNul = open_inheritable(L"NUL", GENERIC_READ | GENERIC_WRITE, OPEN_EXISTING);
    HANDLE hLog = open_inheritable(L"C:\\alma-cs-output.log",
                                   FILE_APPEND_DATA, OPEN_ALWAYS);
    if (hLog == INVALID_HANDLE_VALUE) hLog = hNul;

    /* Launch the decoy (all stdio -> NUL) and capture its PID. */
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
        if (GetFileAttributesW(decoy_path) == INVALID_FILE_ATTRIBUTES) {
            wchar_t m[512];
            _snwprintf(m, 512, L"[cs-wrapper] decoy missing: %s", decoy_path);
            logline(L"C:\\alma-cs-invoke.log", m);
        } else if (CreateProcessW(NULL, dcmd, NULL, NULL, TRUE,
                                  CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
                                  NULL, NULL, &dsi, &dpi)) {
            decoy_pid = dpi.dwProcessId;
            decoy_proc = dpi.hProcess;
            CloseHandle(dpi.hThread);
        } else {
            wchar_t m[128];
            _snwprintf(m, 128, L"[cs-wrapper] decoy CreateProcess FAILED: %lu", GetLastError());
            logline(L"C:\\alma-cs-invoke.log", m);
        }
    }

    /* Build the real sidecar command, rewriting --launcher-pid to the decoy PID. */
    static wchar_t cmdline[32768];
    _snwprintf(cmdline, 32768, L"\"%s\"", target);
    wchar_t pidbuf[16];
    _snwprintf(pidbuf, 16, L"%lu", decoy_pid);
    int replace_next = 0;
    for (int i = 1; i < argc; i++) {
        const wchar_t *val = argv[i];
        if (replace_next) { val = pidbuf; replace_next = 0; }
        else if (decoy_pid && (!_wcsicmp(argv[i], L"--launcher-pid") || !_wcsicmp(argv[i], L"-launcher-pid")))
            replace_next = 1;
        wcsncat(cmdline, L" ", 32767 - wcslen(cmdline));
        if (wcschr(val, L' ') || wcschr(val, L'\t')) {
            wcsncat(cmdline, L"\"", 32767 - wcslen(cmdline));
            wcsncat(cmdline, val, 32767 - wcslen(cmdline));
            wcsncat(cmdline, L"\"", 32767 - wcslen(cmdline));
        } else {
            wcsncat(cmdline, val, 32767 - wcslen(cmdline));
        }
    }

    {
        wchar_t msg[33000];
        _snwprintf(msg, 33000, L"[cs-wrapper] decoy_pid=%lu cmdline=%s", decoy_pid, cmdline);
        logline(L"C:\\alma-cs-invoke.log", msg);
    }

    /* Sidecar: NUL stdin, log file for stdout/stderr -- all valid + inheritable. */
    STARTUPINFOW si; PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si)); si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = hNul; si.hStdOutput = hLog; si.hStdError = hLog;
    ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(NULL, cmdline, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        wchar_t m[128];
        _snwprintf(m, 128, L"[cs-wrapper] CreateProcess FAILED: %lu", GetLastError());
        logline(L"C:\\alma-cs-invoke.log", m);
        if (decoy_proc) { TerminateProcess(decoy_proc, 0); CloseHandle(decoy_proc); }
        return 1;
    }

    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    /* Sidecar is done -> tear down the decoy. */
    if (decoy_proc) { TerminateProcess(decoy_proc, 0); CloseHandle(decoy_proc); }
    if (hNul != INVALID_HANDLE_VALUE) CloseHandle(hNul);
    if (hLog != INVALID_HANDLE_VALUE && hLog != hNul) CloseHandle(hLog);
    {
        wchar_t m[128];
        _snwprintf(m, 128, L"[cs-wrapper] sidecar exited code=%lu", code);
        logline(L"C:\\alma-cs-invoke.log", m);
    }
    return (int)code;
}
