@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1" %*
set "QUANT_EXIT=%ERRORLEVEL%"
if not "%QUANT_EXIT%"=="0" echo Update failed. See the log path above. Existing reports were preserved.
pause
exit /b %QUANT_EXIT%
