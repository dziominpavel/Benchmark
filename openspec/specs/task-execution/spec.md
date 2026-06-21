## Purpose

Выполнение задач участниками. Батч-выполнение: 1 сессия участника = все задачи.
`baseline_commit` в `task.md` заменяет git-теги. Структура `runs/<task-id>/<model>/`.

## Requirements

### Requirement: Батч-выполнение

Участник MUST выполнять все задачи (4) в одной сессии. Промпт: "Выполни задачи
F-001, B-001, R-001, V-001. Для каждой — checkout baseline_commit, выполни,
сохрани прогон, cleanup." Это сокращает 40 сессий → 5 (по 1 на участника).

#### Scenario: Батч из 4 задач

- **WHEN** участник `claude-sonnet-4.5` начинает базовый прогон
- **THEN** он получает промпт с 4 задачами
- **AND** выполняет их последовательно в одной сессии
- **AND** после каждой задачи — cleanup (`git checkout . && git clean -fd`)

#### Scenario: Инкремент — 1 участник, 4 задачи

- **WHEN** новая модель `model-F` добавляется
- **THEN** она выполняет те же 4 задачи в 1 сессии
- **AND** результаты сравнимы с model-A..E (те же задачи, те же baseline_commit)

### Requirement: Изоляция через skill

Изоляция прогонов SHALL выполняться автоматически через skill `benchmark-03-run`
(не вручную). Skill запускает `isolate.py hide --task all --except <model-id>`
перед сессией и `isolate.py restore` после подтверждения пользователя.
Пользователь не запускает `isolate.py` напрямую.

#### Scenario: Skill управляет изоляцией

- **WHEN** пользователь говорит "run claude-sonnet-4.5"
- **THEN** skill `benchmark-03-run` запускает `isolate.py hide --task all --except claude-sonnet-4.5`
- **AND** готовит промпт для участника
- **WHEN** пользователь говорит "готово"
- **THEN** skill запускает `isolate.py restore`
- **AND** пользователь не запускал `isolate.py` напрямую

### Requirement: Саморегистрация участника

Участник SHALL саморегистрироваться в `models.yaml` при старте через
`register_model.py --auto`. AGENTS.md инструктирует модель сделать это
первым шагом (не "попроси пользователя").

#### Scenario: Участник саморегистрируется

- **WHEN** модель `claude-sonnet-4.5` начинает выполнение
- **THEN** она запускает `register_model.py --auto --id claude-sonnet-4.5 --name "Claude Sonnet 4.5"`
- **AND** НЕ просит пользователя сделать это

### Requirement: Скрытие golden-answer от участников

`isolate.py hide --task all --except <model-id>` SHALL также скрывать
папку `tasks/bugfix/<id>/golden-answer/` от участника. Golden answer
содержит эталонное решение bugfix-задачи — участник не должен его видеть
во время выполнения. Это позволяет использовать любую модель как resolver
без конфликта ролей (resolver может быть участником той же задачи,
если golden answer скрыт).

#### Scenario: Golden answer скрыт от участника

- **WHEN** `isolate.py hide --task all --except claude-sonnet-4.5` запущен
- **THEN** папки `tasks/bugfix/*/golden-answer/` перемещаются в сташ
- **AND** участник `claude-sonnet-4.5` не видит golden answer во время выполнения
- **WHEN** `isolate.py restore` запущен
- **THEN** папки `golden-answer/` возвращаются на место

#### Scenario: Resolver = участник той же задачи (разрешено)

- **WHEN** Claude была resolver'ом B-001 (создала golden answer)
- **AND** Claude выполняет B-001 как участник
- **THEN** `isolate.py hide` скрывает `tasks/bugfix/B-001/golden-answer/`
- **AND** Claude не видит свой собственный golden answer в новом чате
- **AND** прогон честный (Claude решает задачу заново, не помня решение)

### Requirement: Работа на baseline_commit

Участник MUST выполнять задачу на `baseline_commit` из front matter `task.md`.
`git checkout <baseline_commit>` в папке проекта. Никаких git-тегов не требуется.

#### Scenario: Checkout по commit

- **WHEN** участник начинает задачу F-001
- **THEN** он читает `baseline_commit` из `tasks/feature/F-001-*/task.md`
- **AND** выполняет `git checkout <commit>` в `C:/projects/<Project>`

### Requirement: Формат прогона (новая структура)

После выполнения участник MUST создать прогон в
`runs/<task-id>/<model-id>/run.md` по шаблону `runs/_TEMPLATE.md`. Для
feature/bugfix/refactor — также `runs/<task-id>/<model-id>/diff.patch`.
Для review — только `run.md`.

#### Scenario: Прогон в новой структуре

- **WHEN** участник `claude-sonnet-4.5` завершил задачу `F-001`
- **THEN** файл `runs/F-001-<slug>/claude-sonnet-4.5/run.md` существует
- **AND** файл `runs/F-001-<slug>/claude-sonnet-4.5/diff.patch` существует

### Requirement: Очистка проекта (батч)

После каждой задачи в батче участник MUST откатить изменения:
`git checkout . && git clean -fd`. После всех задач — проект чист.

#### Scenario: Очистка между задачами

- **WHEN** участник завершил F-001 и начинает B-001
- **THEN** он выполняет `git checkout . && git clean -fd` в папке проекта
- **AND** затем `git checkout <baseline_commit для B-001>`

### Requirement: Clarifying questions (батч)

Участник MAY задавать уточняющие вопросы по задачам. Вопросы MUST быть
зафиксированы в секции «Вопросы по задаче» каждого прогона. Никто не
отвечает на эти вопросы. Судья MUST оценивать качество вопросов в вердикте.

#### Scenario: Вопросы зафиксированы

- **WHEN** участник столкнулся с неоднозначностью в задаче
- **THEN** он записывает вопрос в секцию «Вопросы по задаче» прогона
- **AND** делает разумное предположение и продолжает

### Requirement: Чек-лист виден участнику (батч)

Участник MUST иметь доступ к `tasks/_CHECKLIST.md`. Участник MUST NOT иметь
доступ к `judges/_RUBRIC.md`.

#### Scenario: Чек-лист доступен

- **WHEN** участник читает задачу
- **THEN** `tasks/_CHECKLIST.md` доступен
- **AND** `judges/_RUBRIC.md` не доступен
