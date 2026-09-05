# matchup-management Specification

## Purpose
Хранение попарных вердиктов двумя путями MVP: `tools/record_verdict.py` пишет
`matchups/<task-id>/NNN.json` (skill-путь) и `matchups/general/NNN.json`
(ручной UI) с фиксированным `task: general`. Вердикт — запись результата с
ELO-снэпшотом, без обоснования и идентификации судьи.

## Requirements

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

### Requirement: Нумерация файлов

NNN SHALL быть порядковым номером вердикта внутри директории задачи/корзины, начиная с 001, формат — zero-padded 3 цифры (`001.json`). Номер SHALL вычисляться как `max(существующих номеров) + 1`. Удаление промежуточного файла не SHALL приводить к перезаписи существующего.

#### Scenario: Второй вердикт в корзине general

- **WHEN** в `matchups/general/` есть `001.json` и записывается новый вердикт
- **THEN** файл называется `matchups/general/002.json`

#### Scenario: Известный дефект нумерации сервера

- **WHEN** в `matchups/general/` есть `001.json` и `003.json`
- **THEN** следующий вердикт называется `matchups/general/004.json`
- **AND** существующий `003.json` не перезаписывается

### Requirement: Запись через веб-UI

POST /verdict SHALL принимать `model_a`, `model_b`, `winner`, проверять их,
вызывать `record_verdict` с `task: general`, писать файл в `matchups/general/`
и пересчитывать ELO (`generate_index` + `save_index`). Выбор задачи в форме
отсутствует — корзина всегда `general`.

#### Scenario: Успешная запись

- **WHEN** пользователь выбирает модели A, B и победителя A в веб-форме
- **THEN** система создаёт `matchups/general/NNN.json`
- **AND** пересчитывает ELO обеих моделей
- **AND** обновляет `index.json` и показывает обновлённый leaderboard

### Requirement: Валидация вердикта на сервере

Сервер SHALL проверять: обе модели указаны, модели A и B различны,
`winner` — одно из `a` / `b` / `draw`, обе модели существуют в `models.yaml`.
Сервер MUST NOT проверять наличие ответов моделей на задачу и статус
`archived` — таких проверок в `record_verdict` нет (отличие от старых спек).

#### Scenario: Одинаковые модели

- **WHEN** пользователь выбирает модель A = модель B
- **THEN** система отклоняет запись с ошибкой «Модели должны различаться»

#### Scenario: Несуществующая модель

- **WHEN** выбрана модель, не зарегистрированная в `models.yaml`
- **THEN** система отклоняет запись с ошибкой «Модель … не найдена»

#### Scenario: Вердикт без ответов (фактическое поведение)

- **WHEN** у моделей нет ответов ни на одну задачу (как вердикт `general/001.json` MVP)
- **THEN** сервер всё равно записывает вердикт
- **AND** ELO пересчитывается

### Requirement: Валидация вердикта в skill судьи

Skill `benchmark-judge` SHALL проверять наличие обоих файлов ответов до оценки
и останавливаться с подсказкой нужного прогона, если файла нет. Skill MUST NOT
создавать папку `matchups/T-NNN/` и MUST NOT записывать вердикт.

#### Scenario: Проверка перед оценкой

- **WHEN** вызван `@benchmark-judge T-001`, но `modelB.md` отсутствует
- **THEN** skill сообщает «Ответ модели B не найден. Запусти @benchmark-run-b сначала»
- **AND** вердикт не создаётся

### Requirement: Анонимность вердикта

Вердикт MUST NOT содержать идентификатора судьи, обоснования или баллов.
Только результат сравнения и ELO-снэпшот.

#### Scenario: Содержимое вердикта

- **WHEN** вердикт записан любым путём
- **THEN** файл содержит: task, model_a, model_b, model_a_id, model_b_id,
  winner, date, recorded_at, elo
- **AND** не содержит: judge, reasoning, scores

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

### Requirement: Хронологический порядок

ELO-движок SHALL упорядочивать вердикты с `seq` по возрастанию `seq` как первичному ключу. Для вердиктов без `seq` (legacy) порядок SHALL определяться парой (`date`, `_matchup_id`). `recorded_at` SHALL использоваться только для проверки целостности, а не для определения порядка реплея.

#### Scenario: Два вердикта в один день

- **WHEN** записаны `T-001/001` и `T-001/002` с одинаковой датой
- **THEN** `001` применяется раньше `002`
