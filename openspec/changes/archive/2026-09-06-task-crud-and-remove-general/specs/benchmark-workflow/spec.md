# benchmark-workflow Specification

## MODIFIED Requirements

### Requirement: Шаг 1 — Создание задачи вручную
Задача SHALL создаваться вручную из файла `tasks/_TEMPLATE.md`: копируется шаблон, заполняются front matter (`id`, `title`, опционально `project`, `baseline_commit`) и разделы описания. Генеративного skill для создания задач в репозитории нет. Дополнительно задача MAY создаваться через CLI `tools/register_task.py` или веб-форму, которые определяют следующий `T-NNN` и заполняют front matter автоматически.

#### Scenario: Создание задачи
- **WHEN** пользователь копирует `tasks/_TEMPLATE.md` в `tasks/T-002-<slug>/task.md` и заполняет поля
- **THEN** задача готова к прогонам
- **AND** skills прогонов находят её по маске `tasks/T-NNN-*/task.md`

#### Scenario: Создание задачи через register_task.py
- **WHEN** выполнено `python tools/register_task.py --title "New Hunt" --slug new-hunt`
- **THEN** создаётся `tasks/T-002-new-hunt/task.md`
- **AND** `settings.yaml` обновляется: `T-002: active`, `current_task: T-002`

### Requirement: Шаг 4 — Запись вердикта и leaderboard
Вердикт SHALL попадать в систему через единую точку записи: `tools/record_verdict.py` с явными реальными идентификаторами моделей и обязательным параметром `--task T-NNN`. Веб-сервер MAY предоставлять UI для ручной записи, который внутри вызывает ту же точку записи. Запись SHALL принимать реальные `id` в аргументах `model_a`/`model_b` (CLI) или в форме (UI), SHALL писать `matchups/<task>/<NNN>.json`, SHALL сохранять ELO-снэпшот и SHALL пересчитывать `index.json`. Запись MUST NOT разрешать слоты `modelA`/`modelB` через `answers/<task>/slots.json`. Корзины `general` не существует; каждый вердикт привязан к конкретной задаче `T-NNN`.

#### Scenario: Запись через skill судьи
- **WHEN** `@benchmark-judge` завершил оценку и выбрал победителя
- **THEN** пользователь запускает `python tools/record_verdict.py --task T-001 --model-a <id> --model-b <id> --winner <a|b|draw>`
- **AND** `record_verdict.py` создаёт `matchups/T-001/NNN.json` с `task: T-001`
- **AND** `record_verdict.py` пересчитывает `index.json`

#### Scenario: Запись через веб-UI
- **WHEN** пользователь выбрал модель A, модель B, таск `T-001` и победителя в форме
- **THEN** сервер вызывает `record_verdict` с `task: T-001` и реальными `id`
- **AND** создаётся `matchups/T-001/NNN.json`
- **AND** сервер пересчитывает ELO и показывает обновлённый leaderboard

#### Scenario: Попытка записать слот вместо id
- **WHEN** пользователь вызывает `record_verdict.py --task T-001 --model-a modelA --model-b modelB --winner a`
- **THEN** инструмент возвращает ошибку: "Модель A не разрешена: 'modelA'"
- **AND** вердикт не создаётся
