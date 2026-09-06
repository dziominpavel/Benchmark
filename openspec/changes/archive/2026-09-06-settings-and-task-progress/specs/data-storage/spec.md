## MODIFIED Requirements

### Requirement: Source of truth — файлы

Исходные данные SHALL храниться в файлах: `models.yaml` (реестр), `tasks/T-NNN-<slug>/task.md` (задачи), `answers/T-NNN/*.md` (ответы: `modelA.md` / `modelB.md` от skills либо `<model-id>.md` вручную), `matchups/T-NNN/NNN.json` (вердикты skill судьи), `matchups/general/NNN.json` и `matchups/<task>/NNN.json` (вердикты веб-формы), `settings.yaml` (настройки: статусы тасков и текущая таска). `answers/<task>/slots.json` MUST NOT использоваться как source of truth и MUST NOT существовать. Эти файлы SHALL коммититься в git.

#### Scenario: Git diff ответа

- **WHEN** модель пишет ответ
- **THEN** git diff показывает добавленный Markdown-файл в `answers/T-NNN/`
- **AND** не создаётся `answers/T-NNN/slots.json`

#### Scenario: Git diff вердикта

- **WHEN** записывается новый вердикт
- **THEN** git diff показывает один добавленный JSON-файл
- **AND** `slots.json` не появляется

#### Scenario: Git diff настроек

- **WHEN** пользователь сохраняет настройки через `/settings`
- **THEN** git diff показывает изменённый `settings.yaml` в корне

## ADDED Requirements

### Requirement: Файл настроек settings.yaml

`settings.yaml` в корне репозитория SHALL хранить: `current_task` (id
текущей таски, подставляемой в форму вердикта) и `tasks` — отображение
`id таски -> status` (`active` | `inactive`). Файл SHALL коммититься в
git и MAY редактироваться вручную. При отсутствии файла SHALL
применяться дефолты: все обнаруженные таски активны,
`current_task: general`. При отсутствии `tasks`-записи для обнаруженной
таски она SHALL считаться активной.

#### Scenario: Сохранение настроек

- **WHEN** на странице `/settings` отмечены `general` и `T-001` как активные, текущая — `T-001`
- **THEN** `settings.yaml` содержит `current_task: T-001` и `tasks` со статусами `general: active`, `T-001: active`

#### Scenario: Отсутствующий файл

- **WHEN** `settings.yaml` не существует
- **THEN** сервер работает с дефолтами: все таски активны, `current_task` = `general`

#### Scenario: Новая таска без записи

- **WHEN** в `matchups/` появилась директория новой таски, отсутствующей в `settings.yaml`
- **THEN** таска считается активной до явной отметки
