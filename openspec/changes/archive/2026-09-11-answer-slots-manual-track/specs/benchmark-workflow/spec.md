## MODIFIED Requirements

### Requirement: Шаг 2 — Прогон моделей через run-a / run-b

Прогоны SHALL выполняться skills `benchmark-run-a` и `benchmark-run-b`. Каждый skill сам читает task.md, делает `git checkout <baseline_commit>` в проекте-референсе, анализирует код и пишет ответ в фиксированный файл: `data/answers/<task-id>/modelA.md` либо `data/answers/<task-id>/modelB.md`. Front matter ответа SHALL содержать только `{task, date}` без поля `model`; слот определяется именем файла. После работы skill возвращает проект командой `git checkout . && git clean -fd`. Участник не записывает свой реальный `id` нигде. Тексты ответов для длительного хранения находятся вне проекта; в проекте остаются только два транзитных слота текущего судейства, а наличие ответов по всем моделям ведётся ручным учётом (см. `answer-coverage`).

#### Scenario: Прогон модели A

- **WHEN** пользователь вызывает `@benchmark-run-a T-001`
- **THEN** skill пишет `data/answers/T-001/modelA.md` с front matter `{task, date}` без поля `model`

#### Scenario: Прогон модели B

- **WHEN** пользователь вызывает `@benchmark-run-b T-001`
- **THEN** skill пишет `data/answers/T-001/modelB.md` с front matter `{task, date}` без поля `model`

#### Scenario: Прогон произвольной модели из реестра

- **WHEN** нужно прогнать модель с id из `data/models.yaml` (например `opencode-mimo-v2-5-free`)
- **THEN** текст ответа хранится вне проекта
- **AND** в проект для судейства копируются только два слота `modelA.md` / `modelB.md`
- **AND** координатор отмечает наличие ответа в ручном учёте

### Requirement: Шаг 3 — Судья через skill

Судейство SHALL выполняться skill `benchmark-judge` (`@benchmark-judge T-001`): проверяет наличие обоих слотов `modelA.md` / `modelB.md`, читает `task.md` и оба ответа, при противоречиях сверяется с кодом проекта на `baseline_commit`, оценивает по рубрике задачи и объявляет победителя. Слот определяется только именем файла; поле `model` внутри файла (если осталось от старого формата) SHALL игнорироваться и MUST NOT блокировать оценку. Skill судьи MUST NOT писать `data/matchups/T-NNN/NNN.json`, MUST NOT запускать `python tools/elo.py`, MUST NOT вызывать `tools/record_verdict.py` и MUST NOT иметь доступа к реальным `id` моделей. Судья возвращает только `winner` (`a` | `b` | `draw`); запись вердикта выполняется координатором отдельным шагом.

#### Scenario: Судья выбирает победителя

- **WHEN** оба слота на T-001 готовы и вызван `@benchmark-judge T-001`
- **THEN** skill выводит таблицу оценок, обоснование и победителя (`a` | `b` | `draw`)
- **AND** skill сообщает: "Запишите вердикт через веб-UI или `record_verdict.py` с реальными id"
- **AND** matchups-файл не создаётся

#### Scenario: Ничья

- **WHEN** разница итоговых баллов не превышает порог ничьей задачи
- **THEN** skill MAY объявить ничью (`winner: draw`)
- **AND** в остальных случаях выбирает победителя даже при близких оценках

#### Scenario: Нет ответа

- **WHEN** `modelA.md` или `modelB.md` отсутствует
- **THEN** skill останавливается с сообщением какой прогон запустить сначала
- **AND** вердикт не создаётся

### Requirement: Шаг 3 (альтернатива) — Судья вручную

Пользователь MAY судить вручную: берёт шаблон из `docs/judge-prompt.md`, даёт любой LLM содержимое `task.md` и двух ответов анонимно (Answer 1 / Answer 2) и читает вердикт в чате. Соответствие Answer 1 = слот A и Answer 2 = слот B SHALL определяться порядком вставки координатором, а не шапкой внутри текстов. Судья в чате SHALL предоставлять только оценки, победителя и обоснование; он MUST NOT создавать файлов и MUST NOT считать ELO. Пользователь сам записывает результат через `tools/record_verdict.py` с явными реальными `id` или веб-UI.

#### Scenario: Ручное судейство

- **WHEN** пользователь даёт судье `task.md` + два ответа по шаблону judge-prompt
- **THEN** судья отвечает: оценки, победитель, обоснование
- **AND** пользователь переносит итог в `record_verdict.py --task T-001 --model-a <id> --model-b <id> --winner <a|b|draw>` или форму на `localhost:5000`
