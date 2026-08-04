/*
 * Alma native runtime kernel32 shim (ms_abi) for Milestone 2.
 * Compiled with pe_loader.c into libalma_native_shim.so
 */
#define _GNU_SOURCE
#include "pe_loader.h"

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <setjmp.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <wchar.h>

#ifdef __x86_64__
#define MS_ABI __attribute__((ms_abi))
#else
#define MS_ABI
#endif

typedef void *HANDLE;
typedef uint32_t DWORD;
typedef int BOOL;
typedef const wchar_t *LPCWSTR;
typedef wchar_t *LPWSTR;
typedef const void *LPCVOID;
typedef void *LPVOID;

static char g_workspace[4096];
static uint16_t g_command_line[4096];
static char g_stdout_buf[65536];
static char g_stderr_buf[65536];
static size_t g_stdout_len;
static size_t g_stderr_len;
static int g_exit_code;
static int g_exited;
static int g_entrypoint_invoked;
static int g_simulation_used;
static const char *g_execution_mode = "mapped_pe_entrypoint";
static DWORD g_last_error;

static sigjmp_buf g_jmp_env;

#define MAX_ENV 64
static uint16_t g_env_keys[MAX_ENV][128];
static uint16_t g_env_vals[MAX_ENV][512];
static int g_env_count;

void alma_native_init_ex(const char *workspace, const void *command_line_utf16, const char *env_block);

static int utf16le_to_utf8(const uint16_t *ws, char *out, size_t out_sz) {
    if (!ws || !out || out_sz == 0) return -1;
    size_t i = 0;
    for (size_t j = 0; ws[j] != 0 && i + 1 < out_sz; j++) {
        uint32_t wc = ws[j];
        if (wc < 0x80) out[i++] = (char)wc;
        else if (wc < 0x800) {
            if (i + 2 >= out_sz) break;
            out[i++] = (char)(0xC0 | (wc >> 6));
            out[i++] = (char)(0x80 | (wc & 0x3F));
        } else {
            if (i + 3 >= out_sz) break;
            out[i++] = (char)(0xE0 | (wc >> 12));
            out[i++] = (char)(0x80 | ((wc >> 6) & 0x3F));
            out[i++] = (char)(0x80 | (wc & 0x3F));
        }
    }
    out[i] = '\0';
    return (int)i;
}

static void utf8_to_utf16le(const char *src, uint16_t *dst, size_t dst_count) {
    if (!src || !dst || dst_count == 0) return;
    size_t i = 0;
    for (; *src && i + 1 < dst_count; i++) {
        dst[i] = (uint16_t)(unsigned char)*src++;
    }
    dst[i] = 0;
}

static int utf16le_eq(const uint16_t *a, const uint16_t *b) {
    if (!a || !b) return 0;
    while (*a && *b) {
        uint16_t ca = *a++;
        uint16_t cb = *b++;
        if (ca >= 'A' && ca <= 'Z') ca += 32;
        if (cb >= 'A' && cb <= 'Z') cb += 32;
        if (ca != cb) return 0;
    }
    return *a == *b;
}

static size_t utf16le_len(const uint16_t *ws) {
    size_t n = 0;
    if (ws) while (ws[n]) n++;
    return n;
}

#define STD_OUTPUT_HANDLE ((DWORD)-11)
#define STD_ERROR_HANDLE ((DWORD)-12)
#define INVALID_HANDLE_VALUE ((HANDLE)(intptr_t)-1)
#define GENERIC_READ 0x80000000u
#define GENERIC_WRITE 0x40000000u
#define OPEN_EXISTING 3u
#define CREATE_ALWAYS 2u
#define FILE_APPEND_DATA 0x0004u
#define FILE_ATTRIBUTE_NORMAL 0x80u
#define FILE_SHARE_READ 1u
#define ERROR_FILE_NOT_FOUND 2u
#define ERROR_ACCESS_DENIED 3u
#define ERROR_INVALID_HANDLE 6u
#define ERROR_NOT_SUPPORTED 50u
#define ERROR_INVALID_PARAMETER 87u

typedef struct {
    int fd;
    int is_file;
    int append_mode;
} file_handle_t;

#define MAX_FILES 32
static file_handle_t g_files[MAX_FILES];

static void reset_files(void) {
    for (int i = 0; i < MAX_FILES; i++) {
        if (g_files[i].is_file && g_files[i].fd >= 0) close(g_files[i].fd);
        g_files[i].fd = -1;
        g_files[i].is_file = 0;
        g_files[i].append_mode = 0;
    }
}

