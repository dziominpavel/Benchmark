# Tasks: task-crud-and-remove-general

## 1. Миграция и очистка `general`

- [x] 1.1 Создать `tools/migrate_general_to_t001.py`, который переносит `matchups/general/*.json` → `matchups/T-001/`, переписывает `task` на `T-001`, удаляет пустую `matchups/general/`. Проверка: `python tools/migrate_general_to_t001.py` → в `matchups/T-001/` 68 файлов, `matchups/general/` удалена.
- [x] 1.2 Запустить миграцию в рабочей копии и проверить `git status`. Проверка: `git status` показывает `matchups/general/` deleted, `matchups/T-001/` added.
- [x] 1.3 Обновить `settings.yaml` через миграцию: убрать `general`, `current_task: T-001`, `T-001: active`. Проверка: `cat settings.yaml` не содержит `general`.
- [x] 1.4 Пересчитать `index.json` после миграции. Проверка: `python tools/elo.py --check` проходит без ошибок.

## 2. CRUD тасок в `elo.py`

- [x] 2.1 Изменить `known_tasks()` так, чтобы включались только `T-NNN` из `tasks/`, `matchups/` и `settings.yaml` (игнорировать `general`). Проверка: `python -c "from tools.elo import known_tasks; print(known_tasks())"` → `['T-001']` (после миграции).
- [x] 2.2 Изменить `resolve_current_task()`: возвращать первую активную `T-NNN`, а не `general`; при отсутствии активных — пустую строку. Проверка: удалить/закомментировать `current_task` в `settings.yaml` → `resolve_current_task()` = `T-001`.
- [x] 2.3 Добавить в `record_verdict()` проверку, что `task` активен и соответствует `^T-\d+`. Проверка: `record_verdict('general', ...)` бросает `ValueError`.
- [x] 2.4 Обновить `active_tasks()` и `get_coverage()` для работы без `general`. Проверка: `python tools/elo.py` → прогресс вырос, `general` не в счётчиках.

## 3. CLI `tools/register_task.py`

- [x] 3.1 Создать `register_task.py` с аргументами `--title`, `--slug` (опц.), `--project`, `--baseline`, `--auto`. Проверка: `python tools/register_task.py --title "Test Task"` создаёт `tasks/T-NNN-test-task/task.md` и обновляет `settings.yaml`.
- [x] 3.2 Реализовать автоопределение следующего `T-NNN` по `tasks/T-*` и `matchups/T-*`. Проверка: после `T-001` новая задача получает `T-002`.
- [x] 3.3 Реализовать `slugify` для заголовка, защиту от дубликатов `id`/`slug`. Проверка: `register_task.py --title "Test Task"` второй раз → slug `test-task-2`.
- [x] 3.4 Наполнить `task.md` front matter из шаблона. Проверка: созданный файл содержит `id`, `title`, `project` (если указан), `baseline_commit` (если указан).

## 4. Веб-форма управления тасками

- [x] 4.1 Добавить в `/settings` карточку «Таски» со списком: id, название, статус, кнопки «Активировать/Деактивировать», «Текущая», «Изменить», «+ Добавить таску». Проверка: открыть `http://localhost:5000/settings` → виден список и кнопки.
- [x] 4.2 Создать страницу `/add_task` с формой title/slug/project/baseline. Проверка: отправка формы → новая папка `tasks/T-NNN-*/`, запись в `settings.yaml`.
- [x] 4.3 Создать страницу `/edit_task/<task_id>` для редактирования `title`, `project`, `baseline_commit` и тела `task.md`. Проверка: сохранение → файл `task.md` обновляется, `id` не меняется.
- [x] 4.4 Реализовать POST-обработчики для деактивации/активации и назначения `current_task`. Проверка: тоггл статуса в `/settings` → `settings.yaml` обновляется, форма вердикта показывает только активные.

## 5. Исправление формы вердикта

- [x] 5.1 Заменить в `INDEX_TEMPLATE` `<input type="text" list="task-list">` на `<select>` с активными тасками, выбранным `current_task`. Проверка: открыть главную → виден dropdown с `T-001`.
- [x] 5.2 Обновить `validate()` в JS: таск выбран, модели разные. Проверка: без выбора таска кнопки «Победила A/B/Ничья» disabled.
- [x] 5.3 Обновить `POST /verdict` для валидации активного таска. Проверка: попытка подмены `task=general` → редирект с ошибкой.
- [x] 5.4 Проверить, что `record_verdict.py --task T-NNN` и веб-форма пишут в `matchups/T-NNN/`. Проверка: после записи появляется новый JSON в `matchups/T-001/`.

## 6. Тесты и валидация

- [x] 6.1 Запустить `python tools/elo.py --check` после всех изменений. Проверка: ошибок нет.
- [x] 6.2 Запустить `python tools/test_elo.py` (если затронуты `elo.py` функции). Проверка: все тесты проходят.
- [x] 6.3 Запустить `openspec validate --all`. Проверка: нет ошибок в спеках.
- [x] 6.4 Протестировать полный цикл: `register_task.py` → `/settings` → форма вердикта. Проверка: новый таск появляется в select, вердикт пишется в `matchups/T-NNN/`.

## 7. Документация

- [x] 7.1 Обновить `README.md`: убрать `general`, описать `register_task.py`, новые страницы. Проверка: `README.md` не содержит `matchups/general`.
- [x] 7.2 Обновить `docs/workflow-guide.md`: шаг 1 — добавить `register_task.py`. Проверка: гайд ссылается на `tools/register_task.py`.
- [x] 7.3 Обновить `tasks/_TEMPLATE.md` при необходимости (например, комментарий о создании через `register_task.py`). Проверка: в шаблоне есть ссылка на CLI.
