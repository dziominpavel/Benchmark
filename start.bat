@echo off
REM start.bat — запуск ELO Benchmark сервера в фоне
REM Запускает launch.vbs и сразу закрывается; сервер стартует без видимого окна.

cd /d "%~dp0"

if not exist data\logs\ mkdir data\logs

REM Первый запуск на чистой копии репо: создаём .venv с зависимостями (uv sync)
if not exist .venv\Scripts\python.exe (
    echo Создаю окружение .venv через uv sync...
    uv sync
    if errorlevel 1 (
        echo Ошибка: не удалось создать окружение. Проверьте, что uv установлен и в PATH.
        exit /b 1
    )
)

start "" wscript "%~dp0launch.vbs"
