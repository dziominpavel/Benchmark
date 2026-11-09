# model-registry Specification

## Purpose
Реестр моделей (`models.yaml`) со статусами active/archived. Регистрация через
CLI (`tools/register_model.py`, включая саморегистрацию `--auto`) или веб-форму
«+ Добавить модель»; архивация через CLI (`tools/archive_model.py`). ELO
и статистика хранятся в `index.json` (генерируется), метаданные — в `models.yaml`.

## Requirements

### Requirement: Формат реестра

Модели SHALL храниться в `data/models.yaml` списком `models:`. Каждая запись:
`id` (slug, стабильный), `name` (человекочитаемое имя модели без харнесса и
компании), опциональные `developer` (компания-разработчик модели), `provider`
(провайдер доступа: OpenCode Go, OpenRouter, Vercel AI Gateway, Kilo Code,
встроенный доступ харнесса — Cursor, Cognition, OpenAI), `harness` (харнесс:
Codex, Cursor, Devin, OpenCode), `version`, `released`, `notes`; `added` — дата
регистрации модели (`YYYY-MM-DD`, заполняется при регистрации, может быть
задана вручную); `status`: `active` | `archived` (по умолчанию `active`).
Допустимые значения `developer`/`provider`/`harness` — справочник
`data/lookups.yaml` (см. «Файл справочников»). Комментарии-шапка файла SHALL
описывать формат и команды управления.

#### Scenario: Новая модель

- **WHEN** модель регистрируется
- **THEN** в `data/models.yaml` добавляется запись с id, name, added, status: active

#### Scenario: Запись без added

- **WHEN** запись не содержит `added` (например, добавлена до введения поля)
- **THEN** она читается всеми инструментами без ошибок
- **AND** отсутствие даты не считается ошибкой формата

#### Scenario: Архивная модель

- **WHEN** модель архивируется
- **THEN** её status меняется на archived
- **AND** метаданные (id, name, developer, provider, harness, version, added) сохраняются

#### Scenario: Разработчик, провайдер и харнесс в записи

- **WHEN** модель зарегистрирована с `--developer Anthropic`, `--provider Cursor` и `--harness Cursor`
- **THEN** запись содержит `developer: Anthropic`, `provider: Cursor`, `harness: Cursor`
- **AND** серверные страницы показывают подпись `Anthropic · Cursor` (повтор Cursor схлопывается)
- **AND** значения проходят фильтр по разработчику, провайдеру и харнессу

### Requirement: Регистрация через CLI

`register_model.py` SHALL требовать `--id` и `--name`; `--version` обязателен в
обычном режиме и опционален при `--auto`; `--developer`, `--provider` и
`--harness` опциональны в обоих режимах, переданные значения SHALL записываться
в реестр. `--agent` SHALL оставаться синонимом `--harness` для старых скриптов.
Если непустое значение `--developer`, `--provider` или `--harness` отсутствует
в справочнике (`data/lookups.yaml`), скрипт SHALL добавить его в справочник в
конец соответствующего списка и сообщить об этом в выводе — регистрация MUST NOT
падать из-за значения вне справочника. Дубликат id без `--force` SHALL
отклоняться (exit 1); при `--auto` существующий
id — не ошибка (exit 0, «уже зарегистрирована»); при `--force` запись
перезаписывается. Скрипт SHALL записывать `added`: значение
`--added <YYYY-MM-DD>`, а при его отсутствии — текущую дату. Список SHALL
сортироваться по id, преамбула файла — сохраняться.

#### Scenario: Саморегистрация

- **WHEN** выполняется `register_model.py --auto --id gpt-5 --name "GPT-5"`
- **THEN** модель добавляется в `models.yaml` со status: active
- **AND** `added` содержит текущую дату

#### Scenario: Явная дата регистрации

- **WHEN** выполняется `register_model.py --id gpt-5 --name "GPT-5" --developer OpenAI --provider OpenAI --harness Codex --version gpt-5 --added 2026-01-15`
- **THEN** запись содержит `added: 2026-01-15`

#### Scenario: Уже зарегистрирована

- **WHEN** модель с id gpt-5 уже существует и передан `--auto`
- **THEN** скрипт сообщает «Модель уже зарегистрирована» и завершается успешно
- **AND** `added` существующей записи не меняется

#### Scenario: Регистрация с разработчиком, провайдером и харнессом

- **WHEN** выполняется `register_model.py --id claude-sonnet-4.6 --name "Claude Sonnet 4.6" --developer Anthropic --provider Cursor --harness Cursor --version sonnet-4.6`
- **THEN** запись содержит `developer: Anthropic`, `provider: Cursor`, `harness: Cursor`

