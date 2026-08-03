#include <stdint.h>
typedef void *HANDLE; typedef uint32_t DWORD; typedef int BOOL; typedef const wchar_t *LPCWSTR; typedef void *LPVOID; typedef const void *LPCVOID;
__attribute__((dllimport)) HANDLE __stdcall CreateFileW(LPCWSTR,DWORD,DWORD,LPVOID,DWORD,DWORD,HANDLE);
__attribute__((dllimport)) BOOL __stdcall WriteFile(HANDLE,LPCVOID,DWORD,DWORD*,LPVOID);
__attribute__((dllimport)) BOOL __stdcall CloseHandle(HANDLE);
__attribute__((dllimport)) void __stdcall ExitProcess(DWORD);
void entry(void) {
    const char msg[] = "written by fixture\n";
    HANDLE f = CreateFileW(L"output.txt", 0x40000000, 0, 0, 2, 0x80, 0);
    DWORD w=0; WriteFile(f, msg, sizeof(msg)-1, &w, 0); CloseHandle(f);
    ExitProcess(0);
}
