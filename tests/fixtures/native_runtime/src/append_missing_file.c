#include <stdint.h>
typedef void *HANDLE; typedef uint32_t DWORD; typedef const wchar_t *LPCWSTR; typedef void *LPVOID;
__attribute__((dllimport)) HANDLE __stdcall CreateFileW(LPCWSTR,DWORD,DWORD,LPVOID,DWORD,DWORD,HANDLE);
__attribute__((dllimport)) void __stdcall ExitProcess(DWORD);
#define OPEN_EXISTING 3u
#define FILE_APPEND_DATA 0x0004u
void entry(void) {
    HANDLE f = CreateFileW(L"missing.txt", FILE_APPEND_DATA, 0, 0, OPEN_EXISTING, 0x80, 0);
    if (f != (HANDLE)(intptr_t)-1) ExitProcess(2);
    ExitProcess(0);
}
