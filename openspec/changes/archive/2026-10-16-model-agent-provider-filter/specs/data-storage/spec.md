## MODIFIED Requirements

### Requirement: Кэш — index.json

`data/index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, агент, дата регистрации `added`, статус, ELO, games/wins/losses/draws), `tasks` (сводка: `slug`, `title`, `matchups_count` без списка ответов), `matchups_summary` (счётчики файлов журнала: `total`, `applied`, `voided`, `tombstone`, `skipped`), `elo_history`. Секция-список `matchups_index` MUST NOT присутствовать (её роль выполняют агрегаты `matchups_summary` и полные файлы журнала). Поле `tasks.<id>.answers` MUST NOT присутствовать (авто-учёт ответов удалён, источник — `data/answer_flags.yaml`). `elo_history` SHALL содержать одну запись на применённый матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta); поле `after_matchup` MUST NOT присутствовать (дубликат `matchup`, никем не читается). Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

#### Scenario: Структура index.json

- **WHEN** `data/index.json` сгенерирован
- **THEN** он содержит секции: `version`, `updated`, `matchups_digest`, `models`, `tasks`, `matchups_summary`, `elo_history`
- **AND** каждая запись `models.<id>` содержит `added`, скопированный из `data/models.yaml` (пустая строка, если в реестре поля нет)
- **AND** каждая запись `models.<id>` содержит `agent` и `provider`, скопированные из `data/models.yaml` (пустая строка, если поле не задано)
- **AND** `elo_history[0]` содержит `elo_a` и `elo_b`
- **AND** секция `matchups_index` отсутствует
- **AND** `tasks.T-001` не содержит поля `answers`
- **AND** `matchups_summary` содержит `total`/`applied`/`voided`/`tombstone`/`skipped`

#### Scenario: Просмотр без сервера

- **WHEN** пользователь открывает `data/index.json` в редакторе
- **THEN** видит текущий ELO всех моделей и статистику
- **AND** историю матчей в match-centric формате

### Requirement: Критерий устаревания кэша

`is_index_stale` SHALL считать кэш устаревшим если: `data/index.json` отсутствует
или не парсится; `matchups_digest` в кэше ≠ дайджесту текущего журнала (ловит любые правки, добавления и удаления файлов); множество id моделей в кэше ≠ множеству id в `data/models.yaml`; метаданные модели (`name`, `agent`, `provider`, `status`, `added`) в кэше ≠ реестру. Отдельной проверки числа записей НЕ существует — дайджест покрывает состав журнала полностью. Содержимое ответов, тексты задач и даты внутри вердиктов НЕ проверяются.

#### Scenario: Новый вердикт делает кэш устаревшим

- **WHEN** в `data/matchups/` появился файл, меняющий дайджест журнала
- **THEN** `is_index_stale` возвращает True

#### Scenario: Правка added делает кэш устаревшим

- **WHEN** в `data/models.yaml` изменён `added` модели
- **THEN** `is_index_stale` возвращает True
- **AND** следующий пересчёт копирует новое значение в `data/index.json`

#### Scenario: Правка agent или provider делает кэш устаревшим

- **WHEN** в `data/models.yaml` изменён `agent` или `provider` модели
- **THEN** `is_index_stale` возвращает True
- **AND** следующий пересчёт копирует новые значения в `data/index.json`

#### Scenario: Актуальный кэш

- **WHEN** сервер стартует и дайджест, множество id и метаданные моделей сошлись
- **THEN** сервер использует кэш без пересчёта (мгновенный старт)
