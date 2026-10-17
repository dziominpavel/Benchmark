## MODIFIED Requirements

### Requirement: Шаг 3 — Судья через skill

Судейство SHALL выполняться skill `benchmark-judge` (`@benchmark-judge T-001`): проверяет наличие обоих слотов `modelA.md` / `modelB.md`, читает `task.md` и оба ответа, при противоречиях сверяется с кодом проекта на `baseline_commit`, оценивает по рубрике задачи и объявляет победителя. Слот определяется только именем файла; поле `model` внутри файла (если осталось от старого формата) SHALL игнорироваться и MUST NOT блокировать оценку. Skill судьи MUST NOT писать в `data/matchups/journal.jsonl`, MUST NOT запускать `python tools/elo.py`, MUST NOT вызывать `tools/record_verdict.py` и MUST NOT иметь доступа к реальным `id` моделей. Судья возвращает только `winner` (`a` | `b` | `draw`); запись вердикта выполняется координатором отдельным шагом.

#### Scenario: Судья выбирает победителя

- **WHEN** оба слота на T-001 готовы и вызван `@benchmark-judge T-001`
- **THEN** skill выводит таблицу оценок, обоснование и победителя (`a` | `b` | `draw`)
- **AND** skill сообщает: "Запишите вердикт через веб-UI или `record_verdict.py` с реальными id"
- **AND** строка журнала не создаётся

#### Scenario: Ничья

- **WHEN** разница итоговых баллов не превышает порог ничьей задачи
- **THEN** skill MAY объявить ничью (`winner: draw`)
- **AND** в остальных случаях выбирает победителя даже при близких оценках

#### Scenario: Нет ответа

- **WHEN** `modelA.md` или `modelB.md` отсутствует
- **THEN** skill останавливается с сообщением какой прогон запустить сначала
- **AND** вердикт не создаётся

### Requirement: Шаг 4 — Запись вердикта и leaderboard
Вердикт SHALL попадать в систему через единую точку записи: `tools/record_verdict.py` с явными реальными идентификаторами моделей и обязательным параметром `--task T-NNN`. Веб-сервер MAY предоставлять UI для ручной записи, который внутри вызывает ту же точку записи. Запись SHALL принимать реальные `id` в аргументах `model_a`/`model_b` (CLI) или в форме (UI), SHALL добавлять строку в `data/matchups/journal.jsonl` (событие с `matchup` вида `<task>/<NNN>`), SHALL сохранять ELO-снэпшот и SHALL пересчитывать `data/index.json`. Запись MUST NOT разрешать слоты `modelA`/`modelB` через `data/answers/<task>/slots.json`. Корзины `general` не существует; каждый вердикт привязан к конкретной задаче `T-NNN`.

#### Scenario: Запись через skill судьи
- **WHEN** `@benchmark-judge` завершил оценку и выбрал победителя
- **THEN** пользователь запускает `python tools/record_verdict.py --task T-001 --model-a <id> --model-b <id> --winner <a|b|draw>`
- **AND** `record_verdict.py` добавляет в `data/matchups/journal.jsonl` событие с `task: T-001` и `matchup: T-001/NNN`
- **AND** `record_verdict.py` пересчитывает `data/index.json`

#### Scenario: Запись через веб-UI
- **WHEN** пользователь выбрал модель A, модель B, таск `T-001` и победителя в форме
- **THEN** сервер вызывает `record_verdict` с `task: T-001` и реальными `id`
- **AND** создаётся событие журнала `T-001/NNN`
- **AND** сервер пересчитывает ELO и показывает обновлённый leaderboard

#### Scenario: Попытка записать слот вместо id
- **WHEN** пользователь вызывает `record_verdict.py --task T-001 --model-a modelA --model-b modelB --winner a`
- **THEN** инструмент возвращает ошибку: "Модель A не разрешена: 'modelA'"
- **AND** вердикт не создаётся

### Requirement: Новая задача

Новая задача создаётся копированием `data/tasks/_TEMPLATE.md` под следующим номером,
когда текущая исчерпана. Модели SHALL переносить текущий ELO на новую задачу
(сброса нет); ответы пишутся в `data/answers/T-NNN/`, вердикты skill-пути попадают
строками журнала с `task: T-NNN`.

#### Scenario: Переход к новой задаче

- **WHEN** T-001 исчерпана и создана T-002
- **THEN** модели не сбрасывают ELO
- **AND** вердикты по T-002 продолжают обновлять тот же глобальный рейтинг
