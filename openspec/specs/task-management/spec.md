# task-management Specification

## Purpose
Создание и хранение задач бенчмарка MVP. Единый формат — аналитические задачи
(анализ проекта, поиск багов, планирование, граничные случаи) с опциональным
кодом в ответе. Задачи создаются редко (1 на 2–3 недели прогонов) вручную
из шаблона — генеративного skill в репозитории нет.

## Requirements

### Requirement: Формат задачи

Каждая задача SHALL храниться в `data/tasks/T-NNN-<slug>/task.md`. NNN — сквозной
порядковый номер (001, 002, …), slug — короткое описание в kebab-case.
Файл SHALL содержать YAML front matter и тело описания.

#### Scenario: Структура задачи

- **WHEN** создаётся задача «Bug Hunt — RecurrenceCalculator»
- **THEN** создаётся директория `data/tasks/T-001-recurrence-bugs/`
- **AND** файл `task.md` внутри

### Requirement: Front matter задачи

YAML front matter SHALL содержать: `id` (T-NNN), `title` (человекочитаемое
название); для задач на реальном проекте — `project` (имя проекта-референса)
и `baseline_commit` (хеш коммита для воспроизводимости). Для абстрактных задач
поля `project` / `baseline_commit` отсутствуют.

#### Scenario: Задача с референсом на проект

- **WHEN** задача связана с проектом VoiceMind
- **THEN** front matter содержит: project: VoiceMind, baseline_commit: <хеш>

#### Scenario: Абстрактная задача

- **WHEN** задача не связана с конкретным проектом
- **THEN** поля project и baseline_commit отсутствуют
- **AND** skills пропускают шаг `git checkout`

### Requirement: Содержание задачи

Тело task.md SHALL описывать: что проанализировать/найти/спланировать,
контекст и файлы, что искать, критерии полноты ответа, ограничения.
UI-тексты — на русском, код и идентификаторы — на английском.

#### Scenario: Задача на анализ багов

- **WHEN** задача требует найти баги в модуле
- **THEN** task.md описывает: модуль, файлы, направления поиска, формат ответа
  (файл, строка, пример входа, исправление, критичность)

### Requirement: Шаблон задачи
Файл `data/tasks/_TEMPLATE.md` SHALL содержать пустой шаблон с front matter (`id`, `title`, опциональные `project`, `baseline_commit`) и секциями (описание, критерии полноты, ограничения). Шаблон используется CLI `register_task.py` и веб-формой при создании новой задачи. Ручное копирование шаблона остаётся допустимым, но не является единственным механизмом.

#### Scenario: Создание новой задачи из шаблона
- **WHEN** пользователь копирует `data/tasks/_TEMPLATE.md` в `data/tasks/T-002-<slug>/task.md`
- **THEN** заполняет id, title, project, baseline_commit, описание
- **AND** система распознаёт новую таску как `T-002`

#### Scenario: Создание задачи через CLI
- **WHEN** выполнено `python tools/register_task.py --title "API Race" --slug api-race`
- **THEN** `register_task.py` копирует `_TEMPLATE.md` в `data/tasks/T-002-api-race/task.md`
- **AND** front matter заполняется автоматически

### Requirement: Нумерация задач

Номера задач (NNN) SHALL быть сквозными и не переиспользоваться. Следующий
номер = max(существующие) + 1, определяется вручную.

#### Scenario: Первая задача

- **WHEN** задач ещё нет
- **THEN** первая задача получает номер T-001

#### Scenario: После двух задач

- **WHEN** существуют T-001 и T-002
- **THEN** следующая задача получает номер T-003

### Requirement: baseline_commit опционален

Для задач на реальном проекте `baseline_commit` SHALL обеспечивать
воспроизводимость: skills прогонов и судьи создают отдельную копию проекта
(`git clone --no-local --no-checkout`) и делают checkout baseline только в ней.
Исходный проект MUST NOT изменяться. Для абстрактных задач checkout не выполняется.

#### Scenario: Модель читает проект

- **WHEN** задача имеет `baseline_commit` и `project`
- **THEN** skill создаёт отдельную копию проекта и выполняет в ней `git checkout <baseline_commit>`
- **AND** исходный проект остаётся с зафиксированными до старта HEAD и `git status --short`

