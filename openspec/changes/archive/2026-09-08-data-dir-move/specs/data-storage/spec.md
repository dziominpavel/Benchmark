## ADDED Requirements

### Requirement: Корень данных — data/
Все файлы данных SHALL храниться под директорией `data/` в корне репозитория: `data/models.yaml`, `data/judges.yaml`, `data/settings.yaml`, `data/index.json`, `data/tasks/`, `data/answers/`, `data/matchups/` (включая `data/matchups/state.json`), `data/logs/`. Код SHALL находиться в `tools/`, лаунчеры (`start.bat`, `stop.bat`, `launch.vbs`) — в корне. Файлы данных вне `data/` MUST NOT использоваться.

#### Scenario: Структура корня
- **WHEN** пользователь открывает корень репозитория
- **THEN** все данные прогонов находятся в `data/`
- **AND** в корне нет `tasks/`, `answers/`, `matchups/`, `models.yaml`, `settings.yaml`, `index.json`

## MODIFIED Requirements

### Requirement: Source of truth — файлы
Исходные данные SHALL храниться в файлах: `data/models.yaml` (реестр), `data/tasks/T-NNN-<slug>/task.md` (задачи), `data/answers/T-NNN/*.md` (ответы: `modelA.md` / `modelB.md` от skills либо `<model-id>.md` вручную), `data/matchups/T-NNN/NNN.json` (вердикты), `data/settings.yaml` (настройки: статусы тасок и текущая таска). `data/matchups/general/` и `data/matchups/<non-T-NNN>/` MUST NOT использоваться. `data/answers/<task>/slots.json` MUST NOT использоваться. Эти файлы SHALL коммититься в git.

#### Scenario: Git diff ответа
- **WHEN** модель пишет ответ
- **THEN** git diff показывает добавленный Markdown-файл в `data/answers/T-NNN/`
- **AND** не создаётся `data/answers/T-NNN/slots.json`

#### Scenario: Git diff вердикта
- **WHEN** записывается новый вердикт
- **THEN** git diff показывает один добавленный JSON-файл в `data/matchups/T-001/`
- **AND** `data/matchups/general/` не появляется

#### Scenario: Git diff настроек
- **WHEN** пользователь сохраняет настройки через `/settings`
- **THEN** git diff показывает изменённый `data/settings.yaml`
- **AND** в нём нет ключа `general`

### Requirement: Кэш — index.json

