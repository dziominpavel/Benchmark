@echo off
REM start.bat — запуск ELO Benchmark сервера в фоне
REM Запускает launch.vbs и сразу закрывается; сервер стартует без видимого окна.

cd /d "%~dp0"

if not exist logs\ mkdir logs

start "" wscript "%~dp0launch.vbs"
