# matchup-management Specification

## Purpose
Хранение попарных вердиктов: `tools/record_verdict.py` добавляет строку в
единый журнал `data/matchups/journal.jsonl` с явным `task` вида `T-NNN`
(skill-путь и ручной UI через веб-форму). Вердикт — запись результата с
ELO-снэпшотом, без обоснования и идентификации судьи.

## Requirements

### Requirement: Формат вердикта
Каждый вердикт SHALL храниться событием журнала `data/matchups/journal.jsonl`, созданным `tools/record_verdict.py` (или внутренним вызовом `record_verdict` из веб-UI). Событие SHALL содержать: `version`, `seq`, `task`, `matchup`, `model_a`, `model_b`, `model_a_id`, `model_b_id`, `winner` (`a` | `b` | `draw`), `date` (YYYY-MM-DD), `recorded_at` (ISO 8601 с таймзоной, обязательное) и `elo` — ELO-снэпшот обеих моделей (`before`, `after`, `delta`). Судья MUST NOT писать журнал самостоятельно. Поля `model_a` и `model_b` SHALL содержать реальные `id` из `data/models.yaml`. Поле `task` SHALL содержать активную задачу вида `T-NNN`, поле `matchup` — идентификатор вида `T-NNN/NNN`.

#### Scenario: Вердикт от skill судьи
- **WHEN** `@benchmark-judge` выбрал победителя для T-001 (A победила) и пользователь запустил запись с реальными id
- **THEN** `record_verdict.py` добавляет в `data/matchups/journal.jsonl` строку с `matchup: "T-001/001"`
- **AND** строка содержит `model_a: "<real-id-a>"`, `model_b: "<real-id-b>"`, `model_a_id: "<real-id-a>"`, `model_b_id: "<real-id-b>"`, `winner: "a"`, `seq`, `recorded_at` и `elo` с `before`/`after`/`delta`

#### Scenario: Вердикт от веб-сервера
- **WHEN** пользователь записывает вердикт через форму с таском `T-001`
- **THEN** сервер вызывает `record_verdict` и добавляет строку журнала с `matchup` вида `T-001/NNN`
- **AND** событие содержит реальные `model_a_id` и `model_b_id`, `winner`, `elo`-снэпшот, `recorded_at`, `task: T-001`

#### Scenario: Ничья
- **WHEN** судья определяет ничью в `T-001`
- **THEN** поле `winner` = `draw`
- **AND** `record_verdict` сохраняет снэпшот ELO и `recorded_at`

### Requirement: Нумерация файлов
NNN SHALL быть порядковым номером вердикта внутри задачи, начиная с 001; формат номера — минимум 3 цифры (zero-padded, `001`). `matchup` SHALL иметь вид `T-NNN/NNN`, где NNN вычисляется как `max(номеров существующих событий задачи в журнале) + 1`. Повторное использование номера SHALL быть невозможным: события журнала не удаляются и не перезаписываются.

#### Scenario: Первый вердикт в задаче
- **WHEN** в журнале нет событий таска `T-002` и записывается первый вердикт в `T-002`
- **THEN** его `matchup` равен `T-002/001`

#### Scenario: Второй вердикт в задаче
- **WHEN** в журнале есть `T-001/001` и записывается новый вердикт в `T-001`
- **THEN** его `matchup` называется `T-001/002`

#### Scenario: Известный дефект нумерации сервера
- **WHEN** в журнале есть события `T-001/001` и `T-001/003` (номер 002 пропущен)
- **THEN** следующий вердикт получает `matchup` `T-001/004`
- **AND** существующее событие `T-001/003` не перезаписывается

### Requirement: Запись через веб-UI
POST /verdict SHALL принимать `model_a`, `model_b`, `winner` и `task`, проверять их и вызывать `record_verdict` с переданным `task`, добавляя событие журнала с этим таском, и пересчитывать ELO (`generate_index` + `save_index`). Значение `task` SHALL выбираться из списка активных тасок и SHALL быть активной таской вида `T-NNN`. `general` как значение `task` MUST NOT приниматься. Пустое значение `task` MUST NOT проходить валидацию.

#### Scenario: Успешная запись
- **WHEN** пользователь выбирает модели A, B, таск `T-001` и победителя A в веб-форме
- **THEN** система добавляет в журнал событие с `matchup` вида `T-001/NNN`
- **AND** пересчитывает ELO обеих моделей
- **AND** обновляет `data/index.json` и показывает обновлённый leaderboard

#### Scenario: Некорректный таск
- **WHEN** POST /verdict получает пустой `task`, значение `general` или значение с недопустимыми символами
- **THEN** запись отклоняется с ошибкой
- **AND** событие журнала не создаётся

#### Scenario: Запись в неактивную таску отклонена
- **WHEN** пользователь подменяет `task` на `T-002`, помеченную `inactive`
- **THEN** сервер отклоняет запись с ошибкой

### Requirement: Валидация вердикта на сервере

Сервер SHALL проверять: обе модели указаны, модели A и B различны,
`winner` — одно из `a` / `b` / `draw`, обе модели существуют в `data/models.yaml`.
Сервер MUST NOT проверять наличие ответов моделей на задачу и статус
`archived` — таких проверок в `record_verdict` нет (отличие от старых спек).

#### Scenario: Одинаковые модели

