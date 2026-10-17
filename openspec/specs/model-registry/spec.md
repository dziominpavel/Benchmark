# model-registry Specification

## Purpose
Реестр моделей (`models.yaml`) со статусами active/archived. Регистрация через
CLI (`tools/register_model.py`, включая саморегистрацию `--auto`) или веб-форму
«+ Добавить модель»; архивация через CLI (`tools/archive_model.py`). ELO
и статистика хранятся в `index.json` (генерируется), метаданные — в `models.yaml`.

## Requirements

### Requirement: Формат реестра

Модели SHALL храниться в `data/models.yaml` списком `models:`. Каждая запись:
`id` (slug, стабильный), `name` (человекочитаемое имя), опциональные `provider`
(компания-разработчик модели), `agent` (агент-обёртка; допустимые значения —
справочник `data/lookups.yaml`, см. «Файл справочников»), `version`,
`released`, `notes`; `added` — дата регистрации модели
(`YYYY-MM-DD`, заполняется при регистрации, может быть задана вручную);
`status`: `active` | `archived` (по умолчанию `active`).
Комментарии-Шапка файла SHALL описывать формат и команды управления.

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
- **AND** метаданные (id, name, agent, provider, version, added) сохраняются

#### Scenario: Агент и компания в записи

- **WHEN** модель зарегистрирована с `--agent Cursor` и `--provider Anthropic`
- **THEN** запись содержит `agent: Cursor` и `provider: Anthropic`
- **AND** серверные страницы показывают подпись `Anthropic · Cursor`
- **AND** значения проходят фильтр по агенту и компании

### Requirement: Регистрация через CLI

`register_model.py` SHALL требовать `--id` и `--name`; `--version` обязателен в
обычном режиме и опционален при `--auto`; `--provider` (компания) и `--agent`
опциональны в обоих режимах, переданные значения SHALL записываться в реестр.
Если непустое значение `--agent` или `--provider` отсутствует в справочнике
(`data/lookups.yaml`), скрипт SHALL добавить его в справочник в конец
соответствующего списка и сообщить об этом в выводе — регистрация MUST NOT
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

- **WHEN** выполняется `register_model.py --id gpt-5 --name "GPT-5" --provider OpenAI --version gpt-5 --added 2026-01-15`
- **THEN** запись содержит `added: 2026-01-15`

#### Scenario: Уже зарегистрирована

- **WHEN** модель с id gpt-5 уже существует и передан `--auto`
- **THEN** скрипт сообщает «Модель уже зарегистрирована» и завершается успешно
- **AND** `added` существующей записи не меняется

#### Scenario: Регистрация с агентом и компанией

- **WHEN** выполняется `register_model.py --id claude-sonnet-4.6 --name "Claude Sonnet 4.6" --agent Cursor --provider Anthropic --version sonnet-4.6`
- **THEN** запись содержит `agent: Cursor` и `provider: Anthropic`

#### Scenario: Агент и компания не обязательны

- **WHEN** выполняется `register_model.py --id test --name "Test" --version 1` без `--agent` и `--provider`
- **THEN** запись создаётся с пустыми `agent` и `provider`
- **AND** вызов завершается успешно

#### Scenario: Новое значение попадает в справочник

- **WHEN** выполняется `register_model.py --id amp-1 --name "Amp 1" --agent Amp --provider Sourcegraph --version 1`
- **AND** значений `Amp` и `Sourcegraph` нет в справочнике
- **THEN** запись создаётся
- **AND** `data/lookups.yaml` содержит `Amp` в `agents` и `Sourcegraph` в `providers`
- **AND** вывод содержит сообщение о добавлении значений в справочник

### Requirement: Регистрация через веб-UI

Форма `/add` SHALL принимать название (обязательно) и опциональные поля «Агент»
и «Компания», выбираемые из справочника (см. «Файл справочников»); значение вне
справочника сервер SHALL отклонять с ошибкой. Slug генерируется (`slugify`):
нижний регистр, не-алфанумерика → дефисы; пустое название после очистки —
`model-N`; занятый id — суффикс `-2`, `-3`… Новая запись SHALL получать
`status: active`, `added` (текущая дата), а также переданные `agent`
и `provider`; реестр сортируется по id, `index.json` пересчитывается сразу.

#### Scenario: Добавление через UI

- **WHEN** вводится «GPT-4o»
- **THEN** создаётся id `gpt-4o` со стартовым ELO 1200
- **AND** запись содержит `added` с текущей датой

#### Scenario: Добавление с агентом и компанией

- **WHEN** вводится «Cursor Fable 5.2», агент «Cursor», компания «Anthropic»
- **THEN** запись содержит `agent: Cursor` и `provider: Anthropic`
- **AND** в списке «Уже в списке» под именем видна подпись `Anthropic · Cursor`

#### Scenario: Пустые агент и компания

- **WHEN** название заполнено, а поля «Агент» и «Компания» пусты
- **THEN** запись создаётся с пустыми `agent` и `provider`
- **AND** вызов завершается успешно

#### Scenario: Значение вне справочника отклоняется

- **WHEN** в POST /add_model приходит агент, которого нет в справочнике
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
- **AND** метаданные (id, name, agent, provider, version, added) сохраняются
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

### Requirement: Агент и фирма модели в index.json

`data/index.json["models"][<id>]` SHALL содержать поля `agent` и `provider`,
скопированные из `data/models.yaml` (пустая строка, если поле не задано).
Серверные страницы SHALL брать подписи `Компания · Агент` и значения фильтров из
`index.json`, без повторного чтения `data/models.yaml`.

#### Scenario: Агент и компания в кэше

- **WHEN** `data/index.json` сгенерирован, а у модели в реестре `agent: Cursor` и `provider: Anthropic`
- **THEN** запись `models.<id>` содержит `"Cursor"` и `"Anthropic"`
- **AND** серверная страница показывает подпись `Anthropic · Cursor` из кэша

### Requirement: Визуальная пометка archived

Leaderboard (серверная страница) SHALL визуально отличать модели со `status: archived` от активных (приглушённая строка, плашка «неактивна» рядом с именем).

#### Scenario: Архивная модель в таблице

- **WHEN** модель C имеет `status: archived`
- **THEN** строка C отображается приглушённой с плашкой «неактивна»
- **AND** серверная таблица по умолчанию показывает только активные (параметр фильтра `active` / `all` / `inactive`)

### Requirement: Файл справочников

`data/lookups.yaml` SHALL хранить допустимые значения полей `agent` и `provider`
двумя списками простых строк: `agents:` и `providers:`. Порядок значений в файле
SHALL задавать порядок их вывода в таблицах секции «Справочники», выпадающих
списках форм и других местах выбора значения. Файл SHALL коммититься в git
и MAY редактироваться вручную; при отсутствии файла SHALL считаться, что
справочники пусты (все значения реестра — «вне справочника»), а страницы
работают без ошибок.

#### Scenario: Файл и порядок значений

- **WHEN** `data/lookups.yaml` содержит `agents: [Codex, Cursor, Devin, OpenCode]`
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

- **WHEN** в `data/models.yaml` вручную задан `provider: Zhipu`, которого нет в справочнике
- **THEN** страницы показывают `Zhipu` как значение «вне справочника»
- **AND** страницы, фильтры и регистрация работают без ошибок
