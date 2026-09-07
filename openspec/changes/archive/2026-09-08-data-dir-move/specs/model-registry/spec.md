## MODIFIED Requirements

### Requirement: Формат реестра

Модели SHALL храниться в `data/models.yaml` списком `models:`. Каждая запись:
`id` (slug, стабильный), `name` (человекочитаемое имя), опциональные `provider`,
`version`, `released`, `notes`; `status`: `active` | `archived` (по умолчанию
`active`). Комментарии-Шапка файла SHALL описывать формат и команды управления.

#### Scenario: Новая модель

- **WHEN** модель регистрируется
- **THEN** в `data/models.yaml` добавляется запись с id, name, status: active

#### Scenario: Архивная модель

- **WHEN** модель архивируется
- **THEN** её status меняется на archived
- **AND** метаданные (id, name, provider, version) сохраняются

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
