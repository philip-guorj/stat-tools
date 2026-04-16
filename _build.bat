@echo off
taskkill /F /PID 58628 2>nul
"C:\Program Files\Python311\python.exe" -m PyInstaller "D:\stat-tools\stattools.spec" --noconfirm
echo.
echo === BUILD FINISHED ===
if exist "D:\stat-tools\dist\StatTools\StatTools.exe" (
    for %%A in ("D:\stat-tools\dist\StatTools\StatTools.exe") do echo FILE: %%~fA  SIZE: %%~zA bytes
) else (
    echo StatTools.exe NOT FOUND
)
pause
