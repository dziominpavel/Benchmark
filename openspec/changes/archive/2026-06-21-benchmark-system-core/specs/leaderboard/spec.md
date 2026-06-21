## ADDED Requirements

### Requirement: Агрегация вердиктов в leaderboard

`tools/aggregate.py` MUST читать вердикты из `verdicts/<wave>/<run-id>/<judge-id>.md`, вычислять медиану по 3 судьям для каждого пункта, деанонимизировать через `waves/<wave>/anonymization.yaml` и генерировать `leaderboard.md`.

#### Scenario: Leaderboard сгенерирован

- **WHEN** все вердикты волны `wave-01-2026Q3` созданы
- **THEN** `python tools/aggregate.py` генерирует `leaderboard.md`
- **AND** таблица содержит реальные `model_id` (деанонимизированные)

#### Scenario: Нет вердиктов

- **WHEN** в `verdicts/` нет файлов
- **THEN** `aggregate.py` генерирует `leaderboard.md` с сообщением «Нет вердиктов»

### Requirement: Деанонимизация через anonymization.yaml

`aggregate.py` MUST читать `waves/<wave>/anonymization.yaml` и заменять «Участник X» на реальный `model_id` в leaderboard. `anonymization.yaml` — единственный мост между анонимизированными вердиктами и публичным leaderboard.

#### Scenario: Деанонимизация

- **WHEN** вердикт судит «Участник A» с баллом 4.5
- **AND** `anonymization.yaml` содержит `claude-sonnet-4.5 → Участник A`
- **THEN** leaderboard показывает `claude-sonnet-4.5 | 4.5`

### Requirement: Структура leaderboard

`leaderboard.md` MUST содержать: общий рейтинг моделей (средний нормализованный балл), разбивку по категориям (F/B/R/V), разбивку по волнам. Каждая таблица — Markdown.

#### Scenario: Общий рейтинг

- **WHEN** leaderboard сгенерирован
- **THEN** секция «Общий рейтинг моделей» содержит таблицу: Модель | Прогонов | Средний балл | F | B | R | V

#### Scenario: По волнам

- **WHEN** существует 2 волны с прогонами
- **THEN** секция «По волнам» содержит подтаблицу для каждой волны

### Requirement: Спорные прогоны в leaderboard

Прогоны с разбросом судей > 2 баллов по любому пункту MUST быть помечены `disputed` в leaderboard. Пользователь разбирает их руками и MAY обновить вердикт.

#### Scenario: Disputed помечен

- **WHEN** прогон F-001 участника A имеет разброс 3 по пункту «Корректность»
- **THEN** в leaderboard строка участника A для F-001 помечена `⚠ disputed`
- **AND** в `waves/<wave>/disputed.md` (или эквиваленте) зафиксированы детали спора

### Requirement: Только stdlib Python

`aggregate.py` MUST использовать только стандартную библиотеку Python (без PyYAML, без внешних пакетов). Front matter парсится вручную.

#### Scenario: Запуск без зависимостей

- **WHEN** выполняется `python tools/aggregate.py`
- **THEN** скрипт работает без установки дополнительных пакетов
- **AND** использует только `os`, `re`, `sys`, `collections`, `dataclasses`, `pathlib`, `typing`

### Requirement: Перегенерация leaderboard

`aggregate.py` MUST перегенерировать `leaderboard.md` полностью при каждом запуске. Ручные правки `leaderboard.md` не сохраняются — файл не редактируется руками.

#### Scenario: Перегенерация

- **WHEN** `aggregate.py` запущен повторно после новых вердиктов
- **THEN** `leaderboard.md` полностью перезаписан
- **AND** содержит актуальные данные из всех вердиктов

### Requirement: Качество судей (согласованность)

`aggregate.py` MUST вычислять для каждого судьи средний разброс его оценок с другими судьями по тем же прогонам. Низкая согласованность (средний разброс > 1.5) — сигнал заменить судью в следующей волне. Разброс выводится в `leaderboard.md` и `waves/<wave>/summary.md`.

#### Scenario: Согласованный судья

- **WHEN** судья `claude-sonnet-4.5` оценил 24 прогона, средний разброс с другими судьями = 0.4
- **THEN** в leaderboard он помечен как `согласован: 0.4`
- **AND** в `summary.md` рекомендуется оставить судьёй на следующую волну

#### Scenario: Расходящийся судья

- **WHEN** судья `glm-4.6` оценил 24 прогона, средний разброс = 1.8
- **THEN** в leaderboard он помечен как `расходится: 1.8`
- **AND** в `summary.md` рекомендуется заменить или не назначать на критичные прогроны

### Requirement: Карта назначений судей

`aggregate.py` MUST генерировать таблицу назначений: для каждого прогона (задача × участник) — 3 судьи с их оценками и итоговой медианой. Это даёт полную картину кто судил что и как.

#### Scenario: Карта в leaderboard

- **WHEN** leaderboard сгенерирован
- **THEN** секция «Карта назначений» содержит таблицу: Задача | Участник | Судья 1 | Судья 2 | Судья 3 | Медиана
- **AND** для спорных прогонов строка помечена `⚠ disputed`
