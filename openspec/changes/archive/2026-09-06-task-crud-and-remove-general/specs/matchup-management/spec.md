# matchup-management Specification

## MODIFIED Requirements

### Requirement: Запись через веб-UI
POST /verdict SHALL принимать `model_a`, `model_b`, `winner` и `task`, проверять их и вызывать `record_verdict` с переданным `task`, записывая файл в `matchups/<task>/`, и пересчитывать ELO (`generate_index` + `save_index`). Значение `task` SHALL выбираться из списка активных тасок и SHALL быть активной таской вида `T-NNN`. `general` как значение `task` MUST NOT приниматься. Пустое значение `task` MUST NOT проходить валидацию.

#### Scenario: Успешная запись
- **WHEN** пользователь выбирает модели A, B, таск `T-001` и победителя A в веб-форме
- **THEN** система создаёт `matchups/T-001/NNN.json`
- **AND** пересчитывает ELO обеих моделей
- **AND** обновляет `index.json` и показывает обновлённый leaderboard

#### Scenario: Некорректный таск
- **WHEN** POST /verdict получает пустой `task`, значение `general` или значение с недопустимыми символами
- **THEN** запись отклоняется с ошибкой
- **AND** файл вердикта не создаётся

#### Scenario: Запись в неактивную таску отклонена
- **WHEN** пользователь подменяет `task` на `T-002`, помеченную `inactive`
- **THEN** сервер отклоняет запись с ошибкой

### Requirement: Формат вердикта
Каждый вердикт SHALL храниться в отдельном JSON-файле, созданном `tools/record_verdict.py` (или внутренним вызовом `record_verdict` из веб-UI). Файл SHALL содержать: `version`, `seq`, `task`, `model_a`, `model_b`, `model_a_id`, `model_b_id`, `winner` (`a` | `b` | `draw`), `date` (YYYY-MM-DD), `recorded_at` (ISO 8601 с таймзоной, обязательное) и `elo` — ELO-снэпшот обеих моделей (`before`, `after`, `delta`). Судья MUST NOT писать файл самостоятельно. Поля `model_a` и `model_b` SHALL содержать реальные `id` из `models.yaml`. Поле `task` SHALL содержать активную задачу вида `T-NNN`.

#### Scenario: Вердикт от skill судьи
- **WHEN** `@benchmark-judge` выбрал победителя для T-001 (A победила) и пользователь запустил запись с реальными id
- **THEN** `record_verdict.py` создаёт `matchups/T-001/001.json`
- **AND** файл содержит `model_a: "<real-id-a>"`, `model_b: "<real-id-b>"`, `model_a_id: "<real-id-a>"`, `model_b_id: "<real-id-b>"`, `winner: "a"`, `seq`, `recorded_at` и `elo` с `before`/`after`/`delta`

#### Scenario: Вердикт от веб-сервера
- **WHEN** пользователь записывает вердикт через форму с таском `T-001`
- **THEN** сервер вызывает `record_verdict` и создаёт `matchups/T-001/NNN.json`
- **AND** файл содержит реальные `model_a_id` и `model_b_id`, `winner`, `elo`-снэпшот, `recorded_at`, `task: T-001`

#### Scenario: Ничья
- **WHEN** судья определяет ничью в `T-001`
- **THEN** поле `winner` = `draw`
- **AND** `record_verdict` сохраняет снэпшот ELO и `recorded_at`

### Requirement: Нумерация файлов
NNN SHALL быть порядковым номером вердикта внутри директории задачи, начиная с 001, формат — zero-padded 3 цифры (`001.json`). Номер SHALL вычисляться как `max(существующих номеров) + 1`. Удаление промежуточного файла не SHALL приводить к перезаписи существующего.

#### Scenario: Второй вердикт в корзине general
- **WHEN** в `matchups/T-001/` есть `001.json` и записывается новый вердикт
- **THEN** файл называется `matchups/T-001/002.json`

#### Scenario: Известный дефект нумерации сервера
- **WHEN** в `matchups/T-001/` есть `001.json` и `003.json`
- **THEN** следующий вердикт называется `matchups/T-001/004.json`
- **AND** существующий `003.json` не перезаписывается

## ADDED Requirements

### Requirement: Привязка вердикта к активной задаче
Каждый вердикт MUST быть привязан к активной задаче `T-NNN`. Система MUST NOT создавать вердикты в `matchups/general/` или других не-T-NNN директориях.

#### Scenario: Вердикт всегда имеет активный таск
- **WHEN** записывается любой вердикт
- **THEN** он хранится в `matchups/T-NNN/`
- **AND** значение `task` равно `T-NNN`
- **AND** `T-NNN` активна в `settings.yaml`
