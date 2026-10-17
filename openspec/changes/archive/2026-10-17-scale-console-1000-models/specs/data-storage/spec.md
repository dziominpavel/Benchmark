## MODIFIED Requirements

### Requirement: Корень данных — data/
Все файлы данных SHALL храниться под директорией `data/` в корне репозитория: `data/models.yaml`, `data/lookups.yaml`, `data/judges.yaml`, `data/settings.yaml`, `data/answer_flags.yaml`, `data/index.json`, `data/tasks/`, `data/answers/`, `data/matchups/` (включая `data/matchups/journal.jsonl`), `data/logs/`. Код SHALL находиться в `tools/`, лаунчеры (`start.bat`, `stop.bat`, `launch.vbs`) — в корне. Файлы данных вне `data/` MUST NOT использоваться.

#### Scenario: Структура корня
- **WHEN** пользователь открывает корень репозитория
- **THEN** все данные прогонов находятся в `data/`
- **AND** в корне нет `tasks/`, `answers/`, `matchups/`, `models.yaml`, `settings.yaml`, `index.json`

### Requirement: Source of truth — файлы
Исходные данные SHALL храниться в файлах: `data/models.yaml` (реестр), `data/lookups.yaml` (справочники агентов и компаний), `data/tasks/T-NNN-<slug>/task.md` (задачи), `data/answers/T-NNN/modelA.md` / `modelB.md` (только два транзитных слота текущего судейства), `data/matchups/journal.jsonl` (журнал вердиктов: одна JSON-строка на событие), `data/settings.yaml` (настройки: статусы тасок и текущая таска), `data/answer_flags.yaml` (ручной учёт наличия ответов, см. `answer-coverage`). Файлы `data/answers/<task>/<model-id>.md` в проекте MUST NOT использоваться (тексты ответов хранятся вне проекта). `data/matchups/general/` и `data/matchups/<non-T-NNN>/` MUST NOT использоваться. `data/answers/<task>/slots.json` MUST NOT использоваться. Эти файлы SHALL коммититься в git.

#### Scenario: Git diff ответа
- **WHEN** модель пишет ответ
- **THEN** git diff показывает изменённый Markdown-файл `data/answers/T-NNN/modelA.md` или `modelB.md`
- **AND** не создаётся `data/answers/T-NNN/slots.json`

#### Scenario: Git diff вердикта
- **WHEN** записывается новый вердикт
- **THEN** git diff показывает одну добавленную строку в `data/matchups/journal.jsonl`
- **AND** `data/matchups/general/` не появляется
- **AND** директории `data/matchups/T-NNN/` не создаются

#### Scenario: Git diff настроек
- **WHEN** пользователь сохраняет настройки через `/settings`
- **THEN** git diff показывает изменённый `data/settings.yaml`
- **AND** в нём нет ключа `general`

#### Scenario: Git diff справочников
- **WHEN** координатор добавляет значение в секции «Справочники»
- **THEN** git diff показывает изменённый `data/lookups.yaml`

### Requirement: Кэш — index.json

`data/index.json` SHALL содержать: `version` (=2), `updated` (YYYY-MM-DD), `matchups_digest` (sha256 содержимого журнала), `models` (имя, провайдер, агент, дата регистрации `added`, статус, ELO, games/wins/losses/draws), `tasks` (сводка: `slug`, `title`, `matchups_count` без списка ответов), `matchups_summary` (счётчики событий журнала: `total`, `applied`, `voided`, `tombstone`, `skipped`), `elo_history`. Секция-список `matchups_index` MUST NOT присутствовать (её роль выполняют агрегаты `matchups_summary` и полный журнал `data/matchups/journal.jsonl`). Поле `tasks.<id>.answers` MUST NOT присутствовать (авто-учёт ответов удалён, источник — `data/answer_flags.yaml`). `elo_history` SHALL содержать одну запись на применённый матч с полями `matchup`, `seq`, `date`, `recorded_at`, `model_a_id`, `model_b_id`, `winner`, `elo_a` (before/after/delta), `elo_b` (before/after/delta); поле `after_matchup` MUST NOT присутствовать (дубликат `matchup`, никем не читается). Файл SHALL коммититься в git для просмотра рейтинга без запуска сервера.

#### Scenario: Структура index.json

- **WHEN** `data/index.json` сгенерирован
- **THEN** он содержит секции: `version`, `updated`, `matchups_digest`, `models`, `tasks`, `matchups_summary`, `elo_history`
- **AND** каждая запись `models.<id>` содержит `added`, скопированный из `data/models.yaml` (пустая строка, если в реестре поля нет)
- **AND** каждая запись `models.<id>` содержит `agent` и `provider`, скопированные из `data/models.yaml` (пустая строка, если поле не задано)
- **AND** `elo_history[0]` содержит `elo_a` и `elo_b`
- **AND** секция `matchups_index` отсутствует
- **AND** `tasks.T-001` не содержит поля `answers`
- **AND** `matchups_summary` содержит `total`/`applied`/`voided`/`tombstone`/`skipped`

