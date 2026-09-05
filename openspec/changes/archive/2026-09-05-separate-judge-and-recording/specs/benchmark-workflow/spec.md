## MODIFIED Requirements

### Requirement: Шаг 3 — Судья через skill

Судейство SHALL выполняться skill `benchmark-judge` (`@benchmark-judge T-001`):
проверяет наличие обоих ответов, читает `task.md` и оба ответа, при противоречиях
сверяется с кодом проекта на `baseline_commit`, оценивает по 5 критериям
(полнота, точность, качество кода, структура, глубина, каждый 1–10, итого /50),
объявляет победителя и передаёт результат для записи. Судья MUST NOT писать
`matchups/T-NNN/NNN.json`, MUST NOT запускать `python tools/elo.py` и MUST NOT
иметь доступа к `answers/T-NNN/slots.json` или реальным id моделей.

#### Scenario: Судья выбирает победителя

- **WHEN** оба ответа на T-001 готовы и вызван `@benchmark-judge T-001`
- **THEN** skill выводит таблицу оценок, обоснование и победителя (`a` | `b` | `draw`)
- **AND** skill передаёт результат в `tools/record_verdict.py --task T-001 --winner <a|b|draw>`
- **AND** `record_verdict.py` создаёт `matchups/T-001/NNN.json` и пересчитывает ELO

#### Scenario: Ничья

- **WHEN** разница итоговых баллов ≤ 2
- **THEN** skill MAY объявить ничью (`winner: draw`)
- **AND** в остальных случаях выбирает победителя даже при близких оценках

#### Scenario: Нет ответа

- **WHEN** `modelA.md` или `modelB.md` отсутствует
- **THEN** skill останавливается с сообщением какой прогон запустить сначала
- **AND** вердикт не создаётся

### Requirement: Шаг 3 (альтернатива) — Судья вручную

Пользователь MAY судить вручную: берёт шаблон из `docs/judge-prompt.md`, даёт любой
LLM содержимое `task.md` и двух ответов анонимно (Answer 1 / Answer 2) и читает
вердикт в чате. Судья в чате SHALL предоставлять только оценки, победителя и
обоснование; он MUST NOT создавать файлов и MUST NOT считать ELO. Пользователь
сам записывает результат через `tools/record_verdict.py` или веб-UI (корзина
`general`, см. matchup-management).

#### Scenario: Ручное судейство

- **WHEN** пользователь даёт судье `task.md` + два ответа по шаблону judge-prompt
- **THEN** судья отвечает: оценки, победитель, обоснование
- **AND** пользователь переносит итог в `record_verdict.py` или форму на `localhost:5000`
- **AND** инструмент записи разрешает слоты, сохраняет вердикт и пересчитывает ELO

### Requirement: Шаг 4 — Запись вердикта и leaderboard

Вердикт SHALL попадать в систему через единую точку записи: `tools/record_verdict.py`
(корзина `T-NNN` для skill-пути, корзина `general` для ручного ввода). Веб-сервер
MAY предоставлять UI для ручной записи, который внутри вызывает ту же точку записи.
Запись SHALL разрешать слоты `modelA`/`modelB` через `answers/<task>/slots.json`,
SHALL писать `matchups/<task>/<NNN>.json`, SHALL сохранять ELO-снэпшот и SHALL
пересчитывать `index.json`. Leaderboard доступен на `localhost:5000` и статичным
`leaderboard.html`.

#### Scenario: Запись через skill судьи

- **WHEN** `@benchmark-judge` завершил оценку и выбрал победителя
- **THEN** `record_verdict.py` создаёт `matchups/T-001/NNN.json` с `task: T-001`
- **AND** `record_verdict.py` пересчитывает `index.json`

#### Scenario: Запись через веб-UI

- **WHEN** пользователь выбрал модель A, модель B и победителя в форме
- **THEN** сервер вызывает `record_verdict` с `task: general`
- **AND** создаётся `matchups/general/NNN.json`
- **AND** сервер пересчитывает ELO и показывает обновлённый leaderboard
