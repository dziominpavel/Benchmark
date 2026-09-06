# matchup-management Specification

## Purpose
Хранение попарных вердиктов: `tools/record_verdict.py` пишет
`matchups/<task-id>/NNN.json` с явным `task` вида `T-NNN` (skill-путь и
ручной UI через веб-форму). Вердикт — запись результата с
ELO-снэпшотом, без обоснования и идентификации судьи.

## Requirements

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

#### Scenario: Второй вердикт в задаче
- **WHEN** в `matchups/T-001/` есть `001.json` и записывается новый вердикт
- **THEN** файл называется `matchups/T-001/002.json`

#### Scenario: Известный дефект нумерации сервера
- **WHEN** в `matchups/T-001/` есть `001.json` и `003.json`
- **THEN** следующий вердикт называется `matchups/T-001/004.json`
- **AND** существующий `003.json` не перезаписывается

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

- **WHEN** у моделей нет ответов ни на одну задачу (как первый вердикт `T-001/001.json` MVP)
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

### Requirement: Хронологический порядок

ELO-движок SHALL упорядочивать вердикты с `seq` по возрастанию `seq` как первичному ключу. Для вердиктов без `seq` (legacy) порядок SHALL определяться парой (`date`, `_matchup_id`). `recorded_at` SHALL использоваться только для проверки целостности, а не для определения порядка реплея.

#### Scenario: Два вердикта в один день

- **WHEN** записаны `T-001/001` и `T-001/002` с одинаковой датой
- **THEN** `001` применяется раньше `002`

### Requirement: Привязка вердикта к активной задаче
Каждый вердикт MUST быть привязан к активной задаче `T-NNN`. Система MUST NOT создавать вердикты в `matchups/general/` или других не-T-NNN директориях.

#### Scenario: Вердикт всегда имеет активный таск
- **WHEN** записывается любой вердикт
- **THEN** он хранится в `matchups/T-NNN/`
- **AND** значение `task` равно `T-NNN`
- **AND** `T-NNN` активна в `settings.yaml`
