#include <stdint.h>
typedef void *HANDLE; typedef uint32_t DWORD; typedef int BOOL; typedef const wchar_t *LPCWSTR; typedef void *LPVOID; typedef const void *LPCVOID;
typedef struct { DWORD a,b,c,d; DWORD e,f,g,h; } OVERLAPPED;
__attribute__((dllimport)) HANDLE __stdcall CreateFileW(LPCWSTR,DWORD,DWORD,LPVOID,DWORD,DWORD,HANDLE);
__attribute__((dllimport)) BOOL __stdcall WriteFile(HANDLE,LPCVOID,DWORD,DWORD*,LPVOID);
__attribute__((dllimport)) BOOL __stdcall CloseHandle(HANDLE);
__attribute__((dllimport)) void __stdcall ExitProcess(DWORD);
#define OPEN_EXISTING 3u
#define FILE_APPEND_DATA 0x0004u
void entry(void) {
    const char msg[] = "x";
    OVERLAPPED ov = {0};
    HANDLE f = CreateFileW(L"seed.txt", FILE_APPEND_DATA, 0, 0, OPEN_EXISTING, 0x80, 0);
    if (f == (HANDLE)(intptr_t)-1) ExitProcess(1);
    DWORD w=0;
    if (WriteFile(f, msg, 1, &w, &ov)) ExitProcess(2);
    CloseHandle(f);
    ExitProcess(0);
}
