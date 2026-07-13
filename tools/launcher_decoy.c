/*
 * launcher_decoy.c
 *
 * Tiny Win32 process that sleeps forever. Installed as
 * resources/alma-guard/<LauncherName>.exe so the Ascension client-services
 * launcher_guard sees a process whose *filename* matches the Electron launcher.
 *
 * Build:
 *   x86_64-w64-mingw32-gcc -municode -O2 -s -o "Ascension Launcher.exe" launcher_decoy.c
 */
#include <windows.h>

int wmain(int argc, wchar_t **argv)
{
    (void)argc;
    (void)argv;
    for (;;)
        Sleep(60000);
    return 0;
}
