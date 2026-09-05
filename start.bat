@echo off
REM start.bat - запуск ELO Benchmark сервера
REM Открывает http://localhost:5000 в браузере и стартует Flask-сервер

cd /d "%~dp0"

echo === ELO Benchmark ===
echo Запуск сервера на http://localhost:5000 ...
echo.

REM Открываем браузер через 2 секунды (даём серверу стартовать)
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:5000"

REM Запускаем сервер (блокирует консоль до Ctrl+C)
python tools/server.py

echo.
echo Сервер остановлен. Нажмите любую клавишу для выхода.
pause >nul
