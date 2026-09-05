# model-registry Specification

## Purpose
Реестр моделей с статусами (active/archived). Саморегистрация новых моделей, архивация неактуальных. ELO хранится в index.json (генерируется), метаданные — в models.yaml (source of truth).

## Requirements

### Requirement: Формат реестра

Модели хранятся в `models.yaml`. Каждая модель: id (slug), name, provider (опц.), version (опц.), released (опц.), status (active | archived, по умолчанию active), notes (опц.).

#### Scenario: Новая модель

- **WHEN** модель регистрируется
- **THEN** в models.yaml добавляется запись с id, name, status: active

#### Scenario: Архивная модель

- **WHEN** модель архивируется
- **THEN** её status меняется на archived
- **AND** метаданные (id, name, provider, version) сохраняются

### Requirement: Саморегистрация

Модель может саморегистрироваться через `python tools/register_model.py --auto --id <slug> --name "<name>"`. Поля provider/version опциональны.

#### Scenario: Саморегистрация

- **WHEN** выполняется register_model.py --auto --id gpt-5 --name "GPT-5"
- **THEN** модель добавляется в models.yaml со status: active

#### Scenario: Уже зарегистрирована

- **WHEN** модель с id gpt-5 уже существует
- **THEN** скрипт сообщает "Модель уже зарегистрирована" и завершается успешно

### Requirement: Архивация модели

Архивация через `python tools/archive_model.py <model-id>`. Модель получает status: archived. ELO замораживается. История вердиктов сохраняется.

#### Scenario: Архивация

- **WHEN** выполняется archive_model.py claude-sonnet-4.5
- **THEN** status в models.yaml меняется на archived
- **AND** ELO в index.json не пересчитывается с новыми вердиктами (нет новых)
- **AND** старые вердикты остаются в matchups/

#### Scenario: Архивация несуществующей модели

- **WHEN** выполняется archive_model.py non-existent-model
- **THEN** скрипт сообщает "Модель не найдена" и завершается с ошибкой

### Requirement: Разархивация

Разархивация через `python tools/archive_model.py --restore <model-id>`. Модель получает status: active. ELO не сбрасывается (сохраняется последнее значение).

#### Scenario: Разархивация

- **WHEN** выполняется archive_model.py --restore claude-sonnet-4.5
- **THEN** status меняется на active
- **AND** ELO остаётся прежним
- **AND** модель снова участвует в предложениях пар

### Requirement: Стабильность id

id модели неизменен после создания. При выходе новой версии (claude-sonnet-4.5 → 4.6) создаётся новый id, старый архивируется.

#### Scenario: Новая версия модели

- **WHEN** выходит Claude Sonnet 4.6
- **THEN** создаётся новый id: claude-sonnet-4.6
- **AND** старый claude-sonnet-4.5 архивируется (если пользователь решит)
- **AND** история 4.5 сохраняется

### Requirement: ELO не в models.yaml

ELO и статистика (W/L/D, games) хранятся в index.json (генерируется из matchups). models.yaml содержит только метаданные.

#### Scenario: Ручное редактирование models.yaml

- **WHEN** пользователь редактирует models.yaml (добавляет notes, меняет provider)
- **THEN** ELO не затрагивается (его нет в models.yaml)
- **AND** при следующем пересчёте ELO берётся из matchups/
