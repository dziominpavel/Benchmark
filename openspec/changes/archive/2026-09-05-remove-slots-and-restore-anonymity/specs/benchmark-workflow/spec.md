## MODIFIED Requirements

### Requirement: Шаг 3 — Судья через skill

Судейство SHALL выполняться skill `benchmark-judge` (`@benchmark-judge T-001`): проверяет наличие обоих ответов, читает `task.md` и оба ответа, при противоречиях сверяется с кодом проекта на `baseline_commit`, оценивает по 5 критериям (полнота, точность, качество кода, структура, глубина, каждый 1–10, итого /50) и объявляет победителя. Skill судьи MUST NOT писать `matchups/T-NNN/NNN.json`, MUST NOT запускать `python tools/elo.py`, MUST NOT вызывать `tools/record_verdict.py` и MUST NOT иметь доступа к реальным `id` моделей. Судья возвращает только `winner` (`a` | `b` | `draw`); запись вердикта выполняется координатором отдельным шагом.

#### Scenario: Судья выбирает победителя

- **WHEN** оба ответа на T-001 готовы и вызван `@benchmark-judge T-001`
- **THEN** skill выводит таблицу оценок, обоснование и победителя (`a` | `b` | `draw`)
- **AND** skill сообщает: "Запишите вердикт через веб-UI или `record_verdict.py` с реальными id"
- **AND** matchups-файл не создаётся

#### Scenario: Ничья

- **WHEN** разница итоговых баллов ≤ 2
- **THEN** skill MAY объявить ничью (`winner: draw`)
- **AND** в остальных случаях выбирает победителя даже при близких оценках

#### Scenario: Нет ответа

- **WHEN** `modelA.md` или `modelB.md` отсутствует
- **THEN** skill останавливается с сообщением какой прогон запустить сначала
- **AND** вердикт не создаётся

### Requirement: Шаг 3 (альтернатива) — Судья вручную

Пользователь MAY судить вручную: берёт шаблон из `docs/judge-prompt.md`, даёт любой LLM содержимое `task.md` и двух ответов анонимно (Answer 1 / Answer 2) и читает вердикт в чате. Судья в чате SHALL предоставлять только оценки, победителя и обоснование; он MUST NOT создавать файлов и MUST NOT считать ELO. Пользователь сам записывает результат через `tools/record_verdict.py` с явными реальными `id` или веб-UI.

#### Scenario: Ручное судейство

- **WHEN** пользователь даёт судье `task.md` + два ответа по шаблону judge-prompt
- **THEN** судья отвечает: оценки, победитель, обоснование
- **AND** пользователь переносит итог в `record_verdict.py --task T-001 --model-a <id> --model-b <id> --winner <a|b|draw>` или форму на `localhost:5000`

### Requirement: Шаг 4 — Запись вердикта и leaderboard

Вердикт SHALL попадать в систему через единую точку записи: `tools/record_verdict.py` (корзина `T-NNN` для skill-пути, корзина `general` для ручного ввода) с явными реальными идентификаторами моделей. Веб-сервер MAY предоставлять UI для ручной записи, который внутри вызывает ту же точку записи. Запись SHALL принимать реальные `id` в аргументах `model_a`/`model_b` (CLI) или в форме (UI), SHALL писать `matchups/<task>/<NNN>.json`, SHALL сохранять ELO-снэпшот и SHALL пересчитывать `index.json`. Запись MUST NOT разрешать слоты `modelA`/`modelB` через `answers/<task>/slots.json`.

#### Scenario: Запись через skill судьи

- **WHEN** `@benchmark-judge` завершил оценку и выбрал победителя
- **THEN** пользователь запускает `python tools/record_verdict.py --task T-001 --model-a <id> --model-b <id> --winner <a|b|draw>`
- **AND** `record_verdict.py` создаёт `matchups/T-001/NNN.json` с `task: T-001`
- **AND** `record_verdict.py` пересчитывает `index.json`

#### Scenario: Запись через веб-UI

- **WHEN** пользователь выбрал модель A, модель B и победителя в форме
- **THEN** сервер вызывает `record_verdict` с `task: general` и реальными `id`
- **AND** создаётся `matchups/general/NNN.json`
- **AND** сервер пересчитывает ELO и показывает обновлённый leaderboard

#### Scenario: Попытка записать слот вместо id

- **WHEN** пользователь вызывает `record_verdict.py --task T-001 --model-a modelA --model-b modelB --winner a`
- **THEN** инструмент возвращает ошибку: "Модель A не разрешена: 'modelA'"
- **AND** вердикт не создаётся