`data/index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, статус, ELO, games/wins/losses/draws), `tasks` (сводка), `matchups_index` (сводка вердиктов), `elo_history`. `elo_history` SHALL содержать одну запись на матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta). Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

#### Scenario: Структура index.json

- **WHEN** `data/index.json` сгенерирован
- **THEN** он содержит секции: `version`, `updated`, `matchups_digest`, `models`, `tasks`, `matchups_index`, `elo_history`
- **AND** `elo_history[0]` содержит `elo_a` и `elo_b`

#### Scenario: Просмотр без сервера

- **WHEN** пользователь открывает `data/index.json` в редакторе
- **THEN** видит текущий ELO всех моделей и статистику
- **AND** историю матчей в match-centric формате

### Requirement: Обновление index.json

`data/index.json` SHALL пересчитываться при: записи вердикта через веб-UI,
добавлении модели через веб-UI, ручном запуске `python tools/elo.py`.
CLI-скрипты `register_model.py` / `archive_model.py` MUST NOT переписывать
`data/index.json` сами — свежесть восстанавливается лениво: `ensure_index` сервера
сверяет кэш через `is_index_stale` и пересчитывает при расхождении.

#### Scenario: Запись вердикта обновляет кэш

- **WHEN** через веб-UI записан вердикт
- **THEN** `data/index.json` перезаписывается с обновлённым ELO
- **AND** поле `updated` обновляется на сегодня

#### Scenario: Ленивое восстановление после CLI

- **WHEN** модель зарегистрирована через CLI и сервер стартует со старым кэшем
- **THEN** `ensure_index` обнаруживает расхождение набора моделей и пересчитывает кэш

### Requirement: Критерий устаревания кэша

`is_index_stale` SHALL считать кэш устаревшим если: `data/index.json` отсутствует
или не парсится; число записей `matchups_index` ≠ числу JSON-файлов в
`data/matchups/`; множество id моделей в кэше ≠ множеству id в `data/models.yaml`.
Содержимое ответов, тексты задач и даты внутри вердиктов НЕ проверяются.

#### Scenario: Новый вердикт делает кэш устаревшим

- **WHEN** в `data/matchups/` появился файл, не отражённый в `matchups_index`
- **THEN** `is_index_stale` возвращает True

#### Scenario: Актуальный кэш

- **WHEN** сервер стартует и все три проверки сошлись
- **THEN** сервер использует кэш без пересчёта (мгновенный старт)

### Requirement: Ключ задач в сводке (известный дефект)

`collect_tasks_info` SHALL сканировать директории `data/tasks/` (кроме `_`-префикса) и считать ответы из `data/answers/<task-id>/`, вердикты из `data/matchups/<task-id>/`. Идентификатор задачи SHALL извлекаться из имени директории как префикс `T-NNN` до первого дефиса, включая номер: `T-001-recurrence-bugs` → `T-001`.

#### Scenario: Сводка T-001 в MVP
- **WHEN** сгенерирован `data/index.json` при задаче `T-001-recurrence-bugs`
- **THEN** секция `tasks` содержит ключ `"T-001"` с корректными счётчиками ответов и вердиктов
- **AND** не создаётся ключа `"T"`

### Requirement: .gitignore

`.gitignore` SHALL исключать: `__pycache__/`, `*.pyc`, окружения, IDE-кэши,
ОС-мусор, `data/logs/*.pid`. `data/index.json` MUST NOT игнорироваться (коммитится). Статичный
`leaderboard.html` более не генерируется, поэтому `.gitignore` не SHALL
содержать специальных правил для него.

#### Scenario: Проверка .gitignore

- **WHEN** выполняется `git status`
- **THEN** `data/index.json` виден (не игнорируется)
- **AND** `__pycache__/` игнорируется
- **AND** `leaderboard.html` не упоминается в `.gitignore`

### Requirement: Масштаб хранилища

Хранилище рассчитано на: 1–10 задач, 5–30 моделей, 10–500 вердиктов.
`data/index.json` — до ~50 KB; ответы — до ~50 KB каждый. Полный пересчёт при
500 вердиктах занимает <100ms (один проход, только stdlib).

#### Scenario: Типичный объём

- **WHEN** 3 задачи, 10 моделей, 100 вердиктов
- **THEN** `data/index.json` ~10 KB
- **AND** `data/answers/` ~30 файлов, `data/matchups/` ~100 файлов по ~200 байт

### Requirement: Миграция recorded_at

Код и/или отдельный скрипт SHALL уметь дополнять legacy-вердикты в `data/matchups/` полем `recorded_at` на основе `date` и `seq` перед пересчётом `data/index.json`.

#### Scenario: Миграция перед пересчётом
- **WHEN** `tools/elo.py` запущен после миграции
- **THEN** `data/index.json` содержит `recorded_at` для всех матчей
- **AND** `--check` проходит без предупреждений

### Requirement: Файл настроек settings.yaml
`data/settings.yaml` SHALL хранить: `current_task` (id активной таски, подставляемой в форму вердикта) и `tasks` — отображение `id таски -> status` (`active` | `inactive`). Файл SHALL коммититься в git и MAY редактироваться вручную. При отсутствии файла SHALL применяться дефолты: активные таски — все `T-NNN`, обнаруженные в `data/tasks/` и `data/matchups/T-NNN/`; `current_task` — первая активная таска (лексикографически). При отсутствии `tasks`-записи для обнаруженной `T-NNN` таски она SHALL считаться активной. `general` не является допустимым значением `current_task` или ключа `tasks`.

#### Scenario: Сохранение настроек
- **WHEN** на странице `/settings` отмечены `T-001` и `T-002` как активные, текущая — `T-001`
- **THEN** `data/settings.yaml` содержит `current_task: T-001` и `tasks` со статусами `T-001: active`, `T-002: active`
- **AND** ключа `general` в файле нет

#### Scenario: Отсутствующий файл
- **WHEN** `data/settings.yaml` не существует, но есть `data/tasks/T-001-<slug>/task.md`
- **THEN** сервер работает с дефолтами: `T-001` активна, `current_task` = `T-001`
- **AND** `general` не добавляется

#### Scenario: Новая таска без записи
- **WHEN** в `data/matchups/T-002/` появился новый вердикт, отсутствующий в `data/settings.yaml`
- **THEN** `T-002` считается активной до явной отметки

### Requirement: Миграция корзины general
Система SHALL предоставлять одноразовый скрипт/шаг миграции, который переносит файлы из `data/matchups/general/` в `data/matchups/T-001/` и переписывает в них поле `task` с `general` на `T-001`. После миграции директория `data/matchups/general/` MUST быть пустой/удалённой, а `data/settings.yaml` не SHALL содержать `general`.

#### Scenario: Миграция
- **WHEN** запущен скрипт миграции
- **THEN** все файлы `data/matchups/general/NNN.json` перемещены в `data/matchups/T-001/NNN.json`
- **AND** поле `task` в каждом файле равно `T-001`
- **AND** `data/index.json` пересчитывается
- **AND** `data/settings.yaml` содержит `current_task: T-001` и `T-001: active`