- **WHEN** пользователь выбирает модель A = модель B
- **THEN** система отклоняет запись с ошибкой «Модели должны различаться»

#### Scenario: Несуществующая модель

- **WHEN** выбрана модель, не зарегистрированная в `data/models.yaml`
- **THEN** система отклоняет запись с ошибкой «Модель … не найдена»

#### Scenario: Вердикт без ответов (фактическое поведение)

- **WHEN** у моделей нет ответов ни на одну задачу (как первый вердикт `T-001/001` MVP)
- **THEN** сервер всё равно записывает вердикт
- **AND** ELO пересчитывается

### Requirement: Валидация вердикта в skill судьи

Skill `benchmark-judge` SHALL проверять наличие обоих файлов ответов до оценки
и останавливаться с подсказкой нужного прогона, если файла нет. Skill MUST NOT
писать в `data/matchups/journal.jsonl` и MUST NOT записывать вердикт.

#### Scenario: Проверка перед оценкой

- **WHEN** вызван `@benchmark-judge T-001`, но `modelB.md` отсутствует
- **THEN** skill сообщает «Ответ модели B не найден. Запусти @benchmark-run-b сначала»
- **AND** вердикт не создаётся

### Requirement: Анонимность вердикта

Вердикт MUST NOT содержать идентификатора судьи, обоснования или баллов.
Только результат сравнения и ELO-снэпшот.

#### Scenario: Содержимое вердикта

- **WHEN** вердикт записан любым путём
- **THEN** событие журнала содержит: task, matchup, seq, model_a, model_b,
  model_a_id, model_b_id, winner, date, recorded_at, elo
- **AND** не содержит: judge, reasoning, scores

### Requirement: Анонимность и разрешение идентификаторов

Реальные `id` моделей SHALL появляться только в момент записи вердикта. `record_verdict.py` MUST NOT читать `data/answers/<task>/slots.json` и MUST NOT разрешать слоты `modelA`/`modelB`. Судья (skill или manual) MUST NOT читать `data/models.yaml`, `data/index.json`, `data/answers/<task>/slots.json` или любые другие источники, раскрывающие реальные id моделей. Связь слота `modelA`/`modelB` с реальным `id` устанавливается координатором до вызова `record_verdict`.

#### Scenario: Судья не видит реальные id

- **WHEN** `@benchmark-judge` оценивает ответы
- **THEN** skill читает только `task.md`, `modelA.md`, `modelB.md`
- **AND** skill не вызывает `record_verdict.py`
- **AND** `data/answers/T-001/slots.json` не существует
- **AND** реальные id появляются только в строке журнала `data/matchups/journal.jsonl` после ручной записи координатором

#### Scenario: Запись со слотами отклоняется

- **WHEN** `record_verdict.py` получает `model_a: "modelA"` или `model_b: "modelB"`
- **THEN** запись отклоняется с ошибкой
- **AND** `record_verdict.py` не читает `data/answers/<task>/slots.json`

### Requirement: Хронологический порядок

ELO-движок SHALL упорядочивать события журнала по возрастанию `seq` как первичному ключу. Каждое событие SHALL иметь уникальный `seq`; дубликаты `seq` MUST NOT существовать и SHALL фиксироваться `--check` как проблема. `recorded_at` SHALL использоваться только для проверки целостности, а не для определения порядка реплея.

#### Scenario: Два вердикта в один день

- **WHEN** записаны `T-001/001` и `T-001/002` с одинаковой датой
- **THEN** `001` применяется раньше `002`

#### Scenario: Дубликат seq

- **WHEN** в журнале две строки с одинаковым `seq`
- **THEN** `python tools/elo.py --check` сообщает проблему и завершается с ошибкой

### Requirement: Привязка вердикта к активной задаче
Каждый вердикт MUST быть привязан к активной задаче `T-NNN`. Система MUST NOT создавать события с `task`, не являющимся активной задачей вида `T-NNN` (включая `general`).

#### Scenario: Вердикт всегда имеет активный таск
- **WHEN** записывается любой вердикт
- **THEN** его `task` равен `T-NNN`
- **AND** `T-NNN` активна в `data/settings.yaml`

### Requirement: Аннулирование вердикта (tombstone)
`tools/record_verdict.py --void T-NNN/NNN` SHALL аннулировать вердикт добавлением tombstone-события в `data/matchups/journal.jsonl` с полями `void_of: "T-NNN/NNN"` и `reason`; исходное событие SHALL оставаться в журнале. Tombstone-событие MUST NOT создавать игру (участвовать в реплее ELO и заполнять ячейку покрытия) и SHALL получать собственный `seq`. Ссылка на несуществующий вердикт SHALL отклоняться с ошибкой до записи.

#### Scenario: Аннулирование вердикта
- **WHEN** выполняется `python tools/record_verdict.py --void T-001/001 --reason "ошибка записи"`
- **THEN** в журнал добавлено tombstone-событие с `void_of: "T-001/001"`
- **AND** исходная строка `T-001/001` остаётся в журнале
- **AND** ELO пересчитывается без этой игры
- **AND** `python tools/elo.py --check` проходит без проблем

#### Scenario: Несуществующий вердикт
- **WHEN** выполняется `python tools/record_verdict.py --void T-001/999`
- **THEN** команда завершается с ошибкой
- **AND** журнал не меняется
