## MODIFIED Requirements

### Requirement: Корень данных — data/
Все файлы данных SHALL храниться под директорией `data/` в корне репозитория: `data/models.yaml`, `data/lookups.yaml`, `data/judges.yaml`, `data/settings.yaml`, `data/answer_flags.yaml`, `data/index.json`, `data/tasks/`, `data/answers/`, `data/matchups/` (включая `data/matchups/state.json`), `data/logs/`. Код SHALL находиться в `tools/`, лаунчеры (`start.bat`, `stop.bat`, `launch.vbs`) — в корне. Файлы данных вне `data/` MUST NOT использоваться.

#### Scenario: Структура корня
- **WHEN** пользователь открывает корень репозитория
- **THEN** все данные прогонов находятся в `data/`
- **AND** в корне нет `tasks/`, `answers/`, `matchups/`, `models.yaml`, `settings.yaml`, `index.json`

### Requirement: Source of truth — файлы
Исходные данные SHALL храниться в файлах: `data/models.yaml` (реестр), `data/lookups.yaml` (справочники агентов и компаний), `data/tasks/T-NNN-<slug>/task.md` (задачи), `data/answers/T-NNN/modelA.md` / `modelB.md` (только два транзитных слота текущего судейства), `data/matchups/T-NNN/NNN.json` (вердикты), `data/settings.yaml` (настройки: статусы тасок и текущая таска), `data/answer_flags.yaml` (ручной учёт наличия ответов, см. `answer-coverage`). Файлы `data/answers/<task>/<model-id>.md` в проекте MUST NOT использоваться (тексты ответов хранятся вне проекта). `data/matchups/general/` и `data/matchups/<non-T-NNN>/` MUST NOT использоваться. `data/answers/<task>/slots.json` MUST NOT использоваться. Эти файлы SHALL коммититься в git.

#### Scenario: Git diff ответа
- **WHEN** модель пишет ответ
- **THEN** git diff показывает изменённый Markdown-файл `data/answers/T-NNN/modelA.md` или `modelB.md`
- **AND** не создаётся `data/answers/T-NNN/slots.json`

#### Scenario: Git diff вердикта
- **WHEN** записывается новый вердикт
- **THEN** git diff показывает один добавленный JSON-файл в `data/matchups/T-001/`
- **AND** `data/matchups/general/` не появляется

#### Scenario: Git diff настроек
- **WHEN** пользователь сохраняет настройки через `/settings`
- **THEN** git diff показывает изменённый `data/settings.yaml`
- **AND** в нём нет ключа `general`

#### Scenario: Git diff справочников
- **WHEN** координатор добавляет значение в секции «Справочники»
- **THEN** git diff показывает изменённый `data/lookups.yaml`
