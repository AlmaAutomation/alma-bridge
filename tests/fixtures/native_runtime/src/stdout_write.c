#include <stdint.h>
typedef void *HANDLE; typedef uint32_t DWORD; typedef int BOOL; typedef const void *LPCVOID; typedef void *LPVOID;
#define STD_OUTPUT_HANDLE ((DWORD)-11)
__attribute__((dllimport)) HANDLE __stdcall GetStdHandle(DWORD);
__attribute__((dllimport)) BOOL __stdcall WriteFile(HANDLE, LPCVOID, DWORD, DWORD *, LPVOID);
__attribute__((dllimport)) void __stdcall ExitProcess(DWORD);
void entry(void) {
    const char msg[] = "stdout payload\n";
    DWORD w=0; WriteFile(GetStdHandle(STD_OUTPUT_HANDLE), msg, sizeof(msg)-1, &w, 0);
    ExitProcess(0);
}
