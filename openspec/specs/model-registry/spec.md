# model-registry Specification

## Purpose
Реестр моделей (`models.yaml`) со статусами active/archived. Регистрация через
CLI (`tools/register_model.py`, включая саморегистрацию `--auto`) или веб-форму
«+ Добавить модель»; архивация через CLI (`tools/archive_model.py`). ELO
и статистика хранятся в `index.json` (генерируется), метаданные — в `models.yaml`.

## Requirements

### Requirement: Формат реестра

Модели SHALL храниться в `data/models.yaml` списком `models:`. Каждая запись:
`id` (slug, стабильный), `name` (человекочитаемое имя), опциональные `provider`,
`version`, `released`, `notes`; `added` — дата регистрации модели
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
- **AND** метаданные (id, name, provider, version, added) сохраняются

### Requirement: Регистрация через CLI

`register_model.py` SHALL требовать `--id` и `--name`; `--provider` и `--version`
обязательны в обычном режиме и опциональны при `--auto`. Дубликат id без
`--force` SHALL отклоняться (exit 1); при `--auto` существующий id — не ошибка
(exit 0, «уже зарегистрирована»); при `--force` запись перезаписывается.
Скрипт SHALL записывать `added`: значение `--added <YYYY-MM-DD>`, а при его
отсутствии — текущую дату. Список SHALL сортироваться по id, преамбула файла —
сохраняться.

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

### Requirement: Регистрация через веб-UI

Форма `/add` SHALL принимать только название; slug генерируется (`slugify`):
нижний регистр, не-алфанумерика → дефисы; пустое название после очистки —
`model-N`; занятый id — суффикс `-2`, `-3`… Новая запись SHALL получать
`status: active` и `added` (текущая дата), реестр сортируется по id,
`index.json` пересчитывается сразу.

#### Scenario: Добавление через UI

- **WHEN** вводится «GPT-4o»
- **THEN** создаётся id `gpt-4o` со стартовым ELO 1200
- **AND** запись содержит `added` с текущей датой

### Requirement: Архивация модели

Архивация SHALL выполняться командой `python tools/archive_model.py <model-id>`
(поле `status` → `archived`, запись ищется по точному id через regex).
История вердиктов сохраняется; новых ограничений в коде это не создаёт
(см. elo-engine, pairing-algorithm). Несуществующий id SHALL давать ошибку (exit 1).

#### Scenario: Архивация

- **WHEN** выполняется `archive_model.py claude-sonnet-4.5`
- **THEN** status в `data/models.yaml` меняется на archived
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

### Requirement: Визуальная пометка archived

Leaderboard (серверная страница) SHALL визуально отличать модели со `status: archived` от активных (приглушённая строка, плашка «неактивна» рядом с именем).

#### Scenario: Архивная модель в таблице

- **WHEN** модель C имеет `status: archived`
- **THEN** строка C отображается приглушённой с плашкой «неактивна»
- **AND** серверная таблица по умолчанию показывает только активные (параметр фильтра `active` / `all` / `inactive`)
