## ADDED Requirements

### Requirement: Аннулированные вердикты в индексе

`generate_index` SHALL включать в `data/index.json` секцию `voided_history` — по одной записи на аннулированный вердикт: `matchup`, `seq`, `task`, `model_a_id`, `model_b_id`, `winner`, `date`, `recorded_at`, ELO-снэпшот исходной записи (`elo_a`, `elo_b`) и `void` (причина, дата и `recorded_at` tombstone-события, `matchup` tombstone-события). Записи SHALL упорядочиваться по возрастанию `seq` исходного вердикта. Секция SHALL NOT влиять на `elo_history`, рейтинг и счётчики `matchups_summary`.

#### Scenario: Аннулированный вердикт в индексе

- **WHEN** вердикт записан и затем аннулирован tombstone-событием с причиной
- **THEN** `data/index.json` содержит в `voided_history` запись этого вердикта с `void.reason` = указанная причина
- **AND** ELO пересчитан без аннулированной игры

#### Scenario: Разделение применённых и аннулированных

- **WHEN** журнал содержит применённые и аннулированные вердикты
- **THEN** `elo_history` содержит только применённые записи
- **AND** `voided_history` — только аннулированные
- **AND** `matchups_summary.voided` равен числу аннулированных вердиктов

#### Scenario: Пустая секция

- **WHEN** аннулированных вердиктов в журнале нет
- **THEN** `voided_history` — пустой список
