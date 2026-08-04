#include <stdint.h>
typedef void *HANDLE; typedef uint32_t DWORD; typedef int BOOL; typedef const wchar_t *LPCWSTR; typedef void *LPVOID; typedef const void *LPCVOID;
__attribute__((dllimport)) HANDLE __stdcall CreateFileW(LPCWSTR,DWORD,DWORD,LPVOID,DWORD,DWORD,HANDLE);
__attribute__((dllimport)) BOOL __stdcall WriteFile(HANDLE,LPCVOID,DWORD,DWORD*,LPVOID);
__attribute__((dllimport)) BOOL __stdcall CloseHandle(HANDLE);
__attribute__((dllimport)) void __stdcall ExitProcess(DWORD);
#define OPEN_EXISTING 3u
#define FILE_APPEND_DATA 0x0004u
void entry(void) {
    const char msg[] = "appended by fixture\n";
    HANDLE f = CreateFileW(L"seed.txt", FILE_APPEND_DATA, 0, 0, OPEN_EXISTING, 0x80, 0);
    if (f == (HANDLE)(intptr_t)-1) ExitProcess(1);
    DWORD w=0; WriteFile(f, msg, sizeof(msg)-1, &w, 0); CloseHandle(f);
    ExitProcess(0);
}
