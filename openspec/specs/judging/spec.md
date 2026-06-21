## Purpose

Оценка прогонов судьями. Батч-оценка: 1 сессия судьи = 2-3 участника × все задачи.
Глобальный pool судей (`judges.yaml`). Инкрементальное назначение (`--add-runs`).
Структура `verdicts/<task-id>/<participant-anon-id>/<judge-id>.md`.

## Requirements

### Requirement: Батч-оценка судьями

Судья MUST оценивать 2-3 участника × все задачи (8-12 прогонов) за одну сессию.
При 5 участниках: 2 сессии на судью (2+3 участника). При инкременте (1 новый
участник): 1 сессия на судью. Это сокращает 120 сессий → 6 (базовый) или 3 (инкремент).

#### Scenario: Базовый прогон — 2 батча на судью

- **WHEN** судья `gpt-5` оценивает 5 участников
- **THEN** он проводит 2 сессии: батч 1 (Участники A, B = 8 прогонов), батч 2 (Участники C, D, E = 12 прогонов)

#### Scenario: Инкремент — 1 батч на судью

- **WHEN** судья `gpt-5` оценивает нового участника F
- **THEN** он проводит 1 сессию: 4 прогона Участника F

### Requirement: Анонимизация (глобальная)

Анонимизация SHALL быть глобальной, `anonymization.yaml` в корне репозитория.
`assign_judges.py --init` создаёт карту `model_id → "Участник X"`. Новые модели
добавляются в карту при регистрации. Судьи не видят карту.

#### Scenario: Глобальная карта

- **WHEN** `assign_judges.py --init` запущен
- **THEN** `anonymization.yaml` в корне содержит mapping для всех моделей из `models.yaml`
- **AND** судьи не имеют доступа к этому файлу

#### Scenario: Новая модель добавлена

- **WHEN** `register_model.py --id model-F` добавляет новую модель
- **THEN** `assign_judges.py --add-runs --participant model-F` добавляет `model-F → "Участник F"` в `anonymization.yaml`

### Requirement: Что судья получает (батч)

Судья MUST получить для каждого прогона: файл задачи (`task.md`), анонимизированный
прогон (`run.md`), `diff.patch` (для feature/bugfix/refactor), golden answer
(только для bugfix), `judges/_RUBRIC.md`. При батч-оценке судья получает несколько
прогонов в одном промпте.

#### Scenario: Батч с golden (bugfix)

- **WHEN** судья оценивает bugfix-задачу B-001 Участника A
- **THEN** ему доступны: `tasks/bugfix/B-001/task.md`, анонимизированный `run.md`, `diff.patch`, `golden-answer/answer.md`, `golden-answer/diff.patch`, `judges/_RUBRIC.md`

#### Scenario: Батч без golden (feature)

- **WHEN** судья оценивает feature-задачу F-001 Участника A
- **THEN** ему доступны: `tasks/feature/F-001/task.md`, анонимизированный `run.md`, `diff.patch`, `judges/_RUBRIC.md`
- **AND** golden answer НЕ предоставляется

### Requirement: Вердикт (новая структура)

Судья MUST создать вердикт в `verdicts/<task-id>/<participant-anon-id>/<judge-id>.md`
по шаблону `verdicts/_TEMPLATE.md`. Каждый балл MUST сопровождаться обоснованием.

#### Scenario: Вердикт в новой структуре

- **WHEN** судья `gpt-5` оценивает прогон Участника A по задаче F-001
- **THEN** файл `verdicts/F-001-<slug>/Участник-A/gpt-5.md` существует
- **AND** содержит баллы с обоснованием

#### Scenario: Вердикт без обоснования невалиден

- **WHEN** вердикт не содержит "Обоснование:" в теле
- **THEN** `aggregate.py` исключит его из агрегации

### Requirement: Изоляция судей через skill

Изоляция вердиктов SHALL выполняться автоматически через skill
`benchmark-04-judge` (не вручную). Skill запускает `isolate.py hide-verdicts
--task all --except <judge-id>` перед сессией и `isolate.py restore-verdicts`
после подтверждения. Пользователь не запускает `isolate.py` напрямую.

#### Scenario: Skill управляет изоляцией судей

- **WHEN** пользователь говорит "judge qwen-3-coder"
- **THEN** skill `benchmark-04-judge` запускает `isolate.py hide-verdicts --task all --except qwen-3-coder`
- **AND** готовит промпт для судьи
- **WHEN** пользователь говорит "готово"
- **THEN** skill запускает `isolate.py restore-verdicts`

### Requirement: Саморегистрация судьи

Судья SHALL саморегистрироваться в `judges.yaml` при старте через
`assign_judges.py --add-judge <model-id>`. `judges/_PROMPT.md` инструктирует
судью сделать это первым шагом (не "попроси пользователя").

#### Scenario: Судья саморегистрируется

- **WHEN** модель `qwen-3-coder` начинает оценку
- **THEN** она запускает `assign_judges.py --add-judge qwen-3-coder`
- **AND** добавляется в `judges.yaml`
- **AND** НЕ просит пользователя сделать это

### Requirement: Промпт для судьи через skill

Промпт для судьи SHALL готовиться skill `benchmark-04-judge` (не через
`generate_checklist.py --phase 3`). Skill читает задачи, анонимизированные
прогоны, готовит промпт для копипаста.

#### Scenario: Skill готовит промпт судьи

- **WHEN** пользователь говорит "judge qwen-3-coder"
- **THEN** skill `benchmark-04-judge` читает `tasks/`, `.anon-copies/`
- **AND** готовит промпт с задачами и прогонами для оценки
- **AND** показывает пользователю для копипаста в чат с qwen-3-coder

### Requirement: Глобальный pool судей

`judges.yaml` в корне репозитория SHALL содержать список моделей-судей. Не
привязан к волне. `assign_judges.py` назначает 3 судей из pool для каждого
прогона. Новые модели MAY стать судьями (опционально).

#### Scenario: Pool судей

- **WHEN** `judges.yaml` содержит `[gpt-5, claude-sonnet-4.5, glm-4.6]`
- **THEN** `assign_judges.py` назначает 3 судей для каждого прогона
- **AND** ни один судья не имеет `model_id` = участник прогона

#### Scenario: Новая модель становится судьёй

- **WHEN** `model-F` добавлена в `judges.yaml`
- **THEN** она может судить прогоны других участников
- **AND** не может судить свои собственные прогоны

### Requirement: Инкрементальное назначение судей

`assign_judges.py --add-runs --participant <model-id>` MUST назначать 3 судей
для прогонов НОВОГО участника. Не перераспределяет существующие вердикты.

#### Scenario: Добавление нового участника

- **WHEN** `model-F` добавлена, выполнила 4 задачи
- **THEN** `assign_judges.py --add-runs --participant model-F` назначает 3 судей для 4 прогонов model-F
- **AND** существующие вердикты model-A..E не затронуты

### Requirement: Медиана 3 оценок

Для каждого прогона `aggregate.py` MUST вычислять медиану по 3 судьям.
Если разброс > 2 — прогон помечается `disputed`.

#### Scenario: Медиана вычислена

- **WHEN** 3 судьи оценили прогон с баллами 4.0, 4.5, 5.0
- **THEN** медиана = 4.5
- **AND** разброс = 1.0 (не disputed)

#### Scenario: Disputed

- **WHEN** 3 судьи оценили прогон с баллами 2.0, 4.0, 4.5
- **THEN** медиана = 4.0
- **AND** разброс = 2.5 (> 2) → disputed
