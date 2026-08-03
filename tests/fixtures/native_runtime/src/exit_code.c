#include <stdint.h>
__attribute__((dllimport)) void __stdcall ExitProcess(uint32_t);
void entry(void) { ExitProcess(42); }
