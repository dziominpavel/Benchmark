# Design: task-crud-and-remove-general

## Context

См. `proposal.md` — Why. Ключевые факты о текущем состоянии:

- Задачи создаются только вручную: копируется `tasks/_TEMPLATE.md` в `tasks/T-NNN-<slug>/task.md`.
- `general` — фиктивная корзина: `matchups/general/` содержит 68 вердиктов, в `settings.yaml` `general: active` и `current_task: general`.
- Форма вердикта использует `<input type="text" list="task-list">`, что не работает как выпадающий список и фильтрует подсказки по текущему значению.
- У моделей уже есть полный CRUD: `tools/register_model.py`, `tools/archive_model.py`, веб-формы `/add`, `/edit/<id>`.

## Goals / Non-Goals

**Goals:**

- Полный CRUD тасок: CLI `register_task.py`, веб-форма добавления, редактирование метаданных, активация/деактивация, выбор текущей.
- Удаление `general` как корзины: миграция 68 вердиктов в `matchups/T-001/`.
- Исправление формы вердикта: `<select>` с активными тасками.
- Обновление `settings.yaml` и дефолтов: нет `general`, `current_task` = первая активная `T-NNN`.

**Non-Goals:**

- Генеративный skill для создания содержимого задачи (описание, критерии) — скрипт только скaffold front matter и папку.
- Физическое удаление файлов задач через UI (по аналогии с `archive_model.py` это просто `inactive`); отдельная destructive-команда не в MVP.
- Изменение ELO-математики или формата `matchups/*.json`, кроме поля `task`.

## Decisions

### 1. Реестр тасок — через `settings.yaml`, директории `tasks/` и `matchups/T-NNN/`

Таски не выносятся в отдельный YAML-файл (в отличие от `models.yaml`), потому что у задачи уже есть собственный файл `task.md` с метаданными. Статус активности и `current_task` хранятся в `settings.yaml`, как сейчас. Это минимальное изменение.

### 2. `register_task.py` аналогичен `register_model.py`

- Определяет следующий `T-NNN` по существующим `tasks/T-NNN-*/`.
- Генерирует slug из `title` (или принимает `--slug` явно).
- Копирует `tasks/_TEMPLATE.md`, заполняет front matter `id`, `title`, `project`, `baseline_commit`.
- Добавляет `T-NNN: active` и `current_task: T-NNN` в `settings.yaml`.
- `--auto` режим для саморегистрации/скриптов, аналогичный `register_model --auto`.

### 3. «Удаление» таски = `inactive`

По аналогии с архивацией модели. `answers/` и `matchups/` остаются; при повторной активации история вернётся в прогресс. Это безопасно и не ломает историю ELO.

### 4. Веб-форма вердикта — `<select>` вместо `<input list>`

- Источник опций: `active_tasks()` (отфильтрованные активные `T-NNN`).
- По умолчанию выбран `current_task`.
- Валидация JS: таск выбран, две разные модели.
- Серверная валидация: `task` активна и удовлетворяет `[A-Za-z0-9_-]+`.

### 5. Миграция `general` → `T-001` — отдельный скрипт

Создаём `tools/migrate_general_to_t001.py`:

1. Создаёт `matchups/T-001/` (если нет).
2. Переносит файлы `matchups/general/*.json` → `matchups/T-001/` с сохранением нумерации.
3. Переписывает поле `task` с `general` на `T-001`.
4. Удаляет пустую `matchups/general/`.
5. Обновляет `settings.yaml`: убирает `general`, ставит `current_task: T-001`, `T-001: active`.
6. Пересчитывает `index.json`.

**Альтернатива** — встроить миграцию в `elo.py`/`server.py` автоматически. Отклонено: миграция затрагивает файловую систему и git, должна быть явной и одноразовой.

### 6. `elo.py`: `known_tasks` фильтрует только `T-NNN`

- `known_tasks` собирает директории `tasks/` и `matchups/`, но включает только те, чей id соответствует `^T-\d+`.
- Ключи `settings.yaml` тоже фильтруются по `^T-\d+`; `general` и прочие не-T-NNN имена игнорируются.
- `resolve_current_task`: если сохранённый `current_task` не активен/неизвестен, возвращает первую активную `T-NNN` (а не `general`). Если активных нет — возвращает пустую строку; UI показывает пустой `<select>`.
- `record_verdict` дополнительно проверяет, что `task` активен.

### 7. Страница `/settings` — единая точка управления тасками

- Расширяем существующий `SETTINGS_TEMPLATE`.
- Добавляем карточку «Таски» с таблицей: id, название (из `task.md`), статус, кнопки «Активировать/Деактивировать», «Текущая», «Изменить».
- Кнопка «+ Добавить таску» ведёт на `/add_task` (аналог `/add` для моделей).
- Форма редактирования `/edit_task/<task_id>`: поля `title`, `project`, `baseline_commit`, textarea с телом `task.md`.

### 8. `generate_html.py` и статичный экспорт

Статичный HTML не содержит форму вердикта, поэтому основных изменений не требует. `index.json` будет содержать `tasks` без `general` и `matchups_index` с `task: T-001` после миграции.

## Risks / Trade-offs

- **[Ссылки на старые matchup_id `general/NNN` ломаются]** → `general/NNN` становится `T-001/NNN`. `seq` сохраняются, ELO не меняется, но внешние ссылки на `general/NNN` перестанут работать. Mitigation: это осознанный breaking change; `general` не существует.
- **[Миграция перенумеровывает matchup_id, но не seq]** → история ELO пересчитается по `seq`, порядок не нарушится. `_matchup_id` в `index.json` изменится, но это производная метрика.
- **[Нумерация в `matchups/T-001/` может дойти до 999]** → для MVP 3 цифр хватит; если превысит, формат `NNN.json` ломается. Mitigation: оставляем как есть, при необходимости будущий change.
- **[Ручное редактирование `settings.yaml` может оставить `general`]** → `known_tasks` фильтрует по `^T-\d+`, так что `general` просто игнорируется, даже если кто-то добавит.
- **[Вердикт для `general` после миграции невозможен]** → UI `<select>` не даст выбрать `general`, CLI `record_verdict.py --task general` будет отклонён.

## Migration Plan

1. Остановить сервер.
2. Запустить `python tools/migrate_general_to_t001.py` (переносит файлы, обновляет `settings.yaml`, пересчитывает `index.json`).
3. Проверить `git status` — ожидаются: удаление `matchups/general/`, добавление `matchups/T-001/`, изменение `settings.yaml`, `index.json`.
4. Запустить `python tools/elo.py --check`.
5. Запустить сервер, проверить форму и настройки.

## Open Questions

- Нужна ли отдельная страница `/add_task` или достаточно inline-формы на `/settings`? Предлагаю `/add_task` для консистентности с `/add` модели.
- Как именно редактировать тело `task.md` — одно большое textarea или раздельные поля (описание, критерии, ограничения)? Предлагаю textarea для всего Markdown, так как структура гибкая.
