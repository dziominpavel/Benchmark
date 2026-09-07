@echo off
REM stop.bat — остановка ELO Benchmark сервера по PID из data/logs/server.pid

cd /d "%~dp0"

if not exist "data\logs\server.pid" (
    echo Сервер не запущен.
    exit /b 1
)

for /f "usebackq tokens=*" %%a in ("data\logs\server.pid") do set "PID=%%a"

taskkill /PID %PID% /T /F >nul 2>&1

if errorlevel 1 (
    echo Не удалось остановить сервер, PID=%PID%.
    exit /b 1
)

echo Сервер остановлен.
del "data\logs\server.pid"