#### Scenario: Просмотр без сервера

- **WHEN** пользователь открывает `data/index.json` в редакторе
- **THEN** видит текущий ELO всех моделей и статистику
- **AND** историю матчей в match-centric формате

### Requirement: Критерий устаревания кэша

`is_index_stale` SHALL считать кэш устаревшим если: `data/index.json` отсутствует
или не парсится; `matchups_digest` в кэше ≠ дайджесту текущего журнала (ловит любые правки, добавления и удаления строк журнала); множество id моделей в кэше ≠ множеству id в `data/models.yaml`; метаданные модели (`name`, `agent`, `provider`, `status`, `added`) в кэше ≠ реестру. Отдельной проверки числа записей НЕ существует — дайджест покрывает состав журнала полностью. Содержимое ответов, тексты задач и даты внутри вердиктов НЕ проверяются.

#### Scenario: Новый вердикт делает кэш устаревшим

- **WHEN** в `data/matchups/journal.jsonl` добавлена строка
- **THEN** `is_index_stale` возвращает True

#### Scenario: Правка added делает кэш устаревшим

- **WHEN** в `data/models.yaml` изменён `added` модели
- **THEN** `is_index_stale` возвращает True
- **AND** следующий пересчёт копирует новое значение в `data/index.json`

#### Scenario: Правка agent или provider делает кэш устаревшим

- **WHEN** в `data/models.yaml` изменён `agent` или `provider` модели
- **THEN** `is_index_stale` возвращает True
- **AND** следующий пересчёт копирует новые значения в `data/index.json`

#### Scenario: Актуальный кэш

- **WHEN** сервер стартует и дайджест, множество id и метаданные моделей сошлись
- **THEN** сервер использует кэш без пересчёта (мгновенный старт)

### Requirement: Ключ задач в сводке (известный дефект)

`collect_tasks_info` SHALL сканировать директории `data/tasks/` (кроме `_`-префикса) и считать события журнала с полем `task`, равным ключу задачи. Сканирование `data/answers/<task-id>/` для сводки MUST NOT выполняться. Идентификатор задачи SHALL извлекаться из имени директории как префикс `T-NNN` до первого дефиса, включая номер: `T-001-recurrence-bugs` → `T-001`.

#### Scenario: Сводка T-001 в MVP
- **WHEN** сгенерирован `data/index.json` при задаче `T-001-recurrence-bugs`
- **THEN** секция `tasks` содержит ключ `"T-001"` с корректным счётчиком вердиктов
- **AND** не создаётся ключа `"T"`
- **AND** не создаётся поля `answers`

### Requirement: Масштаб хранилища

Хранилище SHALL быть рассчитано на: 1–10 задач, до 1000 моделей (до 1000 активных одновременно),
10 000–50 000 вердиктов. Маржинальная стоимость вердикта в кэше — ~0.31 КБ (одна
запись `elo_history`; агрегат `matchups_summary` от числа вердиктов не растёт).
Замер: ~44 КБ при 88 вердиктах; прогноз — ~3.5 МБ при 10 000 вердиктов. Полный
пересчёт при 10 000 вердиктов занимает <1 c (один проход, только stdlib).
Ответы — до ~50 KB каждый.

#### Scenario: Типичный объём

- **WHEN** 3 задачи, 10 моделей, 100 вердиктов
- **THEN** `data/index.json` ~48 КБ
- **AND** `data/answers/` ~30 файлов, журнал вердиктов — один файл `data/matchups/journal.jsonl`

#### Scenario: Целевой масштаб

- **WHEN** в реестре 1000 моделей и в журнале 10 000 событий
- **THEN** `data/index.json` — порядка 3.5 МБ
- **AND** дайджест журнала считается не дольше ~50 мс
- **AND** полный пересчёт занимает не более ~1 c

### Requirement: Файл настроек settings.yaml
`data/settings.yaml` SHALL хранить: `current_task` (id активной таски, подставляемой в форму вердикта) и `tasks` — отображение `id таски -> status` (`active` | `inactive`). Файл SHALL коммититься в git и MAY редактироваться вручную. При отсутствии файла SHALL применяться дефолты: активные таски — все `T-NNN`, обнаруженные в `data/tasks/` и среди значений `task` событий `data/matchups/journal.jsonl`; `current_task` — первая активная таска (лексикографически). При отсутствии `tasks`-записи для обнаруженной `T-NNN` таски она SHALL считаться активной. `general` не является допустимым значением `current_task` или ключа `tasks`.

#### Scenario: Сохранение настроек
- **WHEN** на странице `/settings` отмечены `T-001` и `T-002` как активные, текущая — `T-001`
- **THEN** `data/settings.yaml` содержит `current_task: T-001` и `tasks` со статусами `T-001: active`, `T-002: active`
- **AND** ключа `general` в файле нет

