## REMOVED Requirements

### Requirement: 3 судьи на прогон
**Reason**: Батч-оценка: 1 сессия судьи = 2-3 участника × все задачи. Назначение судей по задаче, не по волне.
**Migration**: Использовать новый requirement "Батч-оценка судьями".

### Requirement: Анонимизация прогона для судьи
**Reason**: Сохраняется, но анонимизация глобальная, не на волну.
**Migration**: Использовать новый requirement "Анонимизация (глобальная)".

### Requirement: Что судья получает
**Reason**: Сохраняется по существу, но без привязки к волне. Golden answer только для bugfix.
**Migration**: Использовать новый requirement "Что судья получает (батч)".

### Requirement: Вердикт с обоснованием
**Reason**: Сохраняется. Путь изменён: `verdicts/<task-id>/<model>/<judge-id>.md`.
**Migration**: Использовать новый requirement "Вердикт (новая структура)".

### Requirement: Медиана 3 оценок
**Reason**: Сохраняется. Медиана по 3 судьям.
**Migration**: Без изменений, requirement переносится.

### Requirement: Рубрикатор судьи
**Reason**: Сохраняется. `_RUBRIC.md` без изменений.
**Migration**: Без изменений.

### Requirement: Конфликт интересов судьи
**Reason**: Сохраняется. Судья ≠ участник.
**Migration**: Без изменений.

### Requirement: Изоляция судей
**Reason**: Изоляция по задаче, не по волне. `hide-verdicts --task` вместо `--wave`.
**Migration**: Использовать новый requirement "Изоляция судей (по задаче)".

## ADDED Requirements

### Requirement: Батч-оценка судьями

Судья MUST оценивать 2-3 участника × все задачи (8-12 прогонов) за одну сессию. При 5 участниках: 2 сессии на судью (2+3 участника). При инкременте (1 новый участник): 1 сессия на судью. Это сокращает 120 сессий → 6 (базовый) или 3 (инкремент).

#### Scenario: Базовый прогон — 2 батча на судью

- **WHEN** судья `gpt-5` оценивает 5 участников
- **THEN** он проводит 2 сессии: батч 1 (Участники A, B = 8 прогонов), батч 2 (Участники C, D, E = 12 прогонов)

#### Scenario: Инкремент — 1 батч на судью

- **WHEN** судья `gpt-5` оценивает нового участника F
- **THEN** он проводит 1 сессию: 4 прогона Участника F

### Requirement: Анонимизация (глобальная)

Анонимизация SHALL быть глобальной, `anonymization.yaml` в корне репозитория. `assign_judges.py --init` создаёт карту `model_id → "Участник X"`. Новые модели добавляются в карту при регистрации. Судьи не видят карту.

#### Scenario: Глобальная карта

- **WHEN** `assign_judges.py --init` запущен
- **THEN** `anonymization.yaml` в корне содержит mapping для всех моделей из `models.yaml`
- **AND** судьи не имеют доступа к этому файлу

#### Scenario: Новая модель добавлена

- **WHEN** `register_model.py --id model-F` добавляет новую модель
- **THEN** `assign_judges.py --add-participant model-F` добавляет `model-F → "Участник F"` в `anonymization.yaml`

### Requirement: Что судья получает (батч)

Судья MUST получить для каждого прогона: файл задачи (`task.md`), анонимизированный прогон (`run.md`), `diff.patch` (для feature/bugfix/refactor), golden answer (только для bugfix), `judges/_RUBRIC.md`. При батч-оценке судья получает несколько прогонов в одном промпте.

#### Scenario: Батч с golden (bugfix)

- **WHEN** судья оценивает bugfix-задачу B-001 Участника A
- **THEN** ему доступны: `tasks/bugfix/B-001/task.md`, анонимизированный `run.md`, `diff.patch`, `golden-answer/answer.md`, `golden-answer/diff.patch`, `judges/_RUBRIC.md`

#### Scenario: Батч без golden (feature)

- **WHEN** судья оценивает feature-задачу F-001 Участника A
- **THEN** ему доступны: `tasks/feature/F-001/task.md`, анонимизированный `run.md`, `diff.patch`, `judges/_RUBRIC.md`
- **AND** golden answer НЕ предоставляется

### Requirement: Вердикт (новая структура)

Судья MUST создать вердикт в `verdicts/<task-id>/<participant-anon-id>/<judge-id>.md` по шаблону `verdicts/_TEMPLATE.md`. Каждый балл MUST сопровождаться обоснованием.

#### Scenario: Вердикт в новой структуре

- **WHEN** судья `gpt-5` оценивает прогон Участника A по задаче F-001
- **THEN** файл `verdicts/F-001-<slug>/Участник-A/gpt-5.md` существует
- **AND** содержит баллы с обоснованием

### Requirement: Изоляция судей (по задаче)

Перед оценкой судья MUST быть изолирован от чужих вердиктов. `isolate.py hide-verdicts --task all --except <judge-id>` перемещает чужие вердикты в `.isolation-stash-verdicts/`.

#### Scenario: Чужие вердикты скрыты

- **WHEN** судья `glm-4.6` начинает оценку
- **THEN** `isolate.py hide-verdicts --task all --except glm-4.6` скрывает чужие вердикты
- **AND** в `verdicts/<task-id>/` доступны только вердикты `glm-4.6`

### Requirement: Глобальный pool судей

`judges.yaml` в корне репозитория SHALL содержать список моделей-судей. Не привязан к волне. `assign_judges.py` назначает 3 судей из pool для каждого прогона. Новые модели MAY стать судьями (опционально).

#### Scenario: Pool судей

- **WHEN** `judges.yaml` содержит `[gpt-5, claude-sonnet-4.5, glm-4.6]`
- **THEN** `assign_judges.py` назначает 3 судей для каждого прогона
- **AND** ни один судья не имеет `model_id` = участник прогона

#### Scenario: Новая модель становится судьёй

- **WHEN** `model-F` добавлена в `judges.yaml`
- **THEN** она может судить прогоны других участников
- **AND** не может судить свои собственные прогоны

### Requirement: Инкрементальное назначение судей

`assign_judges.py --add-runs --participant <model-id>` MUST назначать 3 судей для прогонов НОВОГО участника. Не перераспределяет существующие вердикты.

#### Scenario: Добавление нового участника

- **WHEN** `model-F` добавлена, выполнила 4 задачи
- **THEN** `assign_judges.py --add-runs --participant model-F` назначает 3 судей для 4 прогонов model-F
- **AND** существующие вердикты model-A..E не затронуты
