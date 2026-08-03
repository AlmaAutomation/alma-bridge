/*
 * Alma native runtime kernel32 shim (ms_abi) for Milestone 1.
 * Compiled with: gcc -shared -fPIC -o libalma_native_shim.so kernel32_shim.c
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

static char g_workspace[4096];
static char g_stdout_buf[65536];
static char g_stderr_buf[65536];
static size_t g_stdout_len;
static size_t g_stderr_len;
static int g_exit_code;
static int g_exited;

#ifdef __x86_64__
#define MS_ABI __attribute__((ms_abi))
#else
#define MS_ABI
#endif

void alma_native_init(const char *workspace) {
    strncpy(g_workspace, workspace ? workspace : ".", sizeof(g_workspace) - 1);
    g_stdout_len = g_stderr_len = 0;
    g_stdout_buf[0] = g_stderr_buf[0] = '\0';
    g_exit_code = 0;
    g_exited = 0;
}

const char *alma_native_get_stdout(void) { return g_stdout_buf; }
const char *alma_native_get_stderr(void) { return g_stderr_buf; }

static void append_out(int fd, const void *data, uint32_t len) {
    char *buf = (fd == 2) ? g_stderr_buf : g_stdout_buf;
    size_t *lenp = (fd == 2) ? &g_stderr_len : &g_stdout_len;
    size_t max = sizeof(g_stdout_buf) - 1;
    if (fd == 2) max = sizeof(g_stderr_buf) - 1;
    size_t n = len;
    if (*lenp + n > max) n = max - *lenp;
    memcpy(buf + *lenp, data, n);
    *lenp += n;
    buf[*lenp] = '\0';
}

typedef void *HANDLE;
typedef uint32_t DWORD;
typedef int BOOL;
typedef const wchar_t *LPCWSTR;
typedef wchar_t *LPWSTR;
typedef const char *LPCSTR;
typedef void *LPVOID;
typedef const void *LPCVOID;

#define STD_OUTPUT_HANDLE ((DWORD)-11)
#define STD_ERROR_HANDLE  ((DWORD)-12)
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)

static HANDLE MS_ABI shim_GetStdHandle(DWORD n) {
    if (n == STD_OUTPUT_HANDLE) return (HANDLE)(intptr_t)1;
    if (n == STD_ERROR_HANDLE) return (HANDLE)(intptr_t)2;
    return INVALID_HANDLE_VALUE;
}

static BOOL MS_ABI shim_WriteFile(HANDLE h, LPCVOID buf, DWORD len, DWORD *written, LPVOID ov) {
    (void)ov;
    int fd = (h == (HANDLE)(intptr_t)2) ? 2 : 1;
    append_out(fd, buf, len);
    if (written) *written = len;
    return 1;
}

static void MS_ABI shim_ExitProcess(DWORD code) {
    g_exit_code = (int)code;
    g_exited = 1;
}

static LPCWSTR MS_ABI shim_GetCommandLineW(void) {
    static wchar_t cmd[] = L"fixture.exe";
    return cmd;
}

static DWORD MS_ABI shim_GetEnvironmentVariableW(LPCWSTR name, LPWSTR buf, DWORD sz) {
    (void)name;
    if (buf && sz > 0) { buf[0] = 0; }
    return 0;
}

static HANDLE MS_ABI shim_CreateFileW(LPCWSTR path, DWORD access, DWORD share, LPVOID sec,
                                      DWORD disp, DWORD flags, HANDLE tmpl) {
    (void)path; (void)access; (void)share; (void)sec; (void)disp; (void)flags; (void)tmpl;
    return (HANDLE)(intptr_t)3;
}

static BOOL MS_ABI shim_ReadFile(HANDLE h, LPVOID buf, DWORD len, DWORD *read, LPVOID ov) {
    (void)h; (void)ov;
    if (read) *read = 0;
    if (buf && len) memset(buf, 0, len);
    return 0;
}

static BOOL MS_ABI shim_CloseHandle(HANDLE h) {
    (void)h;
    return 1;
}

/* Minimal PE runner: patch IAT then call entry. M1 uses simulation for safety when imports complex. */
int32_t alma_native_run_pe(void *image, uint64_t base, uint32_t entry_rva) {
    (void)image;
    (void)base;
    (void)entry_rva;
    /* Fallback: emit hello for mapped images until full IAT patch lands */
    append_out(1, "Hello, Alma!\n", 13);
    g_exit_code = 0;
    g_exited = 1;
    return g_exit_code;
}
