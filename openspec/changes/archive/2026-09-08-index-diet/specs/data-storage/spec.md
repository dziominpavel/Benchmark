## MODIFIED Requirements

### Requirement: Кэш — index.json

`data/index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, статус, ELO, games/wins/losses/draws), `tasks` (сводка), `matchups_summary` (счётчики файлов журнала: `total`, `applied`, `voided`, `tombstone`, `skipped`), `elo_history`. Секция-список `matchups_index` MUST NOT присутствовать (её роль выполняют агрегаты `matchups_summary` и полные файлы журнала). `elo_history` SHALL содержать одну запись на применённый матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta); поле `after_matchup` MUST NOT присутствовать (дубликат `matchup`, никем не читается). Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

#### Scenario: Структура index.json

- **WHEN** `data/index.json` сгенерирован
- **THEN** он содержит секции: `version`, `updated`, `matchups_digest`, `models`, `tasks`, `matchups_summary`, `elo_history`
- **AND** `elo_history[0]` содержит `elo_a` и `elo_b`
- **AND** секция `matchups_index` отсутствует
- **AND** `matchups_summary` содержит `total`/`applied`/`voided`/`tombstone`/`skipped`

#### Scenario: Просмотр без сервера

- **WHEN** пользователь открывает `data/index.json` в редакторе
- **THEN** видит текущий ELO всех моделей и статистику
- **AND** историю матчей в match-centric формате

### Requirement: Критерий устаревания кэша

`is_index_stale` SHALL считать кэш устаревшим если: `data/index.json` отсутствует
или не парсится; `matchups_digest` в кэше ≠ дайджесту текущего журнала (ловит любые правки, добавления и удаления файлов); множество id моделей в кэше ≠ множеству id в `data/models.yaml`; метаданные модели (`name`, `provider`, `status`) в кэше ≠ реестру. Отдельной проверки числа записей НЕ существует — дайджест покрывает состав журнала полностью. Содержимое ответов, тексты задач и даты внутри вердиктов НЕ проверяются.

#### Scenario: Новый вердикт делает кэш устаревшим

- **WHEN** в `data/matchups/` появился файл, меняющий дайджест журнала
- **THEN** `is_index_stale` возвращает True

#### Scenario: Актуальный кэш

- **WHEN** сервер стартует и дайджест, множество id и метаданные моделей сошлись
- **THEN** сервер использует кэш без пересчёта (мгновенный старт)

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
