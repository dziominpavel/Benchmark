## Why

Сейчас история изменения ELO в `index.json` хранится как две отдельные записи на каждый матч — по одной на модель. В leaderboard это отображается двумя строками с похожим текстом, и у пользователя складывается ощущение, что в логе дубли. Кроме того, существующие файлы вердиктов `matchups/general/NNN.json` не содержат `recorded_at`, поэтому в истории отсутствует время, а `openspec`-спеки отстают от кода: `index.json` уже `version: 2`, но спеки описывают старую модель данных. Наконец, в проекте есть задокументированные, но не исправленные дефекты (ключ задачи `T` вместо `T-001`, архивные модели в рекомендациях, нумерация matchup `len+1` вместо `max+1`).

Пока нагрузка и объём данных малы, стоит переложить фундамент правильно: сделать историю матч-центричной, починить `recorded_at`, синхронизировать спеки с кодом и закрыть известные дефекты leaderboard.

## What Changes

- **BREAKING**: `elo_history` в `index.json` становится матч-центричной: одна запись на один вердикт с двумя блоками `elo_a` и `elo_b` (before/after/delta). Убирается двойная запись `model`/`opponent`.
- **BREAKING**: `tools/elo.py` генерирует `elo_history` в новом формате; `tools/test_elo.py` и UI-код рендерят одну строку на матч.
- Миграция существующих `matchups/general/*.json`: добавление `recorded_at` на основе `seq` (синтетическое, но монотонное), чтобы история содержала время и `--check` действительно проверял порядок.
- Исправление `recorded_at` как обязательного поля в `matchup-management` и `elo-engine`: `record_verdict.py` уже пишет его, теперь оно будет обязательным и в журнале, и в спеках.
- Синхронизация `openspec/specs/` с реальным форматом `index.json` (version = 2, `elo_history` match-centric).
- Исправление `collect_tasks_info`: извлечение корректного `task_id` из директорий вида `T-001-recurrence-bugs`.
- Исключение архивных моделей из pairing-рекомендаций и отдельная визуальная пометка archived в leaderboard.
- Исправление нумерации файлов `matchups/general/NNN.json` в `tools/server.py`: `max + 1` вместо `len + 1`.
- Унификация отображения истории в `tools/server.py` и `tools/generate_html.py`: одна строка на матч, оба ELO, обе дельты, дата и время.

## Capabilities

### New Capabilities

Новых capability не вводится — изменения вписываются в существующие.

### Modified Capabilities

- `elo-engine`: формат `elo_history` (одна запись на матч, `elo_a`/`elo_b`), обязательность `recorded_at`.
- `leaderboard-ui`: отображение истории одной строкой на матч, время, фильтр/пометка archived.
- `matchup-management`: `recorded_at` required, migration/backfill, `seq` как первичный порядок реплея.
- `data-storage`: `index.json` version = 2, `elo_history` как производная, роль `matchups_digest`.
- `pairing-algorithm`: исключать архивные модели из рекомендаций.
- `model-registry`: отображать статус archived в leaderboard.

## Impact

- `tools/elo.py`, `tools/test_elo.py` — изменение генерации `elo_history`.
- `tools/server.py`, `tools/generate_html.py` — рендер истории, рекомендаций, фильтр archived.
- `tools/archive_model.py` — регенерация index после смены статуса с учётом фильтра рекомендаций.
- `matchups/general/*.json` — миграция `recorded_at`.
- `index.json` — будет регенерирован в новом формате.
- `openspec/specs/*.md` — delta-спеки отражают изменения.
