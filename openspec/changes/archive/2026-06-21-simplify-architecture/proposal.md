## Why

Текущая архитектура (wave-based) требует ~184 сессий на прогон из-за поквартального перезапуска всех моделей, git-тегов в чужих проектах, снапшотов и 8 задач × 2 генераторов. Это нереалистично для одного человека. Нужна упрощённая архитектура: задача = самодостаточная единица с `baseline_commit` в front master, батч-выполнение и батч-оценка по умолчанию, инкрементальное добавление новых моделей (4 сессии), кумулятивный leaderboard. Цель: базовый прогон за 13 сессий, инкремент за 4-5.

## What Changes

- **BREAKING**: Убрать концепцию wave/generation. Задача = самодостаточная единица с `baseline_commit` в front matter. Участник делает `git checkout <commit>` вместо `git checkout <tag>`.
- **BREAKING**: Убрать `snapshots/` — нет снапшотов, нет git-тегов в проектах. Commit hash живёт в `task.md`.
- **BREAKING**: Убрать `waves/` — нет participants.yaml/judges.yaml/anonymization.yaml на волну. `judges.yaml` — глобальный pool судей. `models.yaml` — глобальный реестр (без изменений).
- **BREAKING**: Структура папок `runs/<wave>/<model>/<task>/` → `runs/<task-id>/<model>/`. Аналогично `verdicts/<wave>/` → `verdicts/<task-id>/`.
- **BREAKING**: Батч-выполнение по умолчанию — 1 сессия участника = все задачи (а не 1 задача = 1 сессия).
- **BREAKING**: Батч-оценка по умолчанию — 1 сессия судьи = все участники × все задачи (или батч по 2-3 участника).
- **BREAKING**: Golden answer только для bugfix, опционально. Для feature/refactor/review — нет golden.
- **BREAKING**: Leaderboard кумулятивный — не перегенерируется, а обновляется при добавлении новых прогонов/вердиктов.
- **NEW**: `tools/check_stale.py` — проверяет `baseline_commit` задачи vs HEAD проекта. Помечает устаревшие задачи.
- **NEW**: `tools/generate_checklist.py` — генерирует markdown-файлы с готовыми промптами для копипаста в чат.
- **NEW**: `assign_judges.py --add-runs` — инкрементальное назначение судей для новых прогонов (не перераспределяет существующие).
- **MODIFIED**: `isolate.py` — `--task` вместо `--wave`. Изоляция по задаче, не по волне.
- **MODIFIED**: `aggregate.py` — кумулятивный режим, без группировки по волнам. Разбивка по категориям и задачам.
- Убрать capability `wave-snapshot` (нет волн).
- Упростить `task-resolution` (golden только для bugfix).
- Переписать `task-execution`, `judging`, `leaderboard`, `task-generation` под новую архитектуру.

## Capabilities

### New Capabilities

- `stale-detection`: Проверка актуальности задач по `baseline_commit` vs HEAD проекта. Помечает устаревшие задачи.

### Modified Capabilities

- `task-generation`: Задача = самодостаточная единица с `baseline_commit`. Генератор определяет commit из текущего HEAD проекта. 1 генератор на базовый прогон (не 2). Батч-генерация: 1 сессия = все задачи.
- `task-resolution`: Golden answer только для bugfix. Для feature/refactor/review — нет golden. Опционально.
- `task-execution`: Батч-выполнение по умолчанию (1 сессия = все задачи участника). `git checkout <baseline_commit>` вместо тега. Структура `runs/<task-id>/<model>/`. Изоляция по задаче.
- `judging`: Батч-оценка по умолчанию (1 сессия судьи = 2-3 участника × все задачи). Глобальный pool судей (`judges.yaml`). Инкрементальное назначение (`--add-runs`). Структура `verdicts/<task-id>/<model>/`.
- `leaderboard`: Кумулятивный режим. Не перегенерируется, обновляется. Разбивка по категориям и задачам (не по волнам). Качество судей и карта назначений остаются.
- `meta-analysis`: Без изменений по существу, но анализ по задачам (не по волнам).

### Removed Capabilities

- `wave-snapshot`: Убирается полностью. Нет волн, снапшотов, git-тегов, participants.yaml на волну.

## Impact

- **Удаляемые папки**: `snapshots/`, `waves/` (включая `_TEMPLATES/`).
- **Миграция**: `runs/wave-01-2026Q3/` → `runs/<task-id>/<model>/`. `verdicts/wave-01-2026Q3/` → `verdicts/<task-id>/<model>/`.
- **Скрипты**: `isolate.py`, `assign_judges.py`, `aggregate.py` — переписать. `register_model.py` — без изменений. `check_stale.py`, `generate_checklist.py` — новые.
- **AGENTS.md**: переписать (убрать wave-концепцию, добавить батч-выполнение, `baseline_commit`).
- **README.md**: переписать (новый workflow, 13 сессий базовый прогон, 4 инкремент).
- **Шаблоны**: `tasks/_TEMPLATE.md` (добавить `baseline_commit`), `runs/_TEMPLATE.md` (без wave), `verdicts/_TEMPLATE.md` (без wave), `waves/_TEMPLATES/` → удалить.
- **OpenSpec specs**: `wave-snapshot` → удалить из `openspec/specs/`. Остальные 6 — переписать.
- **Сокращение сессий**: 184 → 13 (базовый прогон), 4-5 (инкремент).
