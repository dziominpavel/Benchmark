# task-management Specification

## MODIFIED Requirements

### Requirement: Шаблон задачи
Файл `tasks/_TEMPLATE.md` SHALL содержать пустой шаблон с front matter (`id`, `title`, опциональные `project`, `baseline_commit`) и секциями (описание, критерии полноты, ограничения). Шаблон используется CLI `register_task.py` и веб-формой при создании новой задачи. Ручное копирование шаблона остаётся допустимым, но не является единственным механизмом.

#### Scenario: Создание новой задачи из шаблона
- **WHEN** пользователь копирует `tasks/_TEMPLATE.md` в `tasks/T-002-<slug>/task.md`
- **THEN** заполняет id, title, project, baseline_commit, описание
- **AND** система распознаёт новую таску как `T-002`

#### Scenario: Создание задачи через CLI
- **WHEN** выполнено `python tools/register_task.py --title "API Race" --slug api-race`
- **THEN** `register_task.py` копирует `_TEMPLATE.md` в `tasks/T-002-api-race/task.md`
- **AND** front matter заполняется автоматически

### Requirement: Статус активности задачи
Каждая известная таска SHALL иметь статус активности: `active` или `inactive`, хранящийся в `settings.yaml`. Множество известных тасок SHALL определяться как объединение идентификаторов `tasks/T-NNN-*` и директорий `matchups/T-NNN/`. `general` и другие не-T-NNN имена директорий `matchups/` MUST NOT считаться тасками и не SHALL появляться в настройках. Неактивные таски MUST NOT участвовать в расчёте прогресса и MUST NOT предлагаться как текущие. Таска без записи в `settings.yaml` SHALL считаться активной, кроме не-T-NNN имён.

#### Scenario: Новая таска активна по умолчанию
- **WHEN** создана `tasks/T-002-new/task.md` без записи в `settings.yaml`
- **THEN** `T-002` считается активной
- **AND** участвует в прогрессе

#### Scenario: Исключение устаревшей таски
- **WHEN** таска `T-002` помечена неактивной в настройках
- **THEN** её вердикты не заполняют ячейки прогресса
- **AND** она не может быть выбрана текущей (`current_task`)

#### Scenario: General не считается таской
- **WHEN** существует директория `matchups/general/` с вердиктами
- **THEN** `general` не появляется в списке известных тасок в `/settings`
- **AND** не может быть выбран текущей

## ADDED Requirements

### Requirement: Автоматическое создание задачи
Система SHALL предоставлять CLI `tools/register_task.py` и веб-форму, которые по `title` (и опциональным `project`, `baseline_commit`, `slug`) создают директорию `tasks/T-NNN-<slug>/` с `task.md`, скопированным из `tasks/_TEMPLATE.md` и заполненным front matter. Следующий номер `NNN` SHALL определяться как `max(существующих T-NNN) + 1`. `slug` при отсутствии SHALL генерироваться из `title` аналогично `slugify` моделей. Новая таска SHALL по умолчанию получать статус `active` и становиться `current_task` в `settings.yaml`.

#### Scenario: Создание задачи через CLI
- **WHEN** выполнено `python tools/register_task.py --title "API Race Conditions" --slug api-race`
- **THEN** создаётся `tasks/T-002-api-race/task.md` с `id: T-002`
- **AND** `title: "API Race Conditions"`
- **AND** в `settings.yaml` появляется `T-002: active` и `current_task: T-002`

#### Scenario: Создание задачи через UI
- **WHEN** пользователь вводит название "Cache Invalidation" и slug `cache-inv` на странице добавления задачи
- **THEN** сервер создаёт `tasks/T-003-cache-inv/task.md`
- **AND** обновляет `settings.yaml`

#### Scenario: Автоматический slug
- **WHEN** выполнено `python tools/register_task.py --title "Race Conditions!"`
- **THEN** создаётся директория `tasks/T-002-race-conditions/`

### Requirement: Редактирование метаданных задачи
Система SHALL позволять редактировать `title`, `project`, `baseline_commit` и тело `task.md` без изменения `id`. Изменения в `task.md` SHALL сохраняться в исходном файле; `id` SHALL оставаться неизменным.

#### Scenario: Изменение названия
- **WHEN** пользователь открывает редактирование `T-001` и меняет `title`
- **THEN** `tasks/T-001-recurrence-bugs/task.md` обновляется
- **AND** `id: T-001` остаётся неизменным

### Requirement: Деактивация и активация задачи
Система SHALL позволять переключать статус задачи между `active` и `inactive`. Деактивированная задача MUST NOT участвовать в прогрессе, НЕ может быть `current_task` и не отображается в форме вердикта. Директории `answers/` и `matchups/` задачи остаются на месте.

#### Scenario: Деактивация
- **WHEN** `T-002` помечена `inactive`
- **THEN** `settings.yaml` содержит `T-002: inactive`
- **AND** `T-002` не предлагается в форме вердикта
- **AND** `matchups/T-002/` не удаляется

#### Scenario: Активация
- **WHEN** `T-002` снова активирована
- **THEN** `settings.yaml` содержит `T-002: active`
- **AND** вердикты `matchups/T-002/` снова считаются в прогрессе

### Requirement: Удаление задачи
«Удаление» задачи через UI SHALL означать деактивацию: система не удаляет `tasks/`, `answers/` и `matchups/` директории. Опционально MAY предоставляться отдельная CLI-команда физического удаления, требующая явного подтверждения и доступная только вручную.

#### Scenario: Удаление через UI
- **WHEN** пользователь нажимает «Удалить» для `T-002`
- **THEN** `T-002` становится `inactive`
- **AND** файлы задачи остаются на диске
