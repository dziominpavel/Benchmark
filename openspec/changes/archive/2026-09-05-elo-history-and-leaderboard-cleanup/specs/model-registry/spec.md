# model-registry Specification

## ADDED Requirements

### Requirement: Статус модели в index.json

`index.json["models"][<id>]` SHALL содержать поле `status` (`active` | `archived`), скопированное из `models.yaml`. UI и алгоритм рекомендаций SHALL использовать это поле без повторного чтения `models.yaml`.

#### Scenario: Статус в index.json

- **WHEN** `index.json` сгенерирован
- **THEN** каждая модель содержит `status`
- **AND** `pairing-algorithm` исключает модели со `status: archived`

### Requirement: Визуальная пометка archived

Leaderboard (сервер и статичный экспорт) SHALL визуально отличать модели со `status: archived` от активных (серый фон строки, текст `(archived)` рядом с именем или чекбокс «Показывать архивные»).

#### Scenario: Архивная модель в таблице

- **WHEN** модель C имеет `status: archived`
- **THEN** строка C отображается с пометкой или серым фоном
- **AND** `generate_html.py` по умолчанию скрывает архивные (как уже сделано в текущем экспорте)
