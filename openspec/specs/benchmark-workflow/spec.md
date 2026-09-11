# benchmark-workflow Specification

## Purpose
Сквозной workflow MVP: задача создаётся вручную из шаблона → прогоны выполняются
skills `benchmark-run-a` / `benchmark-run-b` (слоты modelA / modelB) → судейство через
skill `benchmark-judge` либо вручную с записью через веб-UI (выбор активной таски) →
leaderboard. Минимальный прогон: 1 задача + 2 ответа + 1 вердикт = валидный ELO
(победитель +20, проигравший −20 от 1200 при K=40).

## Requirements

### Requirement: Шаг 1 — Создание задачи вручную
Задача SHALL создаваться вручную из файла `data/tasks/_TEMPLATE.md`: копируется шаблон, заполняются front matter (`id`, `title`, опционально `project`, `baseline_commit`) и разделы описания. Генеративного skill для создания задач в репозитории нет. Дополнительно задача MAY создаваться через CLI `tools/register_task.py` или веб-форму, которые определяют следующий `T-NNN` и заполняют front matter автоматически.

#### Scenario: Создание задачи
- **WHEN** пользователь копирует `data/tasks/_TEMPLATE.md` в `data/tasks/T-002-<slug>/task.md` и заполняет поля
- **THEN** задача готова к прогонам
- **AND** skills прогонов находят её по маске `data/tasks/T-NNN-*/task.md`

#### Scenario: Создание задачи через register_task.py
- **WHEN** выполнено `python tools/register_task.py --title "New Hunt" --slug new-hunt`
- **THEN** создаётся `data/tasks/T-002-new-hunt/task.md`
- **AND** `data/settings.yaml` обновляется: `T-002: active`, `current_task: T-002`

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

### Requirement: Шаг 4 — Запись вердикта и leaderboard
Вердикт SHALL попадать в систему через единую точку записи: `tools/record_verdict.py` с явными реальными идентификаторами моделей и обязательным параметром `--task T-NNN`. Веб-сервер MAY предоставлять UI для ручной записи, который внутри вызывает ту же точку записи. Запись SHALL принимать реальные `id` в аргументах `model_a`/`model_b` (CLI) или в форме (UI), SHALL писать `data/matchups/<task>/<NNN>.json`, SHALL сохранять ELO-снэпшот и SHALL пересчитывать `data/index.json`. Запись MUST NOT разрешать слоты `modelA`/`modelB` через `data/answers/<task>/slots.json`. Корзины `general` не существует; каждый вердикт привязан к конкретной задаче `T-NNN`.

#### Scenario: Запись через skill судьи
- **WHEN** `@benchmark-judge` завершил оценку и выбрал победителя
- **THEN** пользователь запускает `python tools/record_verdict.py --task T-001 --model-a <id> --model-b <id> --winner <a|b|draw>`
- **AND** `record_verdict.py` создаёт `data/matchups/T-001/NNN.json` с `task: T-001`
- **AND** `record_verdict.py` пересчитывает `data/index.json`

#### Scenario: Запись через веб-UI
- **WHEN** пользователь выбрал модель A, модель B, таск `T-001` и победителя в форме
- **THEN** сервер вызывает `record_verdict` с `task: T-001` и реальными `id`
- **AND** создаётся `data/matchups/T-001/NNN.json`
- **AND** сервер пересчитывает ELO и показывает обновлённый leaderboard

#### Scenario: Попытка записать слот вместо id
- **WHEN** пользователь вызывает `record_verdict.py --task T-001 --model-a modelA --model-b modelB --winner a`
- **THEN** инструмент возвращает ошибку: "Модель A не разрешена: 'modelA'"
- **AND** вердикт не создаётся

### Requirement: Минимальный прогон

Минимальный валидный прогон: 1 задача + 2 ответа (modelA, modelB) + 1 вердикт.
При стартовом ELO 1200 и K=40 победитель получает +20, проигравший −20.
Значения +16/−16 из старых архивов НЕВЕРНЫ для текущего K-factor и MUST NOT
использоваться в документации.

#### Scenario: Минимальный прогон

- **WHEN** создана T-001, готовы modelA и modelB, записан 1 вердикт A > B
- **THEN** A: ELO=1220, B: ELO=1180
- **AND** leaderboard показывает 2 модели с 1 игрой у каждой

### Requirement: Добавление новой модели

Новая модель SHALL регистрироваться через `tools/register_model.py --auto`
или кнопку «+ Добавить модель» в веб-UI, затем отвечать на существующую задачу
(вручную либо слотами A/B) и сравниваться с уже оценёнными моделями. ELO стартует
с 1200; pairing engine предлагает несравненные пары с её участием в первую очередь
(низкое число игр = высокий score).

#### Scenario: Новая модель на существующую задачу

- **WHEN** зарегистрирована модель D и у неё появился ответ на T-001
- **THEN** рекомендации пар включают D-A, D-B, D-C
- **AND** после вердиктов ELO D калибруется от 1200

### Requirement: Новая задача

Новая задача создаётся копированием `data/tasks/_TEMPLATE.md` под следующим номером,
когда текущая исчерпана. Модели SHALL переносить текущий ELO на новую задачу
(сброса нет); ответы пишутся в `data/answers/T-NNN/`, вердикты skill-пути — в
`data/matchups/T-NNN/`.

#### Scenario: Переход к новой задаче

- **WHEN** T-001 исчерпана и создана T-002
- **THEN** модели не сбрасывают ELO
- **AND** вердикты по T-002 продолжают обновлять тот же глобальный рейтинг
