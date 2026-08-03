#include <stdint.h>
typedef const wchar_t *LPCWSTR;
typedef wchar_t *LPWSTR;
typedef void *HANDLE;
__attribute__((dllimport)) uint32_t __stdcall GetEnvironmentVariableW(LPCWSTR, LPWSTR, uint32_t);
__attribute__((dllimport)) void __stdcall ExitProcess(uint32_t);
__attribute__((dllimport)) HANDLE __stdcall GetStdHandle(uint32_t);
__attribute__((dllimport)) int __stdcall WriteFile(HANDLE, const void*, uint32_t, uint32_t*, void*);
void entry(void) {
    wchar_t buf[64];
    uint32_t n = GetEnvironmentVariableW(L"ALMA_TEST_VAR", buf, 64);
    char ascii[64];
    uint32_t i;
    for (i = 0; i < n && i < 63; i++) ascii[i] = (char)buf[i];
    ascii[i] = '\0';
    uint32_t w = 0;
    WriteFile(GetStdHandle((uint32_t)-11), ascii, i, &w, 0);
    ExitProcess(0);
}
