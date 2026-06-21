## Purpose

Resolve bugfix-задач до участников, создавая golden answer (baseline для судьи).
Golden answer создаётся ТОЛЬКО для bugfix. Для feature/refactor/review — нет golden.

## Requirements

### Requirement: Resolve только для bugfix

Golden answer (resolve) SHALL создаваться ТОЛЬКО для bugfix-задач. Для
feature/refactor/review — нет golden answer. Resolver MUST быть отдельной
моделью, не генератор и не будущий участник этой задачи.

#### Scenario: Bugfix имеет golden

- **WHEN** задача B-001 (bugfix) отобрана для прогона
- **THEN** resolver решает её и создаёт `tasks/bugfix/B-001-*/golden-answer/answer.md` + `diff.patch`
- **AND** сообщает сложность (1-3) и время

#### Scenario: Feature без golden

- **WHEN** задача F-001 (feature) отобрана для прогона
- **THEN** golden answer НЕ создаётся
- **AND** судья оценивает по критериям задачи + patch участника + тесты

#### Scenario: Review без golden

- **WHEN** задача V-001 (review) отобрана для прогона
- **THEN** golden answer НЕ создаётся
- **AND** судья оценивает по рубрикатору для review (глубина, обоснованность, полнота)

### Requirement: Оценка сложности bugfix-задачи

Resolver bugfix-задачи MUST сообщить оценку сложности (1-3) и время решения.
Слишком лёгкие (resolver решил за < 10 мин) или нереализуемые (resolver не смог)
задачи отбраковываются.

#### Scenario: Задача отбракована как тривиальная

- **WHEN** resolver решил bugfix-задачу за 5 минут и сообщил сложность 1/3
- **THEN** пользователь MAY отбраковать задачу или усложнить

#### Scenario: Задача отбракована как нереализуемая

- **WHEN** resolver не смог решить bugfix-задачу
- **THEN** задача отбраковывается

### Requirement: Скрытие golden answer (bugfix)

Golden answer bugfix-задачи MUST быть скрыт от участников. Участник не имеет
доступа к `tasks/bugfix/<id>/golden-answer/` во время выполнения.

#### Scenario: Участник не видит golden

- **WHEN** участник выполняет bugfix-задачу B-001
- **THEN** папка `tasks/bugfix/B-001-*/golden-answer/` не доступна в его рабочем окружении

### Requirement: Resolver не участник (bugfix)

Resolver bugfix-задачи MUST NOT быть участником этой же задачи. Resolver MAY
быть судьёй других задач.

#### Scenario: Конфликт ролей resolver-участник

- **WHEN** модель `gpt-5` была resolver'ом задачи B-001
- **THEN** она не может быть участником B-001

### Requirement: Golden answer — baseline, не истина

Golden answer SHALL быть baseline для судьи, не абсолютной истиной. Судья MAY
зачесть находку участника вне golden если проверит и подтвердит.

#### Scenario: Находка вне golden зачтена

- **WHEN** участник нашёл баг, которого нет в golden answer
- **AND** судья проверил и подтвердил, что баг реальный
- **THEN** судья зачтёт находку и отметит "вне golden, подтверждено"
