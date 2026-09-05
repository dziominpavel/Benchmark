# data-storage Specification

## MODIFIED Requirements

### Requirement: Кэш — index.json

`index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, статус, ELO, games/wins/losses/draws), `tasks` (сводка), `matchups_index` (сводка вердиктов), `elo_history`. `elo_history` SHALL содержать одну запись на матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta). Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

#### Scenario: Структура index.json

- **WHEN** `index.json` сгенерирован
- **THEN** он содержит секции: `version`, `updated`, `matchups_digest`, `models`, `tasks`, `matchups_index`, `elo_history`
- **AND** `elo_history[0]` содержит `elo_a` и `elo_b`

#### Scenario: Просмотр без сервера

- **WHEN** пользователь открывает `index.json` в редакторе
- **THEN** видит текущий ELO всех моделей и статистику
- **AND** историю матчей в match-centric формате

### Requirement: Ключ задач в сводке (известный дефект)

`collect_tasks_info` SHALL сканировать директории `tasks/` (кроме `_`-префикса) и считать ответы из `answers/<task-id>/`, вердикты из `matchups/<task-id>/`. Идентификатор задачи SHALL извлекаться из имени директории как префикс `T-NNN` до первого дефиса, включая номер: `T-001-recurrence-bugs` → `T-001`.

#### Scenario: Сводка T-001 в MVP

- **WHEN** сгенерирован `index.json` при задаче `T-001-recurrence-bugs`
- **THEN** секция `tasks` содержит ключ `"T-001"` с корректными счётчиками ответов и вердиктов
- **AND** не создаётся ключа `"T"`

## ADDED Requirements

### Requirement: Миграция recorded_at

Код и/или отдельный скрипт SHALL уметь дополнять legacy-вердикты в `matchups/` полем `recorded_at` на основе `date` и `seq` перед пересчётом `index.json`.

#### Scenario: Миграция перед пересчётом

- **WHEN** `tools/elo.py` запущен после миграции
- **THEN** `index.json` содержит `recorded_at` для всех матчей
- **AND** `--check` проходит без предупреждений
