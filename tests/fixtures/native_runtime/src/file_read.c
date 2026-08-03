#include <stdint.h>
typedef void *HANDLE; typedef uint32_t DWORD; typedef int BOOL; typedef const wchar_t *LPCWSTR; typedef void *LPVOID;
__attribute__((dllimport)) HANDLE __stdcall CreateFileW(LPCWSTR,DWORD,DWORD,LPVOID,DWORD,DWORD,HANDLE);
__attribute__((dllimport)) BOOL __stdcall ReadFile(HANDLE,LPVOID,DWORD,DWORD*,LPVOID);
__attribute__((dllimport)) BOOL __stdcall CloseHandle(HANDLE);
__attribute__((dllimport)) void __stdcall ExitProcess(DWORD);
__attribute__((dllimport)) BOOL __stdcall WriteFile(HANDLE, const void*, DWORD, DWORD*, LPVOID);
__attribute__((dllimport)) HANDLE __stdcall GetStdHandle(DWORD);
void entry(void) {
    HANDLE f = CreateFileW(L"input.txt", 0x80000000, 1, 0, 3, 0x80, 0);
    char buf[128]; DWORD r=0; ReadFile(f, buf, 128, &r, 0); CloseHandle(f);
    DWORD w=0; WriteFile(GetStdHandle((DWORD)-11), buf, r, &w, 0);
    ExitProcess(0);
}
