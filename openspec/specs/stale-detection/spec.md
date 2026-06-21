## Purpose

Проверка актуальности задач по `baseline_commit` vs HEAD проекта.
`tools/check_stale.py` обнаруживает устаревшие задачи и сигнализирует
пользователю. Прогоны на устаревших задачах остаются валидными.

## Requirements

### Requirement: Проверка устаревания задачи

`tools/check_stale.py` MUST проверять `baseline_commit` каждой задачи vs HEAD
соответствующего проекта. Если коммитов с baseline > порог (по умолчанию 10),
задача помечается `stale`. Скрипт не удаляет задачу, не делает прогоны
невалидными — сигнализирует пользователю.

#### Scenario: Задача актуальна

- **WHEN** `check_stale.py` проверяет задачу F-001 с `baseline_commit: abc123`
- **AND** HEAD проекта VoiceMind = `abc123` (0 коммитов с baseline)
- **THEN** задача помечается `fresh`

#### Scenario: Задача устарела

- **WHEN** `check_stale.py` проверяет задачу F-001 с `baseline_commit: abc123`
- **AND** HEAD проекта VoiceMind = `xyz789` (15 коммитов с baseline)
- **THEN** задача помечается `stale: 15 commits behind`
- **AND** пользователь получает рекомендацию создать новую задачу

#### Scenario: Проект не найден

- **WHEN** `check_stale.py` проверяет задачу с `project: voicemind`
- **AND** папка `C:/projects/VoiceMind` не существует
- **THEN** задача помечается `error: project not found`

### Requirement: Порог устаревания

`check_stale.py` MUST поддерживать `--threshold <N>` для настройки порога
коммитов. По умолчанию 10. Пользователь MAY изменить порог.

#### Scenario: Кастомный порог

- **WHEN** `check_stale.py --threshold 5` запущен
- **AND** задача имеет 7 коммитов с baseline
- **THEN** задача помечается `stale: 7 commits behind (threshold: 5)`

### Requirement: Отчёт об устаревании

`check_stale.py` MUST выводить таблицу: Задача | Проект | Коммитов с baseline |
Статус. Также MAY сохранять отчёт в `stale-report.md` через `--output`.

#### Scenario: Отчёт в консоли

- **WHEN** `check_stale.py` запущен
- **THEN** выводится таблица всех задач с их статусом
- **AND** устаревшие задачи помечены `⚠ stale`

#### Scenario: Отчёт в файл

- **WHEN** `check_stale.py --output stale-report.md` запущен
- **THEN** отчёт сохраняется в `stale-report.md`
- **AND** содержит таблицу и рекомендации

### Requirement: Прогоны на устаревшей задаче валидны

Устаревшая задача MUST NOT делать существующие прогоны невалидными. Прогоны
на `baseline_commit` всё ещё сравнимы между моделями (все на одном commit).
`stale` — сигнал для пользователя, не блокировка.

#### Scenario: Прогоны сохраняются

- **WHEN** задача F-001 помечена `stale`
- **AND** существуют прогоны 5 моделей на F-001
- **THEN** прогоны остаются в `runs/F-001-*/`
- **AND** `aggregate.py` включает их в leaderboard
- **AND** сравнение между моделями честное (все на одном commit)

### Requirement: baseline_commit в front matter

`check_stale.py` MUST читать `baseline_commit` и `project` из front matter
каждой задачи в `tasks/<cat>/<id>/task.md`. Если поле отсутствует — задача
помечается `error: no baseline_commit`.

#### Scenario: Нет baseline_commit

- **WHEN** `check_stale.py` проверяет задачу без `baseline_commit` в front matter
- **THEN** задача помечается `error: no baseline_commit`
- **AND** пользователь получает рекомендацию добавить поле

### Requirement: Только stdlib Python

`check_stale.py` MUST использовать только стандартную библиотеку Python
(вызывает git через subprocess). Никаких внешних зависимостей.

#### Scenario: Запуск без зависимостей

- **WHEN** `python tools/check_stale.py` запущен
- **THEN** скрипт выполняется без установки внешних пакетов
