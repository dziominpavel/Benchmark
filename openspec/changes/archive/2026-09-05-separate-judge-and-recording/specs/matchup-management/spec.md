## MODIFIED Requirements

### Requirement: Формат вердикта

Каждый вердикт SHALL храниться в отдельном JSON-файле, созданном
`tools/record_verdict.py` (или внутренним вызовом record_verdict из веб-UI).
Файл SHALL содержать: `version`, `seq`, `task`, `model_a`, `model_b`,
`model_a_id`, `model_b_id`, `winner` (`a` | `b` | `draw`), `date` (YYYY-MM-DD),
`recorded_at` (ISO 8601 с таймзоной) и `elo` — ELO-снэпшот обеих моделей
(`before`, `after`, `delta`). Судья MUST NOT писать файл самостоятельно.

#### Scenario: Вердикт от skill судьи

- **WHEN** `@benchmark-judge` выбрал победителя для T-001 (A победила)
- **THEN** `record_verdict.py` создаёт `matchups/T-001/001.json`
- **AND** файл содержит `model_a: "modelA"`, `model_b: "modelB"`,
  `model_a_id: "<real-id>"`, `model_b_id: "<real-id>"`, `winner: "a"`,
  `seq`, `recorded_at` и `elo` с `before`/`after`/`delta`

#### Scenario: Вердикт от веб-сервера

- **WHEN** пользователь записывает вердикт через форму
- **THEN** сервер вызывает `record_verdict` и создаёт `matchups/general/NNN.json`
- **AND** файл содержит реальные `model_a_id` и `model_b_id`, `winner`, `elo`-снэпшот

#### Scenario: Ничья

- **WHEN** судья определяет ничью
- **THEN** поле `winner` = `draw`
- **AND** `record_verdict` сохраняет снэпшот ELO

### Requirement: Валидация вердикта в skill судьи

Skill `benchmark-judge` SHALL проверять наличие обоих файлов ответов до оценки
и останавливаться с подсказкой нужного прогона, если файла нет. Skill MUST NOT
создавать папку `matchups/T-NNN/` и MUST NOT записывать вердикт.

#### Scenario: Проверка перед оценкой

- **WHEN** вызван `@benchmark-judge T-001`, но `modelB.md` отсутствует
- **THEN** skill сообщает «Ответ модели B не найден. Запусти @benchmark-run-b сначала»
- **AND** вердикт не создаётся

## ADDED Requirements

### Requirement: Анонимность и разрешение слотов

Слоты `modelA`/`modelB` SHALL разрешаться в реальные `id` из `models.yaml`
только в момент записи вердикта через `record_verdict.py`. `record_verdict.py`
MAY читать `answers/<task>/slots.json` для разрешения. Судья (skill или manual)
MUST NOT читать `slots.json`, `models.yaml`, `index.json` или любые другие
источники, раскрывающие реальные id моделей.

#### Scenario: Судья не видит реальные id

- **WHEN** `@benchmark-judge` оценивает ответы
- **THEN** skill читает только `task.md`, `modelA.md`, `modelB.md`
- **AND** skill не читает `answers/T-001/slots.json`
- **AND** реальные id появляются только в `matchups/T-001/NNN.json` после записи
