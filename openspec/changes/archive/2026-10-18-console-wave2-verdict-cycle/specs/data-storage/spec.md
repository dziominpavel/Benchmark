## MODIFIED Requirements

### Requirement: Кэш — index.json

`data/index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, агент, дата регистрации `added`, статус, ELO, games/wins/losses/draws), `tasks` (сводка: `slug`, `title`, `matchups_count` без списка ответов), `matchups_summary` (счётчики событий журнала: `total`, `applied`, `voided`, `tombstone`, `skipped`), `elo_history`, `voided_history`. Секция-список `matchups_index` MUST NOT присутствовать (её роль выполняют агрегаты `matchups_summary` и полный журнал `data/matchups/journal.jsonl`). Поле `tasks.<id>.answers` MUST NOT присутствовать (авто-учёт ответов удалён, источник — `data/answer_flags.yaml`). `elo_history` SHALL содержать одну запись на применённый матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta); поле `after_matchup` MUST NOT присутствовать (дубликат `matchup`, никем не читается). `voided_history` SHALL содержать одну запись на аннулированный вердикт с полями `matchup`, `seq`, `task`, `model_a_id`, `model_b_id`, `winner`, `date`, `recorded_at`, `elo_a`/`elo_b` (снэпшот исходной записи) и `void` (причина, `date`, `recorded_at`, `matchup` tombstone-события); при отсутствии аннулированных вердиктов секция SHALL быть пустым списком. Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

#### Scenario: Структура index.json

- **WHEN** `data/index.json` сгенерирован
- **THEN** он содержит секции: `version`, `updated`, `matchups_digest`, `models`, `tasks`, `matchups_summary`, `elo_history`, `voided_history`
- **AND** каждая запись `models.<id>` содержит `added`, скопированный из `data/models.yaml` (пустая строка, если в реестре поля нет)
- **AND** каждая запись `models.<id>` содержит `agent` и `provider`, скопированные из `data/models.yaml` (пустая строка, если поле не задано)
- **AND** `elo_history[0]` содержит `elo_a` и `elo_b`
- **AND** секция `matchups_index` отсутствует
- **AND** `tasks.T-001` не содержит поля `answers`
- **AND** `matchups_summary` содержит `total`/`applied`/`voided`/`tombstone`/`skipped`
- **AND** `voided_history` присутствует (пустой список, если аннулированных нет)

#### Scenario: Просмотр без сервера

- **WHEN** пользователь открывает `data/index.json` в редакторе
- **THEN** видит текущий ELO всех моделей и статистику
- **AND** историю матчей в match-centric формате
