# leaderboard-ui Specification

## MODIFIED Requirements

### Requirement: Локальный веб-сервер

Система SHALL запускаться командой `python tools/server.py` (или `start.bat`)
и слушать `http://localhost:<port>`. При занятом порту 5000 система SHALL
выбрать следующий свободный (5001, 5002, … до 10 попыток) через `find_free_port`
и вывести фактический URL. `start.bat` запускает сервер в фоновом режиме,
перенаправляет вывод в `logs/server.log`, и через 2 секунды открывает
фиксированный `http://localhost:5000` в браузере. Собственное консольное окно
`start.bat` не остаётся видимым.

#### Scenario: Запуск сервера

- **WHEN** пользователь выполняет `python tools/server.py`
- **THEN** сервер слушает 127.0.0.1 на свободном порту от 5000
- **AND** выводит URL вида `http://localhost:5000`

#### Scenario: Запуск через start.bat

- **WHEN** пользователь выполняет `start.bat`
- **THEN** сервер запускается в фоновом режиме без видимого консольного окна
- **AND** вывод сервера пишется в `logs/server.log`
- **AND** через 2 секунды автоматически открывается `http://localhost:5000` в браузере

## ADDED Requirements

### Requirement: Остановка сервера

Система SHALL предоставлять команду `stop.bat` для остановки запущенного
локального сервера leaderboard.

#### Scenario: Остановка через stop.bat

- **WHEN** пользователь выполняет `stop.bat`
- **THEN** процесс, запущенный `python tools/server.py`, MUST быть завершён
- **AND** сервер перестаёт слушать порт
