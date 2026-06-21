## REMOVED Requirements

### Requirement: Изоляция участника
**Reason**: Изоляция по задаче, не по волне. `isolate.py --task` вместо `--wave`.
**Migration**: Использовать новый requirement "Изоляция по задаче".

### Requirement: Работа на git-теге волны
**Reason**: Нет волн, нет тегов. Участник делает `git checkout <baseline_commit>` из `task.md`.
**Migration**: Использовать новый requirement "Работа на baseline_commit".

### Requirement: Формат прогона
**Reason**: Структура `runs/<wave>/<model>/<task>/` → `runs/<task-id>/<model>/`.
**Migration**: Использовать новый requirement "Формат прогона (новая структура)".

### Requirement: Diff.patch изменений
**Reason**: Сохраняется, но путь изменён.
**Migration**: `runs/<task-id>/<model>/diff.patch`.

### Requirement: Очистка проекта после выполнения
**Reason**: Сохраняется, но в контексте батч-выполнения.
**Migration**: Использовать новый requirement "Очистка проекта (батч)".

### Requirement: Clarifying questions без ответа
**Reason**: Сохраняется без изменений по существу.
**Migration**: Использовать новый requirement "Clarifying questions (батч)".

### Requirement: Чек-лист виден участнику
**Reason**: Сохраняется без изменений.
**Migration**: Без изменений, requirement переносится.

## ADDED Requirements

### Requirement: Батч-выполнение

Участник MUST выполнять все задачи (4) в одной сессии. Промпт: "Выполни задачи F-001, B-001, R-001, V-001. Для каждой — checkout baseline_commit, выполни, сохрани прогон, cleanup." Это сокращает 40 сессий → 5 (по 1 на участника).

#### Scenario: Батч из 4 задач

- **WHEN** участник `claude-sonnet-4.5` начинает базовый прогон
- **THEN** он получает промпт с 4 задачами
- **AND** выполняет их последовательно в одной сессии
- **AND** после каждой задачи — cleanup (`git checkout . && git clean -fd`)

#### Scenario: Инкремент — 1 участник, 4 задачи

- **WHEN** новая модель `model-F` добавляется
- **THEN** она выполняет те же 4 задачи в 1 сессии
- **AND** результаты сравнимы с model-A..E (те же задачи, те же baseline_commit)

### Requirement: Изоляция по задаче

Перед выполнением участник MUST быть изолирован от чужих прогонов. `isolate.py hide --task all --except <model-id>` перемещает чужие папки `runs/<task-id>/<other-model>/` в `.isolation-stash/`. После выполнения — `isolate.py restore`.

#### Scenario: Чужие прогоны скрыты

- **WHEN** участник `gpt-5` начинает батч-выполнение
- **THEN** `isolate.py hide --task all --except gpt-5` перемещает чужие прогоны
- **AND** в `runs/<task-id>/` остаётся только папка `gpt-5/`

#### Scenario: Восстановление

- **WHEN** участник завершил батч
- **THEN** `isolate.py restore` возвращает перемещённые папки

### Requirement: Работа на baseline_commit

Участник MUST выполнять задачу на `baseline_commit` из front matter `task.md`. `git checkout <baseline_commit>` в папке проекта. Никаких git-тегов не требуется.

#### Scenario: Checkout по commit

- **WHEN** участник начинает задачу F-001
- **THEN** он читает `baseline_commit` из `tasks/feature/F-001-*/task.md`
- **AND** выполняет `git checkout <commit>` в `C:/projects/<Project>`

### Requirement: Формат прогона (новая структура)

После выполнения участник MUST создать прогон в `runs/<task-id>/<model-id>/run.md` по шаблону `runs/_TEMPLATE.md`. Для feature/bugfix/refactor — также `runs/<task-id>/<model-id>/diff.patch`. Для review — только `run.md`.

#### Scenario: Прогон в новой структуре

- **WHEN** участник `claude-sonnet-4.5` завершил задачу `F-001`
- **THEN** файл `runs/F-001-<slug>/claude-sonnet-4.5/run.md` существует
- **AND** файл `runs/F-001-<slug>/claude-sonnet-4.5/diff.patch` существует

### Requirement: Очистка проекта (батч)

После каждой задачи в батче участник MUST откатить изменения: `git checkout . && git clean -fd`. После всех задач — проект чист.

#### Scenario: Очистка между задачами

- **WHEN** участник завершил F-001 и начинает B-001
- **THEN** он выполняет `git checkout . && git clean -fd` в папке проекта
- **AND** затем `git checkout <baseline_commit для B-001>`

### Requirement: Clarifying questions (батч)

Участник MAY задавать уточняющие вопросы по задачам, фиксируя их в секции «Вопросы по задаче» каждого прогона. Никто не SHALL отвечать. Судья MUST оценивать качество вопросов.

#### Scenario: Вопросы зафиксированы

- **WHEN** участник столкнулся с неоднозначностью в задаче
- **THEN** он записывает вопрос в секцию «Вопросы по задаче» прогона
- **AND** делает разумное предположение и продолжает

### Requirement: Чек-лист виден участнику (батч)

Участник MUST иметь доступ к `tasks/_CHECKLIST.md`. Участник MUST NOT иметь доступ к `judges/_RUBRIC.md`.

#### Scenario: Чек-лист доступен

- **WHEN** участник читает задачу
- **THEN** `tasks/_CHECKLIST.md` доступен
- **AND** `judges/_RUBRIC.md` не доступен
