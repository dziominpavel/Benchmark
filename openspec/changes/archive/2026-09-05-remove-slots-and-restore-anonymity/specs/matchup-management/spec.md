## MODIFIED Requirements

### Requirement: Формат вердикта

Каждый вердикт SHALL храниться в отдельном JSON-файле, созданном `tools/record_verdict.py` (или внутренним вызовом `record_verdict` из веб-UI). Файл SHALL содержать: `version`, `seq`, `task`, `model_a`, `model_b`, `model_a_id`, `model_b_id`, `winner` (`a` | `b` | `draw`), `date` (YYYY-MM-DD), `recorded_at` (ISO 8601 с таймзоной, обязательное) и `elo` — ELO-снэпшот обеих моделей (`before`, `after`, `delta`). Судья MUST NOT писать файл самостоятельно. Поля `model_a` и `model_b` SHALL содержать реальные `id` из `models.yaml`.

#### Scenario: Вердикт от skill судьи

- **WHEN** `@benchmark-judge` выбрал победителя для T-001 (A победила) и пользователь запустил запись с реальными id
- **THEN** `record_verdict.py` создаёт `matchups/T-001/001.json`
- **AND** файл содержит `model_a: "<real-id-a>"`, `model_b: "<real-id-b>"`, `model_a_id: "<real-id-a>"`, `model_b_id: "<real-id-b>"`, `winner: "a"`, `seq`, `recorded_at` и `elo` с `before`/`after`/`delta`

#### Scenario: Вердикт от веб-сервера

- **WHEN** пользователь записывает вердикт через форму
- **THEN** сервер вызывает `record_verdict` и создаёт `matchups/general/NNN.json`
- **AND** файл содержит реальные `model_a_id` и `model_b_id`, `winner`, `elo`-снэпшот, `recorded_at`

#### Scenario: Ничья

- **WHEN** судья определяет ничью
- **THEN** поле `winner` = `draw`
- **AND** `record_verdict` сохраняет снэпшот ELO и `recorded_at`

### Requirement: Анонимность и разрешение идентификаторов

Реальные `id` моделей SHALL появляться только в момент записи вердикта. `record_verdict.py` MUST NOT читать `answers/<task>/slots.json` и MUST NOT разрешать слоты `modelA`/`modelB`. Судья (skill или manual) MUST NOT читать `models.yaml`, `index.json`, `answers/<task>/slots.json` или любые другие источники, раскрывающие реальные id моделей. Связь слота `modelA`/`modelB` с реальным `id` устанавливается координатором до вызова `record_verdict`.

#### Scenario: Судья не видит реальные id

- **WHEN** `@benchmark-judge` оценивает ответы
- **THEN** skill читает только `task.md`, `modelA.md`, `modelB.md`
- **AND** skill не вызывает `record_verdict.py`
- **AND** `answers/T-001/slots.json` не существует
- **AND** реальные id появляются только в `matchups/T-001/NNN.json` после ручной записи координатором

#### Scenario: Запись со слотами отклоняется

- **WHEN** `record_verdict.py` получает `model_a: "modelA"` или `model_b: "modelB"`
- **THEN** запись отклоняется с ошибкой
- **AND** `record_verdict.py` не читает `answers/<task>/slots.json`
