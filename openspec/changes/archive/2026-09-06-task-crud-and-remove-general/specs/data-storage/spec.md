# data-storage Specification

## MODIFIED Requirements

### Requirement: Source of truth — файлы
Исходные данные SHALL храниться в файлах: `models.yaml` (реестр), `tasks/T-NNN-<slug>/task.md` (задачи), `answers/T-NNN/*.md` (ответы: `modelA.md` / `modelB.md` от skills либо `<model-id>.md` вручную), `matchups/T-NNN/NNN.json` (вердикты), `settings.yaml` (настройки: статусы тасок и текущая таска). `matchups/general/` и `matchups/<non-T-NNN>/` MUST NOT использоваться. `answers/<task>/slots.json` MUST NOT использоваться. Эти файлы SHALL коммититься в git.

#### Scenario: Git diff ответа
- **WHEN** модель пишет ответ
- **THEN** git diff показывает добавленный Markdown-файл в `answers/T-NNN/`
- **AND** не создаётся `answers/T-NNN/slots.json`

#### Scenario: Git diff вердикта
- **WHEN** записывается новый вердикт
- **THEN** git diff показывает один добавленный JSON-файл в `matchups/T-001/`
- **AND** `matchups/general/` не появляется

#### Scenario: Git diff настроек
- **WHEN** пользователь сохраняет настройки через `/settings`
- **THEN** git diff показывает изменённый `settings.yaml` в корне
- **AND** в нём нет ключа `general`

### Requirement: Файл настроек settings.yaml
`settings.yaml` в корне репозитория SHALL хранить: `current_task` (id активной таски, подставляемой в форму вердикта) и `tasks` — отображение `id таски -> status` (`active` | `inactive`). Файл SHALL коммититься в git и MAY редактироваться вручную. При отсутствии файла SHALL применяться дефолты: активные таски — все `T-NNN`, обнаруженные в `tasks/` и `matchups/T-NNN/`; `current_task` — первая активная таска (лексикографически). При отсутствии `tasks`-записи для обнаруженной `T-NNN` таски она SHALL считаться активной. `general` не является допустимым значением `current_task` или ключа `tasks`.

#### Scenario: Сохранение настроек
- **WHEN** на странице `/settings` отмечены `T-001` и `T-002` как активные, текущая — `T-001`
- **THEN** `settings.yaml` содержит `current_task: T-001` и `tasks` со статусами `T-001: active`, `T-002: active`
- **AND** ключа `general` в файле нет

#### Scenario: Отсутствующий файл
- **WHEN** `settings.yaml` не существует, но есть `tasks/T-001-<slug>/task.md`
- **THEN** сервер работает с дефолтами: `T-001` активна, `current_task` = `T-001`
- **AND** `general` не добавляется

#### Scenario: Новая таска без записи
- **WHEN** в `matchups/T-002/` появился новый вердикт, отсутствующий в `settings.yaml`
- **THEN** `T-002` считается активной до явной отметки

## ADDED Requirements

### Requirement: Миграция корзины general
Система SHALL предоставлять одноразовый скрипт/шаг миграции, который переносит файлы из `matchups/general/` в `matchups/T-001/` и переписывает в них поле `task` с `general` на `T-001`. После миграции директория `matchups/general/` MUST быть пустой/удалённой, а `settings.yaml` не SHALL содержать `general`.

#### Scenario: Миграция
- **WHEN** запущен скрипт миграции
- **THEN** все файлы `matchups/general/NNN.json` перемещены в `matchups/T-001/NNN.json`
- **AND** поле `task` в каждом файле равно `T-001`
- **AND** `index.json` пересчитывается
- **AND** `settings.yaml` содержит `current_task: T-001` и `T-001: active`
