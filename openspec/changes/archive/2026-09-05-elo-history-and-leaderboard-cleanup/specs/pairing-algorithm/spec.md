# pairing-algorithm Specification

## REMOVED Requirements

### Requirement: Отсутствие фильтра архивных моделей

**Reason:** Архивные модели не должны участвовать в новых сравнениях, поэтому фильтр необходим.

**Migration:** Новое поведение описано в `## ADDED Requirements` ниже.

## ADDED Requirements

### Requirement: Фильтр архивных моделей

Алгоритм SHALL исключать модели со `status: archived` из кандидатов на сравнение. `get_recommendations` SHALL читать `status` из `index.json["models"][<id>]["status"]` и пропускать архивные модели. Пары, в которых хотя бы одна модель `archived`, SHALL NOT появляться в рекомендациях.

#### Scenario: Архивная модель исключена

- **WHEN** модель C имеет `status: archived`
- **THEN** пары с участием C не предлагаются в блоке рекомендаций

#### Scenario: Активная модель предлагается

- **WHEN** обе модели в паре имеют `status: active`
- **THEN** пара MAY появиться в рекомендациях при прочих условиях
