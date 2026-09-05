## Why

Цветные ELO-бейджи на leaderboard и в статическом экспорте создают визуальный шум. Убрав цветовое кодирование, оставим интерфейс чище и акцентируем внимание на самих рейтинговых значениях.

## What Changes

- Убрать CSS-классы `.elo-badge`, `.elo-high`, `.elo-mid` и `.elo-low` из `tools/server.py`.
- Убрать классы `.elo-high`, `.elo-mid`, `.elo-low` из `tools/generate_html.py` и оставить ELO-цифры без цветового выделения.
- Обновить `openspec/specs/leaderboard-ui/spec.md`: убрать упоминание цветных бейджей из сценария отображения рейтинга.

## Capabilities

### New Capabilities

- (нет)

### Modified Capabilities

- `leaderboard-ui`: изменяется сценарий отображения таблицы рейтинга — ELO показывается простым числом без цветного фона/шрифта.

## Impact

- `tools/server.py` — шаблоны таблицы рейтинга и страницы модели.
- `tools/generate_html.py` — статический HTML-шаблон и генератор строк.
- `openspec/specs/leaderboard-ui/spec.md` — нормативное описание внешнего поведения UI.
