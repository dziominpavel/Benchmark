## ADDED Requirements

### Requirement: Изоляция участника

Перед выполнением задачи участник MUST быть изолирован от чужих прогонов. `tools/isolate.py hide --wave <wave> --except <model-id>` физически перемещает чужие папки `runs/<wave>/<other-model-id>/` в `.isolation-stash/` (в `.gitignore`). После выполнения — `isolate.py restore`.

#### Scenario: Чужие прогоны скрыты

- **WHEN** участник `gpt-5` начинает задачу на волне `wave-01-2026Q3`
- **THEN** `isolate.py hide --wave wave-01-2026Q3 --except gpt-5` перемещает `runs/wave-01-2026Q3/claude-sonnet-4.5/` и `runs/wave-01-2026Q3/glm-4.6/` в `.isolation-stash/`
- **AND** в `runs/wave-01-2026Q3/` остаётся только папка `gpt-5/`

#### Scenario: Восстановление после выполнения

- **WHEN** участник `gpt-5` завершил задачу
- **THEN** `isolate.py restore` возвращает перемещённые папки из `.isolation-stash/` обратно
- **AND** `.isolation-stash/` пуст

### Requirement: Работа на git-теге волны

Участник MUST выполнять задачу в папке проекта на git-теге `benchmark-wave-NN` текущей волны. Запрещено работать на произвольной ветке.

#### Scenario: Checkout тега

- **WHEN** участник начинает задачу, привязанную к проекту VoiceMind, на волне `wave-01-2026Q3`
- **THEN** в `C:/projects/VoiceMind` выполнен `git checkout benchmark-wave-01`

### Requirement: Формат прогона

После выполнения участник MUST создать прогон в `runs/<wave>/<model-id>/<task-id>/run.md` по шаблону `runs/_TEMPLATE.md`. Front matter: `task_id`, `model_id`, `wave`, `date`, `status`, `build_pass`, `tests_pass`, `openspec_validate_pass`, баллы самооценки, `total_score`, `max_score`, `normalized_score`, `diff_ref`. Ниже — секции «Что сделано», «Что получилось хорошо», «Что не получилось», «Trade-offs», «Что бы улучшила», «Препятствия», «Вопросы по задаче».

#### Scenario: Прогон создан

- **WHEN** участник `claude-sonnet-4.5` завершил задачу `F-001` на волне `wave-01-2026Q3`
- **THEN** файл `runs/wave-01-2026Q3/claude-sonnet-4.5/F-001-<slug>/run.md` существует
- **AND** его front matter содержит `task_id`, `model_id`, `wave`, `date`, `status`

### Requirement: Diff.patch изменений

Для задач категорий feature, bugfix, refactor участник MUST сохранить `diff.patch` — git diff изменений в проекте — в `runs/<wave>/<model-id>/<task-id>/diff.patch`. Для review-задач `diff.patch` отсутствует.

#### Scenario: Diff сохранён для feature

- **WHEN** участник завершил feature-задачу F-001
- **THEN** `runs/<wave>/<model-id>/F-001-<slug>/diff.patch` существует
- **AND** `git apply diff.patch` на теге волны применяет изменения без конфликтов

#### Scenario: Diff отсутствует для review

- **WHEN** участник завершил review-задачу V-001
- **THEN** `diff.patch` не создаётся
- **AND** прогон содержит только текстовый анализ в `run.md`

### Requirement: Очистка проекта после выполнения

После сохранения прогона участник MUST откатить изменения в проекте: `git checkout .` и `git clean -fd`. Снапшот остаётся чистым для следующей модели.

#### Scenario: Проект чист после прогона

- **WHEN** участник завершил задачу и сохранил прогон
- **THEN** `git status` в папке проекта показывает clean working tree
- **AND** `git checkout . && git clean -fd` выполнены

### Requirement: Clarifying questions без ответа

Участник MAY задавать уточняющие вопросы по задаче, фиксируя их в секции «Вопросы по задаче» прогона. Никто не SHALL отвечать участнику. Судья MUST оценивать качество вопросов в рубрикаторе.

#### Scenario: Вопросы зафиксированы

- **WHEN** участник столкнулся с неоднозначностью в задаче
- **THEN** он записывает вопрос в секцию «Вопросы по задаче» прогона
- **AND** делает разумное предположение и продолжает выполнение

#### Scenario: Никто не отвечает

- **WHEN** участник задал вопрос в прогоне
- **THEN** ответ не предоставляется ни пользователем, ни другой моделью
- **AND** судья оценивает качество вопроса в рубрикаторе

### Requirement: Чек-лист виден участнику

Участник MUST иметь доступ к `tasks/_CHECKLIST.md` — список критериев без баллов. Участник MUST NOT иметь доступ к `judges/_RUBRIC.md` — детальному рубрикатору с баллами.

#### Scenario: Чек-лист доступен

- **WHEN** участник читает задачу
- **THEN** `tasks/_CHECKLIST.md` доступен и содержит критерии без баллов

#### Scenario: Рубрикатор скрыт

- **WHEN** участник выполняет задачу
- **THEN** `judges/_RUBRIC.md` не доступен в его рабочем окружении
