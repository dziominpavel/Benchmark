## ADDED Requirements

### Requirement: Skills в .windsurf/skills/ с нумерацией

System SHALL provide Windsurf/Devin IDE skills in `.windsurf/skills/benchmark-NN-<action>/`
where NN is the order in the workflow (00=status, 01=gen-task, 02=resolve, 03=run,
04=judge, 05=aggregate, 06=stale). Each skill has `SKILL.md` with YAML frontmatter
(`name`, `description`) and supporting files. Skills wrap python scripts — user
does not run python directly. The `description` field includes "Шаг N из 5.
Используй после `benchmark-(N-1)-*`. Дальше: `benchmark-(N+1)-*`." for guidance.

#### Scenario: Skill обнаружен Windsurf

- **WHEN** пользователь открывает workspace в Windsurf/Devin Desktop
- **THEN** skills из `.windsurf/skills/benchmark-*/` автоматически обнаруживаются
- **AND** доступны через `@benchmark-01-gen-task` или автоматический вызов по описанию
- **AND** описание подсказывает порядок (Шаг 1 из 5, дальше 02)

### Requirement: Skill benchmark-00-status — прогресс и навигация

Skill `benchmark-00-status` SHALL показывать текущий прогресс и подсказывать
следующий шаг. Читает `tasks/`, `runs/`, `verdicts/`, определяет на каком шаге
пользователь, что сделано, что осталось, какую команду вызвать следующей.
Доступен ВСЕГДА — вне основного порядка.

#### Scenario: Статус показывает следующий шаг

- **WHEN** пользователь говорит "status"
- **THEN** skill читает `tasks/`, `runs/`, `verdicts/`
- **AND** показывает: "Шаг 3 из 5. Сделано: 2 задачи, 1 resolve, 1 участник. Дальше: `benchmark-03-run gpt-5`"
- **AND** показывает что осталось (сколько сессий)

### Requirement: Skill benchmark-01-gen-task — диалоговая генерация

Skill `benchmark-01-gen-task` SHALL вести диалог с пользователем для создания
задачи по одной. Skill определяет `baseline_commit` через `git rev-parse HEAD`,
предлагает формулировку, пользователь утверждает, файл создаётся.

#### Scenario: Диалоговая генерация

- **WHEN** пользователь говорит "сгенерируй задачу про баги в WorkoutScoreCalculator"
- **THEN** skill определяет `baseline_commit` = текущий HEAD GymProgress
- **AND** предлагает формулировку задачи (категория bugfix, сложность, критерии)
- **AND** спрашивает утверждение
- **WHEN** пользователь говорит "добро"
- **THEN** skill создаёт `tasks/bugfix/B-NNN-<slug>/task.md`

### Requirement: Skill benchmark-02-resolve — golden answer

Skill `benchmark-02-resolve <task-id>` SHALL готовить промпт для resolver-модели
(только bugfix). После "готово" проверяет `tasks/bugfix/<id>/golden-answer/answer.md`
+ `diff.patch`.

#### Scenario: Resolve bugfix

- **WHEN** пользователь говорит "resolve B-001"
- **THEN** skill готовит промпт для resolver-модели
- **AND** показывает промпт для копипаста
- **WHEN** пользователь говорит "готово"
- **THEN** skill проверяет `tasks/bugfix/B-001/golden-answer/answer.md` существует
- **AND** проверяет `tasks/bugfix/B-001/golden-answer/diff.patch` существует

### Requirement: Skill benchmark-03-run — выполнение с изоляцией

Skill `benchmark-03-run <model-id>` SHALL автоматизировать Phase 2: запускает
`isolate.py hide --task all --except <model-id>` (включая скрытие golden-answer),
готовит промпт для участника, показывает пользователю для копипаста, ждёт
подтверждения, запускает `isolate.py restore`.

#### Scenario: Запуск участника

- **WHEN** пользователь говорит "run claude-sonnet-4.5"
- **THEN** skill запускает `isolate.py hide --task all --except claude-sonnet-4.5`
- **AND** `isolate.py` скрывает чужие прогоны И `golden-answer/` папки
- **AND** готовит промпт (читает задачи, AGENTS.md)
- **AND** показывает промпт для копипаста в чат с Claude
- **WHEN** пользователь говорит "готово"
- **THEN** skill запускает `isolate.py restore`
- **AND** проверяет что файлы прогонов созданы в `runs/<task-id>/claude-sonnet-4.5/`

### Requirement: Skill benchmark-04-judge — оценка с изоляцией

Skill `benchmark-04-judge <judge-id>` SHALL автоматизировать Phase 3: запускает
`assign_judges.py --distribute`, `isolate.py hide-verdicts --task all --except
<judge-id>`, готовит промпт для судьи, ждёт подтверждения, запускает
`isolate.py restore-verdicts`.

#### Scenario: Запуск судьи

- **WHEN** пользователь говорит "judge qwen-3-coder"
- **THEN** skill запускает `assign_judges.py --distribute`
- **AND** запускает `isolate.py hide-verdicts --task all --except qwen-3-coder`
- **AND** готовит промпт (читает задачи, анонимизированные прогоны)
- **AND** показывает промпт для копипаста
- **WHEN** пользователь говорит "готово"
- **THEN** skill запускает `isolate.py restore-verdicts`
- **AND** проверяет что вердикты созданы

### Requirement: Skill benchmark-05-aggregate — агрегация

Skill `benchmark-05-aggregate` SHALL запускать `aggregate.py` и показывать
`leaderboard.md`. Подсвечивает disputed прогоны.

#### Scenario: Агрегация

- **WHEN** пользователь говорит "aggregate"
- **THEN** skill запускает `python tools/aggregate.py`
- **AND** показывает содержимое `leaderboard.md`
- **AND** подсвечивает disputed прогоны (разброс > 2)

### Requirement: Skill benchmark-06-stale — проверка устаревания

Skill `benchmark-06-stale` SHALL запускать `check_stale.py` и показывать отчёт.
Опциональный skill — вне основного порядка, используется по запросу.

#### Scenario: Проверка устаревания

- **WHEN** пользователь говорит "stale"
- **THEN** skill запускает `python tools/check_stale.py`
- **AND** показывает таблицу устаревания задач
