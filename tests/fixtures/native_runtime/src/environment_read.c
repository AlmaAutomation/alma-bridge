#include <stdint.h>
typedef const wchar_t *LPCWSTR;
typedef wchar_t *LPWSTR;
__attribute__((dllimport)) uint32_t __stdcall GetEnvironmentVariableW(LPCWSTR, LPWSTR, uint32_t);
__attribute__((dllimport)) void __stdcall ExitProcess(uint32_t);
__attribute__((dllimport)) void * __stdcall GetStdHandle(uint32_t);
__attribute__((dllimport)) int __stdcall WriteFile(void*, const void*, uint32_t, uint32_t*, void*);
void entry(void) {
    wchar_t buf[64]; uint32_t n = GetEnvironmentVariableW(L"ALMA_TEST_VAR", buf, 64);
    uint32_t w=0; WriteFile(GetStdHandle((uint32_t)-11), buf, n*2, &w, 0);
    ExitProcess(0);
}
