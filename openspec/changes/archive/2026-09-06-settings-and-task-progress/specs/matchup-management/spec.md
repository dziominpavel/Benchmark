## MODIFIED Requirements

### Requirement: Формат вердикта

Каждый вердикт SHALL храниться в отдельном JSON-файле, созданном `tools/record_verdict.py` (или внутренним вызовом `record_verdict` из веб-UI). Файл SHALL содержать: `version`, `seq`, `task`, `model_a`, `model_b`, `model_a_id`, `model_b_id`, `winner` (`a` | `b` | `draw`), `date` (YYYY-MM-DD), `recorded_at` (ISO 8601 с таймзоной, обязательное) и `elo` — ELO-снэпшот обеих моделей (`before`, `after`, `delta`). Судья MUST NOT писать файл самостоятельно. Поля `model_a` и `model_b` SHALL содержать реальные `id` из `models.yaml`.

#### Scenario: Вердикт от skill судьи

- **WHEN** `@benchmark-judge` выбрал победителя для T-001 (A победила) и пользователь запустил запись с реальными id
- **THEN** `record_verdict.py` создаёт `matchups/T-001/001.json`
- **AND** файл содержит `model_a: "<real-id-a>"`, `model_b: "<real-id-b>"`, `model_a_id: "<real-id-a>"`, `model_b_id: "<real-id-b>"`, `winner: "a"`, `seq`, `recorded_at` и `elo` с `before`/`after`/`delta`

#### Scenario: Вердикт от веб-сервера

- **WHEN** пользователь записывает вердикт через форму с таском `<task>`
- **THEN** сервер вызывает `record_verdict` и создаёт `matchups/<task>/NNN.json`
- **AND** файл содержит реальные `model_a_id` и `model_b_id`, `winner`, `elo`-снэпшот, `recorded_at`

#### Scenario: Ничья

- **WHEN** судья определяет ничью
- **THEN** поле `winner` = `draw`
- **AND** `record_verdict` сохраняет снэпшот ELO и `recorded_at`

### Requirement: Запись через веб-UI

POST /verdict SHALL принимать `model_a`, `model_b`, `winner` и `task`,
проверять их и вызывать `record_verdict` с переданным `task`, записывая
файл в `matchups/<task>/`, и пересчитывать ELO (`generate_index` +
`save_index`). Значение `task` SHALL быть непустым и удовлетворять
валидации `record_verdict` (`[A-Za-z0-9_-]+`); значение по умолчанию в
форме — `current_task` из `settings.yaml`.

#### Scenario: Успешная запись

- **WHEN** пользователь выбирает модели A, B, таск `T-001` и победителя A в веб-форме
- **THEN** система создаёт `matchups/T-001/NNN.json`
- **AND** пересчитывает ELO обеих моделей
- **AND** обновляет `index.json` и показывает обновлённый leaderboard

#### Scenario: Некорректный таск

- **WHEN** POST /verdict получает пустой `task` или значение с недопустимыми символами
- **THEN** запись отклоняется с ошибкой
- **AND** файл вердикта не создаётся