#### Scenario: Классификация не обязательна

- **WHEN** выполняется `register_model.py --id test --name "Test" --version 1` без `--developer`, `--provider` и `--harness`
- **THEN** запись создаётся с пустыми `developer`, `provider` и `harness`
- **AND** вызов завершается успешно

#### Scenario: Новое значение попадает в справочник

- **WHEN** выполняется `register_model.py --id amp-1 --name "Amp 1" --developer Sourcegraph --provider Amp --harness Amp --version 1`
- **AND** значений `Sourcegraph` и `Amp` нет в справочнике
- **THEN** запись создаётся
- **AND** `data/lookups.yaml` содержит `Amp` в `harnesses` и `providers`, `Sourcegraph` в `developers`
- **AND** вывод содержит сообщение о добавлении значений в справочник

### Requirement: Регистрация через веб-UI

Форма `/add` SHALL принимать название (обязательно) и опциональные поля
«Разработчик», «Провайдер» и «Харнесс», выбираемые из справочника (см. «Файл
справочников»); значение вне справочника сервер SHALL отклонять с ошибкой. Slug
генерируется (`slugify`): нижний регистр, не-алфанумерика → дефисы; пустое
название после очистки — `model-N`; занятый id — суффикс `-2`, `-3`… Новая
запись SHALL получать `status: active`, `added` (текущая дата), а также
переданные `developer`, `provider` и `harness`; реестр сортируется по id,
`index.json` пересчитывается сразу.

#### Scenario: Добавление через UI

- **WHEN** вводится «GPT-4o»
- **THEN** создаётся id `gpt-4o` со стартовым ELO 1200
- **AND** запись содержит `added` с текущей датой

#### Scenario: Добавление с классификацией

- **WHEN** вводится «Claude Fable 5.2», разработчик «Anthropic», провайдер «Cursor», харнесс «Cursor»
- **THEN** запись содержит `developer: Anthropic`, `provider: Cursor`, `harness: Cursor`
- **AND** в списке «Уже в списке» под именем видна подпись `Anthropic · Cursor`

#### Scenario: Пустая классификация

- **WHEN** название заполнено, а поля «Разработчик», «Провайдер» и «Харнесс» пусты
- **THEN** запись создаётся с пустыми `developer`, `provider` и `harness`
- **AND** вызов завершается успешно

#### Scenario: Значение вне справочника отклоняется

- **WHEN** в POST /add_model приходит разработчик, которого нет в справочнике
- **THEN** сервер отклоняет запрос с ошибкой
- **AND** новая запись не создаётся

### Requirement: Архивация модели

Архивация SHALL выполняться командой `python tools/archive_model.py <model-id>`
(поле `status` → `archived`, запись ищется по точному id через regex).
История вердиктов сохраняется; новых ограничений в коде это не создаёт
(см. elo-engine, pairing-algorithm). Несуществующий id SHALL давать ошибку (exit 1).

#### Scenario: Архивация

- **WHEN** выполняется `archive_model.py claude-sonnet-4.5`
- **THEN** status в `data/models.yaml` меняется на archived
- **AND** метаданные (id, name, developer, provider, harness, version, added) сохраняются
- **AND** старые вердикты остаются в `data/matchups/`

#### Scenario: Архивация несуществующей модели

- **WHEN** выполняется `archive_model.py non-existent-model`
- **THEN** скрипт сообщает «Модель не найдена» и завершается с ошибкой

### Requirement: Разархивация

Разархивация SHALL выполняться командой
`python tools/archive_model.py --restore <model-id>` (status → `active`).
ELO SHALL сохраняться (пересчёт идёт из тех же вердиктов, сброса нет).

#### Scenario: Разархивация

- **WHEN** выполняется `archive_model.py --restore claude-sonnet-4.5`
- **THEN** status меняется на active
- **AND** ELO остаётся прежним

### Requirement: Стабильность id

id модели SHALL быть неизменным после создания. При выходе новой версии модели
(например claude-sonnet-4.5 → 4.6) SHALL создаваться новый id, старый MAY
архивироваться. История старой версии сохраняется.

#### Scenario: Новая версия модели

- **WHEN** выходит Claude Sonnet 4.6
- **THEN** создаётся новый id: claude-sonnet-4.6
- **AND** старый id при необходимости архивируется
- **AND** история 4.5 сохраняется

### Requirement: ELO не в models.yaml

