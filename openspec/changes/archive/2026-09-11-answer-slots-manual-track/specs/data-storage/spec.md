## MODIFIED Requirements

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

`data/index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, статус, ELO, games/wins/losses/draws), `tasks` (сводка: `slug`, `title`, `matchups_count` без списка ответов), `matchups_summary` (счётчики файлов журнала: `total`, `applied`, `voided`, `tombstone`, `skipped`), `elo_history`. Секция-список `matchups_index` MUST NOT присутствовать. Поле `tasks.<id>.answers` MUST NOT присутствовать (авто-учёт ответов удалён, источник — `data/answer_flags.yaml`). `elo_history` SHALL содержать одну запись на применённый матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta); поле `after_matchup` MUST NOT присутствовать. Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

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

### Requirement: Ключ задач в сводке (известный дефект)

`collect_tasks_info` SHALL сканировать директории `data/tasks/` (кроме `_`-префикса) и считать вердикты из `data/matchups/<task-id>/`. Сканирование `data/answers/<task-id>/` для сводки MUST NOT выполняться. Идентификатор задачи SHALL извлекаться из имени директории как префикс `T-NNN` до первого дефиса, включая номер: `T-001-recurrence-bugs` → `T-001`.

#### Scenario: Сводка T-001 в MVP

- **WHEN** сгенерирован `data/index.json` при задаче `T-001-recurrence-bugs`
- **THEN** секция `tasks` содержит ключ `"T-001"` с корректным счётчиком вердиктов
- **AND** не создаётся ключа `"T"`
- **AND** не создаётся поля `answers`
