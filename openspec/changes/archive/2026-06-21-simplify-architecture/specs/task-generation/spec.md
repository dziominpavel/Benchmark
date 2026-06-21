## REMOVED Requirements

### Requirement: Генерация задачи моделями-генераторами
**Reason**: Заменено на батч-генерацию: 1 генератор создаёт все задачи за 1 сессию. 2-3 генератора независимо — убрано для сокращения сессий.
**Migration**: Использовать новый requirement "Батч-генерация задач".

### Requirement: Отбор лучшего черновика
**Reason**: 1 генератор = 1 черновик на задачу. Отбор между генераторами убран.
**Migration**: Генератор создаёт задачу напрямую в `tasks/<cat>/<id>/task.md`.

### Requirement: Промпт для генератора
**Reason**: Промпт обновлён — генератор определяет `baseline_commit` из текущего HEAD проекта.
**Migration**: Обновить `generators/_PROMPT.md`.

## ADDED Requirements

### Requirement: Батч-генерация задач

Задачи на базовый прогон MUST генерироваться 1 моделью-генератором в 1 сессии. Генератор создаёт 4 задачи (1F + 1B + 1R + 1V) для одного проекта. Для каждой задачи генератор определяет `baseline_commit` — текущий HEAD проекта (`git rev-parse HEAD`). Задачи сохраняются напрямую в `tasks/<cat>/<id>/task.md` по шаблону `tasks/_TEMPLATE.md`.

#### Scenario: Генератор создаёт 4 задачи

- **WHEN** пользователь открывает сессию с генератором
- **AND** даёт промпт "Сгенерируй 4 задачи для VoiceMind. Прочитай generators/_PROMPT.md."
- **THEN** генератор создаёт 4 файла: `tasks/feature/F-001-*/task.md`, `tasks/bugfix/B-001-*/task.md`, `tasks/refactor/R-001-*/task.md`, `tasks/review/V-001-*/task.md`
- **AND** каждый содержит `baseline_commit` = текущий HEAD VoiceMind

#### Scenario: baseline_commit зафиксирован

- **WHEN** задача F-001 создана
- **THEN** front matter содержит `baseline_commit: <40-символьный SHA>`
- **AND** этот commit не меняется при последующих генерациях

### Requirement: baseline_commit в задаче

Каждая задача MUST содержать `baseline_commit` в front matter — SHA коммита проекта, на котором задача актуальна. Участник делает `git checkout <baseline_commit>` в папке проекта. Никаких git-тегов в проектах не требуется.

#### Scenario: Участник checkout по commit

- **WHEN** участник начинает задачу F-001
- **THEN** он читает `baseline_commit` из `tasks/feature/F-001-*/task.md`
- **AND** выполняет `git checkout <baseline_commit>` в `C:/projects/<Project>`
- **AND** НЕ требует git-тегов в проекте

#### Scenario: Никаких правок проекта

- **WHEN** задача создана для VoiceMind
- **THEN** в репозитории VoiceMind не создаётся никаких тегов, веток или коммитов
- **AND** только `baseline_commit` в `task.md` ссылается на состояние кода

### Requirement: Генератор не решает задачу

Генератор MUST NOT решать задачу при генерации. Для bugfix — НЕ перечисляет конкретные баги, только "найди N багов в модуле X". Для feature — описывает фичу, не реализует. Генератор не знает ответ.

#### Scenario: Bugfix без ответа

- **WHEN** генератор создаёт bugfix-задачу B-001
- **THEN** задача содержит "найди 5 багов в WorkoutScoreCalculator"
- **AND** НЕ содержит список конкретных багов