static int alloc_file_fd(int fd, int append_mode) {
    for (int i = 0; i < MAX_FILES; i++) {
        if (g_files[i].fd < 0) {
            g_files[i].fd = fd;
            g_files[i].is_file = 1;
            g_files[i].append_mode = append_mode;
            return i + 10;
        }
    }
    return -1;
}

static void append_out(int fd, const void *data, uint32_t len) {
    char *buf = (fd == 2) ? g_stderr_buf : g_stdout_buf;
    size_t *lenp = (fd == 2) ? &g_stderr_len : &g_stdout_len;
    size_t max = (fd == 2) ? sizeof(g_stderr_buf) - 1 : sizeof(g_stdout_buf) - 1;
    size_t n = len;
    if (*lenp + n > max) n = max - *lenp;
    memcpy(buf + *lenp, data, n);
    *lenp += n;
    buf[*lenp] = '\0';
}

static int wide_to_utf8(LPCWSTR ws, char *out, size_t out_sz) {
    return utf16le_to_utf8((const uint16_t *)ws, out, out_sz);
}

static int resolve_workspace_path(LPCWSTR wpath, char *out, size_t out_sz) {
    char rel[2048];
    if (wide_to_utf8(wpath, rel, sizeof(rel)) < 0) return -1;
    for (char *p = rel; *p; p++) {
        if (*p == '\\') *p = '/';
    }
    if (strstr(rel, "..") != NULL) return -1;
    const char *name = rel;
    if (*name == '/') name++;
    snprintf(out, out_sz, "%s/%s", g_workspace, name);
    return 0;
}

static int str_ieq(const char *a, const char *b) {
    while (*a && *b) {
        char ca = (*a >= 'A' && *a <= 'Z') ? (*a + 32) : *a;
        char cb = (*b >= 'A' && *b <= 'Z') ? (*b + 32) : *b;
        if (ca != cb) return 0;
        a++;
        b++;
    }
    return *a == *b;
}

void alma_native_init(const char *workspace) {
    static const uint16_t default_cmd[] = {'f','i','x','t','u','r','e','.','e','x','e',0};
    alma_native_init_ex(workspace, default_cmd, NULL);
}

void alma_native_init_ex(const char *workspace, const void *command_line_utf16, const char *env_block) {
    strncpy(g_workspace, workspace ? workspace : ".", sizeof(g_workspace) - 1);
    g_workspace[sizeof(g_workspace) - 1] = '\0';
    const uint16_t *cmd = (const uint16_t *)command_line_utf16;
    if (!cmd) {
        static const uint16_t default_cmd[] = {'f','i','x','t','u','r','e','.','e','x','e',0};
        cmd = default_cmd;
    }
    for (size_t i = 0; i < 4095 && cmd[i]; i++) g_command_line[i] = cmd[i];
    g_command_line[4095] = 0;
    g_stdout_len = g_stderr_len = 0;
    g_stdout_buf[0] = g_stderr_buf[0] = '\0';
    g_exit_code = 0;
    g_exited = 0;
    g_entrypoint_invoked = 0;
    g_simulation_used = 0;
    g_last_error = 0;
    g_env_count = 0;
    reset_files();
    if (env_block) {
        char buf[4096];
        strncpy(buf, env_block, sizeof(buf) - 1);
        buf[sizeof(buf) - 1] = '\0';
        char *save = NULL;
        for (char *line = strtok_r(buf, "\n", &save); line && g_env_count < MAX_ENV;
             line = strtok_r(NULL, "\n", &save)) {
            char *eq = strchr(line, '=');
            if (!eq) continue;
            *eq = '\0';
            utf8_to_utf16le(line, g_env_keys[g_env_count], 127);
            {
                char *val = eq + 1;
                char *nl = strpbrk(val, "\r\n");
                if (nl) *nl = '\0';
                utf8_to_utf16le(val, g_env_vals[g_env_count], 511);
            }
            g_env_count++;
        }
    }
}

const char *alma_native_get_stdout(void) { return g_stdout_buf; }
const char *alma_native_get_stderr(void) { return g_stderr_buf; }
size_t alma_native_get_stdout_len(void) { return g_stdout_len; }
size_t alma_native_get_stderr_len(void) { return g_stderr_len; }
int alma_native_get_env_count(void) { return g_env_count; }
int alma_native_get_entrypoint_invoked(void) { return g_entrypoint_invoked; }
int alma_native_get_simulation_used(void) { return g_simulation_used; }
const char *alma_native_get_execution_mode(void) { return g_execution_mode; }
uint64_t alma_native_get_load_base(void) { return 0; }

