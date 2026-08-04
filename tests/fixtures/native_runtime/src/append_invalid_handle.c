#include <stdint.h>
typedef void *HANDLE; typedef uint32_t DWORD; typedef int BOOL; typedef const void *LPCVOID; typedef void *LPVOID;
__attribute__((dllimport)) BOOL __stdcall WriteFile(HANDLE,LPCVOID,DWORD,DWORD*,LPVOID);
__attribute__((dllimport)) void __stdcall ExitProcess(DWORD);
void entry(void) {
    DWORD w=0;
    if (WriteFile((HANDLE)(intptr_t)99, "x", 1, &w, 0)) ExitProcess(1);
    ExitProcess(0);
}
