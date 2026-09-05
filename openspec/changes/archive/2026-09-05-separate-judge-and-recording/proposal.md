## Why

В `openspec/specs/benchmark-workflow/spec.md` сейчас записано, что skill судьи сам пишет `matchups/T-NNN/NNN.json` и запускает `python tools/elo.py`. В реальности `benchmark-judge` skill только сравнивает ответы, выбирает победителя и передаёт результат в `tools/record_verdict.py` — единую точку записи, которая разрешает слоты, пишет вердикт и пересчитывает ELO. Рассинхрон спеки и кода путает: кажется, будто судья «считает рейтинг» или имеет доступ к `slots.json` / реальным id моделей. Нужно привести документацию и спеки к фактическому разделению ролей.

## What Changes

- Исправить `benchmark-workflow` spec: судья (skill или ручной) SHALL только определять победителя; запись вердикта и пересчёт ELO SHALL выполняться `record_verdict.py` / веб-UI / CLI.
- Уточнить `matchup-management` spec: `record_verdict.py` — единственная точка записи; он разрешает слоты через `answers/<task>/slots.json` и сохраняет ELO-снэпшот (before/after/delta); судья НЕ читает `slots.json`.
- Дополнить `leaderboard-ui` spec: история на главной странице SHALL показывать соперника и ELO до/после для каждой записи, а не только дельту.
- Обновить `docs/workflow-guide.md` и `README.md`: убрать описание, по которому судья сам пишет в `matchups/` и запускает `elo.py`.

## Capabilities

### New Capabilities

(нет)

### Modified Capabilities

- `benchmark-workflow`: разделение шага «Судья» и шага «Запись вердикта + пересчёт ELO».
- `matchup-management`: уточнение единой точки записи и роли `slots.json`.
- `leaderboard-ui`: дополнение истории полями соперник и ELO before/after.

## Impact

- Текстовые артефакты `openspec/specs/benchmark-workflow/spec.md`, `openspec/specs/matchup-management/spec.md`, `openspec/specs/leaderboard-ui/spec.md`.
- Документация `docs/workflow-guide.md` и `README.md`.
- Код `tools/server.py` (история на UI) — изменения в `leaderboard-ui` spec.
- `tools/` (record_verdict.py, elo.py) поведение не меняется, спеки только приходят в соответствие с ним.