#### Scenario: Отсутствующий файл
- **WHEN** `data/settings.yaml` не существует, но есть `data/tasks/T-001-<slug>/task.md`
- **THEN** сервер работает с дефолтами: `T-001` активна, `current_task` = `T-001`
- **AND** `general` не добавляется

#### Scenario: Новая таска без записи
- **WHEN** в `data/matchups/journal.jsonl` появилось событие с `task: T-002`, отсутствующим в `data/settings.yaml`
- **THEN** `T-002` считается активной до явной отметки

## ADDED Requirements

### Requirement: Формат журнала journal.jsonl
Вердикты SHALL храниться в едином append-only файле `data/matchups/journal.jsonl` (UTF-8, одна JSON-строка — одно событие) с обязательными полями `seq` (глобальный возрастающий номер), `task`, `matchup` (`T-NNN/NNN`), `recorded_at`. Виды событий: вердикт (поля — см. `matchup-management`) и аннулирование (`void_of`, `reason`). Порядок реплея — строго по возрастанию `seq`. Отдельные файлы вердиктов в поддиректориях задач (`T-NNN/`) и файл-счётчик `seq` `data/matchups/state.json` MUST NOT вестись.

#### Scenario: Событие за событием

- **WHEN** записан новый вердикт в `T-001`
- **THEN** в `data/matchups/journal.jsonl` появилась ровно одна новая строка с уникальным `seq`, большим всех предыдущих
- **AND** строка содержит `task: T-001`, `matchup` вида `T-001/NNN` и поля вердикта
- **AND** в `data/matchups/` нет директорий `T-NNN/` и файла `state.json`

#### Scenario: Порядок реплея по seq

- **WHEN** журнал содержит события с `seq` 1 и 2
- **THEN** реплей применяет событие 1 раньше события 2 независимо от позиции строк в файле

### Requirement: Целостность журнала
Журнал SHALL выдерживать параллельные записи и аварийные прерывания: запись события SHALL быть атомарной относительно других писателей (файловый lock), конкурирующие записи MUST NOT терять или перемешивать события. Оборванная последняя строка SHALL игнорироваться чтением с предупреждением; остальные события остаются валидными. `python tools/elo.py --check` SHALL сообщать об оборванной строке, дубликате `seq` и tombstone-ссылке на несуществующий вердикт как о проблемах.

#### Scenario: Оборванная последняя строка

- **WHEN** последняя строка журнала оборвана (невалидный JSON) из-за аварийного прерывания записи
- **THEN** чтение пропускает её с предупреждением
- **AND** все предыдущие события применяются как обычно
- **AND** `python tools/elo.py --check` сообщает проблему и завершается с ошибкой

#### Scenario: Параллельная запись

- **WHEN** запись вердикта через веб-UI совпала по времени с записью через CLI
- **THEN** в журнале присутствуют обе строки целиком, без смешения
- **AND** оба события получают различные `seq`

### Requirement: Миграция в единый журнал
Одноразовый скрипт миграции SHALL собрать события из `data/matchups/T-NNN/*.json` в порядке реплея, сохраняя `seq`, `task` и поля вердиктов, записать `data/matchups/journal.jsonl`, пересчитать `data/index.json` и верифицировать результат полным реплеем (ELO и статистика каждой модели совпадают до и после). Только после успешной верификации старые файлы и `data/matchups/state.json` SHALL быть удалены. Файл без `seq` SHALL считаться ошибкой миграции.

#### Scenario: Успешная миграция

- **WHEN** запущен скрипт миграции на хранилище из 535 файлов с `seq` 1–535
- **THEN** `data/matchups/journal.jsonl` содержит 535 строк в порядке `seq`
- **AND** реплей из журнала даёт те же ELO и статистику, что реплей исходных файлов
- **AND** `python tools/elo.py --check` проходит без проблем
- **AND** старые файлы `data/matchups/T-NNN/*.json` и `data/matchups/state.json` удалены

#### Scenario: Верификация не прошла

- **WHEN** реплей из собранного журнала расходится с реплеем исходных файлов
- **THEN** скрипт завершается с ошибкой
- **AND** старые файлы `data/matchups/T-NNN/*.json` остаются на месте
- **AND** `data/index.json` не переключается на новый журнал

## REMOVED Requirements

### Requirement: Миграция корзины general

**Reason**: Одноразовая миграция `general` → `T-001` выполнена исторически;
файловой раскладки `data/matchups/<task>/NNN.json` больше не существует, а
значение `task: general` не может попасть в журнал (см. требования «Source of
truth — файлы», «Привязка вердикта к активной задаче», «Учёт только активных
сущностей»).

**Migration**: Переносить нечего: событий с `task: general` в журнале нет,
попытка записать вердикт с `general` отклоняется валидацией.