ELO и статистика (W/L/D, games) SHALL храниться только в `data/index.json`.
`data/models.yaml` содержит только метаданные, поэтому ручное редактирование
метаданных на ELO не влияет.

#### Scenario: Ручное редактирование models.yaml

- **WHEN** пользователь меняет notes/provider в `data/models.yaml`
- **THEN** ELO не затрагивается
- **AND** следующий пересчёт строится из `data/matchups/`

### Requirement: Статус модели в index.json

`data/index.json["models"][<id>]` SHALL содержать поле `status` (`active` | `archived`), скопированное из `data/models.yaml`. UI и алгоритм рекомендаций SHALL использовать это поле без повторного чтения `data/models.yaml`.

#### Scenario: Статус в index.json

- **WHEN** `data/index.json` сгенерирован
- **THEN** каждая модель содержит `status`
- **AND** `pairing-algorithm` исключает модели со `status: archived`

### Requirement: Разработчик, провайдер и харнесс в index.json

`data/index.json["models"][<id>]` SHALL содержать поля `developer`, `provider`
и `harness`, скопированные из `data/models.yaml` (пустая строка, если поле не
задано). Серверные страницы SHALL брать подписи
`Разработчик · Провайдер · Харнесс` и значения фильтров из `index.json`, без
повторного чтения `data/models.yaml`.

#### Scenario: Классификация в кэше

- **WHEN** `data/index.json` сгенерирован, а у модели в реестре `developer: Anthropic`, `provider: Cursor`, `harness: Cursor`
- **THEN** запись `models.<id>` содержит `"Anthropic"`, `"Cursor"` и `"Cursor"`
- **AND** серверная страница показывает подпись `Anthropic · Cursor` из кэша

### Requirement: Визуальная пометка archived

Leaderboard (серверная страница) SHALL визуально отличать модели со `status: archived` от активных (приглушённая строка, плашка «неактивна» рядом с именем).

#### Scenario: Архивная модель в таблице

- **WHEN** модель C имеет `status: archived`
- **THEN** строка C отображается приглушённой с плашкой «неактивна»
- **AND** серверная таблица по умолчанию показывает только активные (параметр фильтра `active` / `all` / `inactive`)

### Requirement: Файл справочников

`data/lookups.yaml` SHALL хранить допустимые значения полей `harness`,
`developer` и `provider` тремя списками простых строк: `harnesses:`,
`developers:` и `providers:`. Порядок значений в файле SHALL задавать порядок их
вывода в таблицах секции «Справочники», выпадающих списках форм и других местах
выбора значения. Файл SHALL коммититься в git и MAY редактироваться вручную;
при отсутствии файла SHALL считаться, что справочники пусты (все значения
реестра — «вне справочника»), а страницы работают без ошибок.

#### Scenario: Файл и порядок значений

- **WHEN** `data/lookups.yaml` содержит `harnesses: [Codex, Cursor, Devin, OpenCode]`
- **THEN** таблицы и выпадающие списки показывают значения в порядке файла

#### Scenario: Отсутствующий файл

- **WHEN** `data/lookups.yaml` отсутствует
- **THEN** справочники считаются пустыми, все значения реестра — «вне справочника»
- **AND** страницы работают без ошибок

### Requirement: Изменение значений справочника

Переименование значения SHALL каскадом обновлять все записи реестра
`data/models.yaml` и пересчитывать `data/index.json`; удаление SHALL быть
возможно только пока значение не используется ни одной моделью; обе операции
SHALL NOT менять ELO и вердикты. Значения реестра, отсутствующие в справочнике
(ручная правка файлов), SHALL оставаться допустимыми: страницы показывают их
с пометкой «вне справочника», и такое значение MAY быть внесено в справочник
одним действием.

#### Scenario: Каскад переименования

- **WHEN** значение `Z.ai` переименовано в `Zhipu`
- **THEN** все модели реестра со значением `Z.ai` получают `Zhipu`
- **AND** `data/index.json` пересчитан
- **AND** ELO и вердикты не изменились

#### Scenario: Удаление

- **WHEN** у значения есть хотя бы одна модель в реестре
- **THEN** удаление отклоняется
- **WHEN** значение не использует ни одна модель
- **THEN** оно удаляется из `data/lookups.yaml`

#### Scenario: Ручное значение вне справочника

- **WHEN** в `data/models.yaml` вручную задан `developer: Zhipu`, которого нет в справочнике
- **THEN** страницы показывают `Zhipu` как значение «вне справочника»
- **AND** страницы, фильтры и регистрация работают без ошибок
