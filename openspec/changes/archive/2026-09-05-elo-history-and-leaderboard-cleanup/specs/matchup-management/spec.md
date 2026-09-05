# matchup-management Specification

## MODIFIED Requirements

### Requirement: Формат вердикта

Каждый вердикт SHALL храниться в отдельном JSON-файле, созданном `tools/record_verdict.py` (или внутренним вызовом `record_verdict` из веб-UI). Файл SHALL содержать: `version`, `seq`, `task`, `model_a`, `model_b`, `model_a_id`, `model_b_id`, `winner` (`a` | `b` | `draw`), `date` (YYYY-MM-DD), `recorded_at` (ISO 8601 с таймзоной, обязательное) и `elo` — ELO-снэпшот обеих моделей (`before`, `after`, `delta`). Судья MUST NOT писать файл самостоятельно.

#### Scenario: Вердикт от skill судьи

- **WHEN** `@benchmark-judge` выбрал победителя для T-001 (A победила)
- **THEN** `record_verdict.py` создаёт `matchups/T-001/001.json`
- **AND** файл содержит `model_a: "modelA"`, `model_b: "modelB"`, `model_a_id: "<real-id>"`, `model_b_id: "<real-id>"`, `winner: "a"`, `seq`, `recorded_at` и `elo` с `before`/`after`/`delta`

#### Scenario: Вердикт от веб-сервера

- **WHEN** пользователь записывает вердикт через форму
- **THEN** сервер вызывает `record_verdict` и создаёт `matchups/general/NNN.json`
- **AND** файл содержит реальные `model_a_id` и `model_b_id`, `winner`, `elo`-снэпшот, `recorded_at`

#### Scenario: Ничья

- **WHEN** судья определяет ничью
- **THEN** поле `winner` = `draw`
- **AND** `record_verdict` сохраняет снэпшот ELO и `recorded_at`

### Requirement: Хронологический порядок

ELO-движок SHALL упорядочивать вердикты с `seq` по возрастанию `seq` как первичному ключу. Для вердиктов без `seq` (legacy) порядок SHALL определяться парой (`date`, `_matchup_id`). `recorded_at` SHALL использоваться только для проверки целостности, а не для определения порядка реплея.

#### Scenario: Два вердикта в один день

- **WHEN** записаны `T-001/001` и `T-001/002` с одинаковой датой
- **THEN** `001` применяется раньше `002`

### Requirement: Нумерация файлов

NNN SHALL быть порядковым номером вердикта внутри директории задачи/корзины, начиная с 001, формат — zero-padded 3 цифры (`001.json`). Номер SHALL вычисляться как `max(существующих номеров) + 1`. Удаление промежуточного файла не SHALL приводить к перезаписи существующего.

#### Scenario: Второй вердикт в корзине general

- **WHEN** в `matchups/general/` есть `001.json` и записывается новый вердикт
- **THEN** файл называется `matchups/general/002.json`

#### Scenario: Известный дефект нумерации сервера

- **WHEN** в `matchups/general/` есть `001.json` и `003.json`
- **THEN** следующий вердикт называется `matchups/general/004.json`
- **AND** существующий `003.json` не перезаписывается
