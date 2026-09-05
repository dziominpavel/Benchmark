# elo-engine Specification

## MODIFIED Requirements

### Requirement: История изменений ELO

Система SHALL сохранять **одну** запись истории на каждый применённый вердикт. Запись содержит идентификатор матча (`matchup` и `after_matchup`), глобальный `seq`, `date`, `recorded_at`, идентификаторы обеих моделей (`model_a_id`, `model_b_id`), победителя (`winner`) и ELO-снэпшоты обеих сторон (`elo_a`, `elo_b`), каждый с полями `before`, `after`, `delta`. Записи истории моделей (`model`, `opponent`) SHALL NOT генерироваться в `elo_history`.

#### Scenario: Запись истории

- **WHEN** вердикт `general/001` обновляет ELO модели A с 1200 до 1220, а модели B с 1200 до 1180
- **THEN** в `elo_history` добавляется одна запись `{matchup: "general/001", model_a_id: "A", model_b_id: "B", winner: "a", elo_a: {before: 1200, after: 1220, delta: 20}, elo_b: {before: 1200, after: 1180, delta: -20}}`
- **AND** поля `seq`, `date`, `recorded_at` сохраняются из вердикта
- **AND** не создаётся отдельная запись для модели B

#### Scenario: Проверка монотонности recorded_at

- **WHEN** `recorded_at` вердикта `seq=3` раньше `recorded_at` вердикта `seq=2`
- **THEN** `--check` сообщает об ошибке

#### Scenario: Проверка recorded_at на наличие

- **WHEN** вердикт не содержит `recorded_at`
- **THEN** `--check` сообщает об ошибке

## ADDED Requirements

### Requirement: Миграция legacy-вердиктов

Для вердиктов, записанных до введения обязательного `recorded_at`, система MAY проставить синтетическое `recorded_at` на основе `date` и `seq` при миграции, чтобы сохранить монотонность. Новые вердикты MUST получать реальное системное время.

#### Scenario: Бэкфилл recorded_at

- **WHEN** `tools/migrate_recorded_at.py` обрабатывает вердикт с `seq=2` и `date=2026-09-05` без `recorded_at`
- **THEN** файл дополняется `recorded_at: "2026-09-05T00:00:04+00:00"`
- **AND** при следующем `elo.py --check` ошибок не возникает
