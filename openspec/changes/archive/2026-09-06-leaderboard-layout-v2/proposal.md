## Why

Текущий layout главной страницы ELO Benchmark слишком узкий, элементы имеют разную ширину, а sidebar не выровнен с основной областью. Это создаёт визуальный шум и пустое пространство на широких мониторах.

## What Changes

- Расширить page container до ~1400px и центрировать его.
- Объединить header, controls и content в единый контейнер.
- Пересобрать grid: основная колонка `minmax(0, 1fr)`, sidebar `320px`.
- Переместить блок «История» внутрь `main-column` под рейтинг, сделав его ширину равной ширине рейтинга.
- Сделать таблицу адаптивной: `width: 100%`, `min-width: 0`, горизонтальный скролл внутри `.table-wrap`.
- Sidebar выровнять по высоте с карточкой рейтинга и не растягивать искусственно.
- Обновить те же правила в статическом `leaderboard.html`.

## Capabilities

### Modified Capabilities

- `leaderboard-ui`: обновлены layout- и адаптивные требования.

## Impact

- `tools/server.py` — CSS и `INDEX_TEMPLATE`.
- `tools/generate_html.py` — CSS и HTML-шаблон.
- `openspec/specs/leaderboard-ui/spec.md` — layout-уточнения.
