# data-storage Specification

## Purpose
Гибридное хранение MVP: файлы — source of truth (коммитятся в git),
`index.json` — генерируемый кэш для просмотра рейтинга без сервера.

## Requirements

### Requirement: Корень данных — data/
Все файлы данных SHALL храниться под директорией `data/` в корне репозитория: `data/models.yaml`, `data/judges.yaml`, `data/settings.yaml`, `data/answer_flags.yaml`, `data/index.json`, `data/tasks/`, `data/answers/`, `data/matchups/` (включая `data/matchups/state.json`), `data/logs/`. Код SHALL находиться в `tools/`, лаунчеры (`start.bat`, `stop.bat`, `launch.vbs`) — в корне. Файлы данных вне `data/` MUST NOT использоваться.

#### Scenario: Структура корня
- **WHEN** пользователь открывает корень репозитория
- **THEN** все данные прогонов находятся в `data/`
- **AND** в корне нет `tasks/`, `answers/`, `matchups/`, `models.yaml`, `settings.yaml`, `index.json`

### Requirement: Source of truth — файлы
Исходные данные SHALL храниться в файлах: `data/models.yaml` (реестр), `data/tasks/T-NNN-<slug>/task.md` (задачи), `data/answers/T-NNN/modelA.md` / `modelB.md` (только два транзитных слота текущего судейства), `data/matchups/T-NNN/NNN.json` (вердикты), `data/settings.yaml` (настройки: статусы тасок и текущая таска), `data/answer_flags.yaml` (ручной учёт наличия ответов, см. `answer-coverage`). Файлы `data/answers/<task>/<model-id>.md` в проекте MUST NOT использоваться (тексты ответов хранятся вне проекта). `data/matchups/general/` и `data/matchups/<non-T-NNN>/` MUST NOT использоваться. `data/answers/<task>/slots.json` MUST NOT использоваться. Эти файлы SHALL коммититься в git.

#### Scenario: Git diff ответа
- **WHEN** модель пишет ответ
- **THEN** git diff показывает изменённый Markdown-файл `data/answers/T-NNN/modelA.md` или `modelB.md`
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

`data/index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, статус, ELO, games/wins/losses/draws), `tasks` (сводка: `slug`, `title`, `matchups_count` без списка ответов), `matchups_summary` (счётчики файлов журнала: `total`, `applied`, `voided`, `tombstone`, `skipped`), `elo_history`. Секция-список `matchups_index` MUST NOT присутствовать (её роль выполняют агрегаты `matchups_summary` и полные файлы журнала). Поле `tasks.<id>.answers` MUST NOT присутствовать (авто-учёт ответов удалён, источник — `data/answer_flags.yaml`). `elo_history` SHALL содержать одну запись на применённый матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta); поле `after_matchup` MUST NOT присутствовать (дубликат `matchup`, никем не читается). Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

#### Scenario: Структура index.json

- **WHEN** `data/index.json` сгенерирован
- **THEN** он содержит секции: `version`, `updated`, `matchups_digest`, `models`, `tasks`, `matchups_summary`, `elo_history`
- **AND** `elo_history[0]` содержит `elo_a` и `elo_b`
- **AND** секция `matchups_index` отсутствует
- **AND** `tasks.T-001` не содержит поля `answers`
- **AND** `matchups_summary` содержит `total`/`applied`/`voided`/`tombstone`/`skipped`

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
или не парсится; `matchups_digest` в кэше ≠ дайджесту текущего журнала (ловит любые правки, добавления и удаления файлов); множество id моделей в кэше ≠ множеству id в `data/models.yaml`; метаданные модели (`name`, `provider`, `status`) в кэше ≠ реестру. Отдельной проверки числа записей НЕ существует — дайджест покрывает состав журнала полностью. Содержимое ответов, тексты задач и даты внутри вердиктов НЕ проверяются.

#### Scenario: Новый вердикт делает кэш устаревшим

- **WHEN** в `data/matchups/` появился файл, меняющий дайджест журнала
- **THEN** `is_index_stale` возвращает True

#### Scenario: Актуальный кэш

- **WHEN** сервер стартует и дайджест, множество id и метаданные моделей сошлись
- **THEN** сервер использует кэш без пересчёта (мгновенный старт)

### Requirement: Ключ задач в сводке (известный дефект)

`collect_tasks_info` SHALL сканировать директории `data/tasks/` (кроме `_`-префикса) и считать вердикты из `data/matchups/<task-id>/`. Сканирование `data/answers/<task-id>/` для сводки MUST NOT выполняться. Идентификатор задачи SHALL извлекаться из имени директории как префикс `T-NNN` до первого дефиса, включая номер: `T-001-recurrence-bugs` → `T-001`.

#### Scenario: Сводка T-001 в MVP
- **WHEN** сгенерирован `data/index.json` при задаче `T-001-recurrence-bugs`
- **THEN** секция `tasks` содержит ключ `"T-001"` с корректным счётчиком вердиктов
- **AND** не создаётся ключа `"T"`
- **AND** не создаётся поля `answers`

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
Маржинальная стоимость вердикта в кэше — ~0.31 КБ (одна запись `elo_history`;
агрегат `matchups_summary` от числа вердиктов не растёт). Замер: ~44 КБ при
88 вердиктах; прогноз на 500 вердиктов — ~170 КБ. Ответы — до ~50 KB каждый.
Полный пересчёт при 500 вердиктах занимает <100ms (один проход, только stdlib).

#### Scenario: Типичный объём

- **WHEN** 3 задачи, 10 моделей, 100 вердиктов
- **THEN** `data/index.json` ~48 КБ
- **AND** `data/answers/` ~30 файлов, `data/matchups/` ~100 файлов

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
