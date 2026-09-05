## Purpose

Гибридное хранение данных бенчмарка. Файлы (source of truth, коммитятся в git) + index.json (генерируемый кэш для быстрого поиска и просмотра без сервера).

## ADDED Requirements

### Requirement: Source of truth — файлы

Исходные данные хранятся в файлах: models.yaml (модели), tasks/T-NNN/task.md (задачи), answers/T-NNN/model.md (ответы), matchups/T-NNN/NNN.json (вердикты). Эти файлы коммитятся в git.

#### Scenario: Git diff вердикта

- **WHEN** записывается новый вердикт
- **THEN** git diff показывает добавленный файл matchups/T-NNN/NNN.json
- **AND** дифф содержит только содержимое этого файла

#### Scenario: Git diff ответа

- **WHEN** модель пишет ответ
- **THEN** git diff показывает добавленный файл answers/T-NNN/model.md
- **AND** содержимое читаемо (Markdown)

### Requirement: Кэш — index.json

index.json — генерируемый файл, содержащий: текущий ELO всех моделей, статистику W/L/D/games, сводку задач, индекс вердиктов, историю ELO. Коммитится в git для просмотра без сервера.

#### Scenario: Структура index.json

- **WHEN** index.json сгенерирован
- **THEN** он содержит секции: version, updated, models (с ELO и статистикой), tasks (с количеством ответов и вердиктов), matchups_index (сводка), elo_history

#### Scenario: Просмотр без сервера

- **WHEN** пользователь открывает index.json в редакторе (без запуска сервера)
- **THEN** видит текущий ELO всех моделей и статистику

### Requirement: Обновление index.json

index.json обновляется при: записи вердикта, архивации модели, регистрации модели. Обновление = пересчёт ELO из всех вердиктов + обновление сводок.

#### Scenario: Запись вердикта обновляет кэш

- **WHEN** через веб-UI записан вердикт
- **THEN** index.json перезаписывается с обновлённым ELO
- **AND** updated timestamp обновляется

### Requirement: Восстановление кэша

При запуске сервер проверяет целостность index.json vs файлы. Если index.json устарел (новые файлы в matchups/ или answers/, не отражённые в кэше) — пересчитывает.

#### Scenario: Устаревший кэш

- **WHEN** сервер запускается, в matchups/ есть файлы, не отражённые в index.json
- **THEN** сервер пересчитывает ELO из всех вердиктов
- **AND** перезаписывает index.json

#### Scenario: Актуальный кэш

- **WHEN** сервер запускается, index.json актуален
- **THEN** сервер использует кэш без пересчёта (мгновенный старт)

### Requirement: Масштаб хранилища

Хранилище рассчитано на: 1–10 задач, 5–30 моделей, 10–500 вердиктов. index.json — до ~50 KB. Ответы — до ~50 KB каждый.

#### Scenario: Типичный объём

- **WHEN** 3 задачи, 10 моделей, 100 вердиктов
- **THEN** index.json ~10 KB
- **AND** answers/ ~30 файлов × 20 KB = ~600 KB
- **AND** matchups/ ~100 файлов × 200 байт = ~20 KB

### Requirement: .gitignore

В .gitignore исключаются: __pycache__/, *.pyc, .DS_Store, Thumbs.db. index.json НЕ в .gitignore (коммитится).

#### Scenario: Проверка .gitignore

- **WHEN** выполняется git status
- **THEN** index.json виден (не игнорируется)
- **AND** __pycache__/ игнорируется