### Requirement: Статус активности задачи
Каждая известная таска SHALL иметь статус активности: `active` или `inactive`, хранящийся в `data/settings.yaml`. Множество известных тасок SHALL определяться как объединение идентификаторов `data/tasks/T-NNN-*` и значений поля `task` в событиях `data/matchups/journal.jsonl`. `general` и другие не-T-NNN значения `task` в журнале MUST NOT считаться тасками и не SHALL появляться в настройках. Неактивные таски MUST NOT участвовать в расчёте прогресса и MUST NOT предлагаться как текущие. Таска без записи в `data/settings.yaml` SHALL считаться активной, кроме не-T-NNN значений.

#### Scenario: Новая таска активна по умолчанию
- **WHEN** создана `data/tasks/T-002-new/task.md` без записи в `data/settings.yaml`
- **THEN** `T-002` считается активной
- **AND** участвует в прогрессе

#### Scenario: Исключение устаревшей таски
- **WHEN** таска `T-002` помечена неактивной в настройках
- **THEN** её вердикты не заполняют ячейки прогресса
- **AND** она не может быть выбрана текущей (`current_task`)

#### Scenario: General не считается таской
- **WHEN** в `data/matchups/journal.jsonl` есть событие с `task: general`
- **THEN** `general` не появляется в списке известных тасок в `/settings`
- **AND** не может быть выбран текущей

### Requirement: Автоматическое создание задачи
Система SHALL предоставлять CLI `tools/register_task.py` и веб-форму, которые по `title` (и опциональным `project`, `baseline_commit`, `slug`) создают директорию `data/tasks/T-NNN-<slug>/` с `task.md`, скопированным из `data/tasks/_TEMPLATE.md` и заполненным front matter. Следующий номер `NNN` SHALL определяться как `max(существующих T-NNN) + 1`. `slug` при отсутствии SHALL генерироваться из `title` аналогично `slugify` моделей. Новая таска SHALL по умолчанию получать статус `active` и становиться `current_task` в `data/settings.yaml`.

#### Scenario: Создание задачи через CLI
- **WHEN** выполнено `python tools/register_task.py --title "API Race Conditions" --slug api-race`
- **THEN** создаётся `data/tasks/T-002-api-race/task.md` с `id: T-002`
- **AND** `title: "API Race Conditions"`
- **AND** в `data/settings.yaml` появляется `T-002: active` и `current_task: T-002`

#### Scenario: Создание задачи через UI
- **WHEN** пользователь вводит название "Cache Invalidation" и slug `cache-inv` на странице добавления задачи
- **THEN** сервер создаёт `data/tasks/T-003-cache-inv/task.md`
- **AND** обновляет `data/settings.yaml`

#### Scenario: Автоматический slug
- **WHEN** выполнено `python tools/register_task.py --title "Race Conditions!"`
- **THEN** создаётся директория `data/tasks/T-002-race-conditions/`

### Requirement: Редактирование метаданных задачи
Система SHALL позволять редактировать `title`, `project`, `baseline_commit` и тело `task.md` без изменения `id`. Изменения в `task.md` SHALL сохраняться в исходном файле; `id` SHALL оставаться неизменным.

#### Scenario: Изменение названия
- **WHEN** пользователь открывает редактирование `T-001` и меняет `title`
- **THEN** `data/tasks/T-001-recurrence-bugs/task.md` обновляется
- **AND** `id: T-001` остаётся неизменным

### Requirement: Деактивация и активация задачи
Система SHALL позволять переключать статус задачи между `active` и `inactive`. Деактивированная задача MUST NOT участвовать в прогрессе, НЕ может быть `current_task` и не отображается в форме вердикта. Слоты `data/answers/` и события журнала задачи остаются на месте.

#### Scenario: Деактивация
- **WHEN** `T-002` помечена `inactive`
- **THEN** `data/settings.yaml` содержит `T-002: inactive`
- **AND** `T-002` не предлагается в форме вердикта
- **AND** события `T-002` в журнале не удаляются

#### Scenario: Активация
- **WHEN** `T-002` снова активирована
- **THEN** `data/settings.yaml` содержит `T-002: active`
- **AND** события `T-002` в журнале снова считаются в прогрессе

### Requirement: Удаление задачи
«Удаление» задачи через UI SHALL означать деактивацию: система не удаляет `data/tasks/`, `data/answers/` и события журнала. Опционально MAY предоставляться отдельная CLI-команда физического удаления, требующая явного подтверждения и доступная только вручную.

#### Scenario: Удаление через UI
- **WHEN** пользователь нажимает «Удалить» для `T-002`
- **THEN** `T-002` становится `inactive`
- **AND** файлы задачи остаются на диске
