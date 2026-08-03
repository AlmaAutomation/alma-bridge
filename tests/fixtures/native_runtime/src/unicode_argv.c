#include <stdint.h>
typedef const wchar_t *LPCWSTR;
__attribute__((dllimport)) LPCWSTR __stdcall GetCommandLineW(void);
__attribute__((dllimport)) void __stdcall ExitProcess(uint32_t);
__attribute__((dllimport)) void * __stdcall GetStdHandle(uint32_t);
__attribute__((dllimport)) int __stdcall WriteFile(void*, const void*, uint32_t, uint32_t*, void*);
void entry(void) {
    LPCWSTR cmd = GetCommandLineW();
    uint32_t w=0;
    WriteFile(GetStdHandle((uint32_t)-11), cmd, 32, &w, 0);
    ExitProcess(0);
}