static HANDLE MS_ABI shim_GetStdHandle(DWORD n) {
    if (n == STD_OUTPUT_HANDLE) return (HANDLE)(intptr_t)1;
    if (n == STD_ERROR_HANDLE) return (HANDLE)(intptr_t)2;
    return INVALID_HANDLE_VALUE;
}

static BOOL MS_ABI shim_WriteFile(HANDLE h, LPCVOID buf, DWORD len, DWORD *written, LPVOID ov) {
    if (ov != NULL) {
        g_last_error = ERROR_NOT_SUPPORTED;
        return 0;
    }
    intptr_t hv = (intptr_t)h;
    if (hv == 1 || hv == 2) {
        append_out((int)hv, buf, len);
        if (written) *written = len;
        return 1;
    }
    if (hv >= 10 && hv < 10 + MAX_FILES) {
        file_handle_t *fh = &g_files[hv - 10];
        if (fh->is_file && fh->fd >= 0) {
            if (len == 0) {
                if (written) *written = 0;
                return 1;
            }
            ssize_t n = write(fh->fd, buf, len);
            if (n < 0) {
                g_last_error = ERROR_INVALID_HANDLE;
                return 0;
            }
            if (written) *written = (DWORD)n;
            return 1;
        }
    }
    g_last_error = ERROR_INVALID_HANDLE;
    return 0;
}

static BOOL MS_ABI shim_ReadFile(HANDLE h, LPVOID buf, DWORD len, DWORD *nread, LPVOID ov) {
    (void)ov;
    intptr_t hv = (intptr_t)h;
    if (hv >= 10 && hv < 10 + MAX_FILES) {
        file_handle_t *fh = &g_files[hv - 10];
        if (fh->is_file && fh->fd >= 0) {
            ssize_t n = read(fh->fd, buf, len);
            if (n < 0) return 0;
            if (nread) *nread = (DWORD)n;
            return 1;
        }
    }
    if (nread) *nread = 0;
    return 0;
}

static void MS_ABI shim_ExitProcess(DWORD code) {
    g_exit_code = (int)code;
    g_exited = 1;
    siglongjmp(g_jmp_env, 1);
}

static LPCWSTR MS_ABI shim_GetCommandLineW(void) {
    return (LPCWSTR)g_command_line;
}

static DWORD MS_ABI shim_GetEnvironmentVariableW(LPCWSTR name, LPWSTR buf, DWORD sz) {
    if (!name || !buf || sz == 0) return 0;
    const uint16_t *n16 = (const uint16_t *)name;
    for (int i = 0; i < g_env_count; i++) {
        if (utf16le_eq(n16, g_env_keys[i])) {
            size_t n = utf16le_len(g_env_vals[i]);
            if (n >= sz) n = sz - 1;
            for (size_t j = 0; j <= n; j++) ((uint16_t *)buf)[j] = g_env_vals[i][j];
            return (DWORD)n;
        }
    }
    buf[0] = 0;
    return 0;
}

static HANDLE MS_ABI shim_CreateFileW(LPCWSTR path, DWORD access, DWORD share, LPVOID sec,
                                      DWORD disp, DWORD flags, HANDLE tmpl) {
    (void)share;
    (void)sec;
    (void)flags;
    (void)tmpl;
    char full[4096];
    if (resolve_workspace_path(path, full, sizeof(full)) != 0) {
        g_last_error = ERROR_ACCESS_DENIED;
        return INVALID_HANDLE_VALUE;
    }
    int append_mode = 0;
    int flags_posix = O_CLOEXEC;
    if (access & FILE_APPEND_DATA) {
        if (disp != OPEN_EXISTING) {
            g_last_error = ERROR_INVALID_PARAMETER;
            return INVALID_HANDLE_VALUE;
        }
        flags_posix |= O_RDWR | O_APPEND;
        append_mode = 1;
    } else if (access & GENERIC_WRITE) {
        if (disp == CREATE_ALWAYS) flags_posix |= O_CREAT | O_TRUNC | O_RDWR;
        else if (disp == OPEN_EXISTING) flags_posix |= O_RDWR;
        else flags_posix |= O_CREAT | O_RDWR;
    } else {
        flags_posix |= O_RDONLY;
    }
    int fd = open(full, flags_posix, 0644);
    if (fd < 0) {
        if (errno == ENOENT) g_last_error = ERROR_FILE_NOT_FOUND;
        else if (errno == EACCES) g_last_error = ERROR_ACCESS_DENIED;
        else g_last_error = ERROR_FILE_NOT_FOUND;
        return INVALID_HANDLE_VALUE;
    }
    int slot = alloc_file_fd(fd, append_mode);
    if (slot < 0) {
        close(fd);
        return INVALID_HANDLE_VALUE;
    }
    return (HANDLE)(intptr_t)slot;
}

