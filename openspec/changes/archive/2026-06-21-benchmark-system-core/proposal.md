## Why

Бенчмарк-системе нужен формальный контракт на 6 flow (генерация задач, resolve, выполнение, оценка, агрегация, мета-анализ), чтобы каждый шаг был воспроизводимым, изолированным и проверяемым. Без спецификаций процедура держится только в `AGENTS.md` и разговорах — это хрупко, и новые модели-участники не имеют чётких правил. Спеки зафиксируют роли, форматы артефактов, правила изоляции и анонимизации, критерии оценки.

## What Changes

- **Новые роли моделей**: генератор, resolver, участник, судья — с правилом запрета совмещения ролей в одном прогоне.
- **Поток волны (квартал) из 6 фаз**: подготовка снапшота → генерация задач → resolve (golden answer как baseline) → выполнение (изолированно) → оценка (анонимно, 3 судьи, медиана) → агрегация leaderboard.
- **Изоляция прогонов через `tools/isolate.py`**: физическое скрытие чужих прогонов/вердиктов из файловой системы во время работы модели.
- **Анонимизация судей**: судья не видит `model_id` участника; мост — `waves/<wave>/anonymization.yaml`, доступный только `aggregate.py`.
- **Golden answer как baseline, не истина**: resolver решает задачу до участников, его результат — опорный набор для судьи, но судья может зачесть находку вне golden если проверил и подтвердил.
- **Двухслойный рубрикатор**: `tasks/_CHECKLIST.md` (виден участнику, без баллов) + `judges/_RUBRIC.md` (скрыт, с баллами и индикаторами уровня).
- **8 задач на волну**: 2 feature + 2 bugfix + 2 refactor + 2 review.
- **Clarifying questions без ответа**: участник фиксирует вопросы в прогоне, судья оценивает их качество.
- **Multi-project задачи**: `projects: [a, b]` в front matter, diff.patch может содержать изменения из нескольких проектов.
- **Регистрация моделей через `tools/register_model.py`**: `models.yaml` заполняется командой, не руками и не самописцем участника.
- **Мета-анализ после 2–3 волн**: отбраковка задач, не различающих модели; корректировка рубрикатора.
- **BREAKING**: текущий каркас `runs/<wave>/<task-id>__<model-id>.md` (плоская структура) заменяется на `runs/<wave>/<model-id>/<task-id>/run.md` + `diff.patch` (вложенная, с diff).
- **BREAKING**: `models.yaml` больше не заполняется руками — только через `register_model.py`.

## Capabilities

### New Capabilities

- `wave-snapshot`: подготовка квартальной волны — git-теги в проектах, `snapshots/<wave>/*.yaml`, `participants.yaml`, `judges.yaml`, `anonymization.yaml`.
- `task-generation`: генерация задач 2–3 моделями-генераторами в `_drafts/<gen>/`, отбор, калибровка через resolver.
- `task-resolution`: resolve задачи до участников — golden answer как baseline + оценка сложности для калибровки.
- `task-execution`: выполнение участником в изоляции, формат прогона `run.md` + `diff.patch`, clarifying questions без ответа.
- `judging`: оценка прогонов 3 судьями анонимно, вердикт с обоснованием, медиана, разброс > 2 → ручной разбор.
- `leaderboard`: агрегация вердиктов в `leaderboard.md` через `aggregate.py`, деанонимизация, разбивка по категориям и волнам.
- `meta-analysis`: анализ качества задач и критериев после 2–3 волн, отбраковка неразличающих задач.

### Modified Capabilities

(Нет — в `openspec/specs/` пока пусто, это первые спеки.)

## Impact

- **Новые папки**: `judges/`, `verdicts/`, `tasks/_drafts/`, `tasks/<cat>/<id>/golden-answer/`, `waves/<wave>/{participants,judges,anonymization}.yaml`.
- **Новые скрипты**: `tools/isolate.py`, `tools/register_model.py`, `tools/assign_judges.py`; расширение `tools/aggregate.py` (чтение `verdicts/` + `anonymization.yaml`, медиана, деанонимизация).
- **Изменение структуры**: `runs/<wave>/<task-id>__<model-id>.md` → `runs/<wave>/<model-id>/<task-id>/{run.md, diff.patch}`.
- **Изменение `AGENTS.md`**: протокол участника дополняется шагами изоляции, clarifying questions, форматом `run.md` + `diff.patch`.
- **Новые шаблоны**: `judges/_PROMPT.md`, `judges/_RUBRIC.md`, `tasks/_drafts/_TEMPLATE.md`, `waves/<wave>/{participants,judges,anonymization}.yaml` шаблоны.
- **`models.yaml`**: формат сохраняется, но заполняется только через `register_model.py`.
- **Зависимости**: Python stdlib только (без PyYAML); `aggregate.py` уже работает, будет расширен.
