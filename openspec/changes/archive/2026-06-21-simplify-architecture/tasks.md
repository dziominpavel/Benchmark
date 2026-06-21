## 1. Удаление старой структуры (wave-based)

- [x] 1.1 Удалить папку `snapshots/` (включая `_TEMPLATE.md`, `_TEMPLATE.yaml`)
- [x] 1.2 Удалить папку `waves/` (включая `_TEMPLATES/`)
- [x] 1.3 Удалить `runs/wave-01-2026Q3/` (демо-прогон)
- [x] 1.4 Удалить `verdicts/wave-01-2026Q3/` (если есть)
- [x] 1.5 Удалить `openspec/specs/wave-snapshot/` (спека убрана)
- [x] 1.6 Удалить временные файлы `_fix_specs.py`, `_test_*.py` из корня

## 2. Обновление шаблонов

- [x] 2.1 Обновить `tasks/_TEMPLATE.md` — добавить `baseline_commit` и `project` в front matter, убрать `wave`
- [x] 2.2 Обновить `tasks/_CHECKLIST.md` — без изменений по существу, проверить актуальность
- [x] 2.3 Обновить `runs/_TEMPLATE.md` — убрать `wave` из front matter, путь `runs/<task-id>/<model>/`
- [x] 2.4 Создать `verdicts/_TEMPLATE.md` — шаблон вердикта с путём `verdicts/<task-id>/<model>/<judge-id>.md`
- [x] 2.5 Обновить `generators/_PROMPT.md` — генератор определяет `baseline_commit` из `git rev-parse HEAD`, создаёт 4 задачи за 1 сессию
- [x] 2.6 Обновить `judges/_PROMPT.md` — батч-оценка (2-3 участника × все задачи), без привязки к волне
- [x] 2.7 Обновить `judges/_RUBRIC.md` — без изменений по существу, проверить актуальность
- [x] 2.8 Создать `tasks/feature/_TEMPLATE/golden-answer/` — убрать (golden только для bugfix)
- [x] 2.9 Обновить `tasks/bugfix/_TEMPLATE/golden-answer/answer.md` — оставить (golden для bugfix)
- [x] 2.10 Обновить `tasks/refactor/_TEMPLATE/` и `tasks/review/_TEMPLATE/` — убрать `golden-answer/`

## 3. Скрипты — обновление

- [x] 3.1 Обновить `tools/isolate.py` — `--task` вместо `--wave`, изоляция по задаче (`runs/<task-id>/`), добавить `hide-verdicts --task all --except <judge-id>`
- [x] 3.2 Обновить `tools/assign_judges.py` — `--task` вместо `--wave`, глобальный `judges.yaml`, `--add-runs --participant <model-id>` для инкремента, `--init` для базовой анонимизации
- [x] 3.3 Обновить `tools/aggregate.py` — кумулятивный режим, `anonymization.yaml` в корне, разбивка по категориям и задачам (не по волнам), карта назначений по задачам
- [x] 3.4 Проверить `tools/register_model.py` — без изменений (глобальный `models.yaml`)

## 4. Скрипты — новые

- [x] 4.1 Создать `tools/check_stale.py` — проверка `baseline_commit` vs HEAD проекта, `--threshold <N>` (по умолчанию 10), `--output <file>`, отчёт в консоли
- [x] 4.2 Создать `tools/generate_checklist.py` — генерация markdown-файлов с готовыми промптами: `--phase 1|1.5|2|3`, `--participant <model-id>` (для инкремента), читает `models.yaml`, `judges.yaml`, `tasks/`, `runs/`

## 5. Конфигурация — глобальные файлы

- [x] 5.1 Создать `judges.yaml` в корне — список моделей-судей (пустой, заполняется пользователем)
- [x] 5.2 Создать `anonymization.yaml` в корне — пустой, заполняется `assign_judges.py --init`
- [x] 5.3 Проверить `models.yaml` — без изменений (глобальный реестр)

## 6. Документация

- [x] 6.1 Переписать `AGENTS.md` — убрать wave-концепцию, добавить: `baseline_commit` в задаче, батч-выполнение, батч-оценка, глобальный pool судей, инкрементальное добавление
- [x] 6.2 Переписать `README.md` — новый workflow: базовый прогон (13 сессий), инкремент (4-5 сессий), сводная таблица сессий
- [x] 6.3 Обновить `.gitignore` — `.isolation-stash/`, `.isolation-stash-verdicts/`, `stale-report.md`

## 7. Миграция существующих спек (openspec/specs/)

- [x] 7.1 Удалить `openspec/specs/wave-snapshot/` (спека убрана в change)
- [x] 7.2 Переписать `openspec/specs/task-generation/spec.md` — `baseline_commit`, батч-генерация, 1 генератор
- [x] 7.3 Переписать `openspec/specs/task-resolution/spec.md` — golden только для bugfix
- [x] 7.4 Переписать `openspec/specs/task-execution/spec.md` — батч-выполнение, `runs/<task-id>/<model>/`, изоляция по задаче
- [x] 7.5 Переписать `openspec/specs/judging/spec.md` — батч-оценка, глобальный pool, `verdicts/<task-id>/<model>/`
- [x] 7.6 Переписать `openspec/specs/leaderboard/spec.md` — кумулятивный, разбивка по задачам
- [x] 7.7 Обновить `openspec/specs/meta-analysis/spec.md` — анализ по задачам (не по волнам)
- [x] 7.8 Создать `openspec/specs/stale-detection/spec.md` — новая capability

## 8. Проверка

- [x] 8.1 `openspec validate --all` — все спеки валидны
- [x] 8.2 `python tools/check_stale.py` — запускается без ошибок (задач нет, отчёт пуст)
- [x] 8.3 `python tools/generate_checklist.py --phase 2` — запускается, генерирует шаблон (моделей нет, отчёт пуст)
- [x] 8.4 `python tools/isolate.py --help` — `--task` вместо `--wave`
- [x] 8.5 `python tools/assign_judges.py --help` — `--add-runs --participant` доступен
- [x] 8.6 `python tools/aggregate.py` — запускается без ошибок (вердиктов нет, leaderboard пустой)
- [x] 8.7 Проверить, что `snapshots/`, `waves/` не существуют
- [x] 8.8 Проверить, что `judges.yaml`, `anonymization.yaml` в корне существуют
