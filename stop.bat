@echo off
REM stop.bat — остановка ELO Benchmark сервера (логика в stop.vbs)

cd /d "%~dp0"
cscript //nologo "%~dp0stop.vbs" >nul 2>&1
if errorlevel 1 (
    echo Сервер не запущен.
    exit /b 1
)
echo Сервер остановлен.
exit /b 0
