## Context

Текущая страница имеет `max-width: 1200px`, нестабильный grid и «Историю»
вне основной колонки, из-за чего блоки имеют разную ширину. См. proposal.md.

## Goals / Non-Goals

**Goals:**
- Единый `.page` контейнер с `max-width: 1400px`, центрированием и padding.
- `content-grid` с `minmax(0, 1fr) 320px`, `align-items: stretch`.
- `main-column` содержит рейтинг и историю.
- Sidebar — flex-колонка с двумя карточками, высота соответствует рейтингу.
- Таблица `width: 100%; min-width: 0;` в `.table-wrap` с `overflow-x: auto`.
- Те же правила в статическом `leaderboard.html`.

**Non-Goals:**
- Изменение цветов, текстов, ELO-логики, форм, данных.

## Decisions

- `body` оставляем с фоном и padding; внутри него `.page` задаёт max-width и
  горизонтальные padding.
- `content-grid` — единый grid; `.main-column` использует `display: contents`,
  чтобы дочерние `.rating-card` и `.history-card` участвовали в grid:
  - `grid-template-areas: "rating sidebar" "history .";`
  - row-gap 16px, column-gap 24px.
- `.sidebar` — `grid-area: sidebar`, `display: flex; flex-direction: column; gap: 16px; height: 100%;`.
- `.rating-card` — `grid-area: rating`, содержит `.table-wrap`.
- `.history-details` — `grid-area: history`.
- Таблица: `width: 100%; min-width: 0;`, `.table-wrap { overflow-x: auto; }`.
- Длинные имена моделей: `white-space: normal` для ячейки модели, `nowrap` для
  остальных колонок, чтобы избежать перекоса в сторону узких числовых ячеек.
- При `max-width: 900px` grid переключается в `1fr`.

## Risks / Trade-offs

- [Risk] `display: contents` у `.main-column` убирает собственный бокс —
  [Mitigation] используем только для layout, контент остаётся в валидной
  иерархии.
- [Risk] История остаётся под рейтингом и не растягивает sidebar —
  [Mitigation] так и задумано по ТЗ: sidebar выровнен с рейтингом.