static BOOL MS_ABI shim_CloseHandle(HANDLE h) {
    intptr_t hv = (intptr_t)h;
    if (hv >= 10 && hv < 10 + MAX_FILES) {
        file_handle_t *fh = &g_files[hv - 10];
        if (fh->is_file && fh->fd >= 0) close(fh->fd);
        fh->fd = -1;
        fh->is_file = 0;
        return 1;
    }
    return 1;
}

static DWORD MS_ABI shim_GetLastError(void) { return g_last_error; }

static void MS_ABI shim_SetLastError(DWORD err) { g_last_error = err; }

static DWORD MS_ABI shim_GetModuleFileNameW(HANDLE mod, LPWSTR buf, DWORD sz) {
    (void)mod;
    if (!buf || sz == 0) return 0;
    uint16_t wpath[512];
    utf8_to_utf16le(g_workspace, wpath, 500);
    size_t n = utf16le_len(wpath);
    const uint16_t suffix[] = {'/','f','i','x','t','u','r','e','.','e','x','e',0};
    for (size_t i = 0; suffix[i] && n + i + 1 < 511; i++) wpath[n + i] = suffix[i];
    wpath[n + 12] = 0;
    n = utf16le_len(wpath);
    if (n >= sz) n = sz - 1;
    for (size_t j = 0; j <= n; j++) ((uint16_t *)buf)[j] = wpath[j];
    return (DWORD)n;
}

static DWORD MS_ABI shim_GetCurrentProcessId(void) { return (DWORD)getpid(); }

static void MS_ABI shim_Sleep(DWORD ms) {
    usleep((useconds_t)ms * 1000);
}

void *alma_shim_resolve_import(const char *name) {
    if (str_ieq(name, "GetStdHandle")) return (void *)shim_GetStdHandle;
    if (str_ieq(name, "WriteFile")) return (void *)shim_WriteFile;
    if (str_ieq(name, "ReadFile")) return (void *)shim_ReadFile;
    if (str_ieq(name, "CreateFileW")) return (void *)shim_CreateFileW;
    if (str_ieq(name, "CloseHandle")) return (void *)shim_CloseHandle;
    if (str_ieq(name, "GetCommandLineW")) return (void *)shim_GetCommandLineW;
    if (str_ieq(name, "GetEnvironmentVariableW")) return (void *)shim_GetEnvironmentVariableW;
    if (str_ieq(name, "GetLastError")) return (void *)shim_GetLastError;
    if (str_ieq(name, "SetLastError")) return (void *)shim_SetLastError;
    if (str_ieq(name, "GetModuleFileNameW")) return (void *)shim_GetModuleFileNameW;
    if (str_ieq(name, "GetCurrentProcessId")) return (void *)shim_GetCurrentProcessId;
    if (str_ieq(name, "Sleep")) return (void *)shim_Sleep;
    if (str_ieq(name, "ExitProcess")) return (void *)shim_ExitProcess;
    return NULL;
}

int32_t alma_native_run_pe(void *image, uint64_t base, uint32_t entry_rva) {
    (void)image;
    (void)base;
    (void)entry_rva;
    g_last_error = ENOSYS;
    return -1;
}

int32_t alma_native_load_and_run(
    const uint8_t *pe_data,
    size_t pe_size,
    uint64_t load_base_override
) {
    g_execution_mode = "mapped_pe_entrypoint";
    g_simulation_used = 0;
    int invoked = 0;
    if (sigsetjmp(g_jmp_env, 1) == 0) {
        int32_t rc = alma_pe_load_and_run(pe_data, pe_size, load_base_override, 0, &invoked);
        if (rc < 0 && !g_exited) return rc;
    }
    g_entrypoint_invoked = invoked || g_exited;
    return g_exited ? g_exit_code : 0;
}
