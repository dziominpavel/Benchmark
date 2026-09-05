## 1. Серверный UI

- [x] 1.1 В `tools/server.py` обновить CSS: `.page` контейнер (max-width 1400px, centered), `.content-grid` (`minmax(0, 1fr) 320px`), `.main-column` (`display: contents`), `.sidebar` (flex column, height 100%), `.rating-card` / `.history-details` grid-areas, `.table-wrap` + `table` responsive rules, адаптив `@media (max-width: 900px)`.
- [x] 1.2 Перестроить `INDEX_TEMPLATE`: обернуть всё в `.page`, header, `.controls`, `.content-grid` c `.main-column` (rating + history) и `.sidebar` (recommendations + form), убрать лишние контейнеры и вложенности.
- [x] 1.3 Запустить сервер и проверить layout на ширине 1920px и 2560px: контейнер ~1400px, таблица в main-column, история под ней той же ширины, sidebar выровнен с рейтингом, нет горизонтального скролла страницы.

## 2. Статический экспорт

- [x] 2.1 В `tools/generate_html.py` обновить CSS аналогично `server.py`.
- [x] 2.2 Обновить `HTML`-шаблон: тот же `.page` + `.content-grid` с `main-column` и `sidebar`.
- [x] 2.3 Сгенерировать `leaderboard.html` и проверить layout.

## 3. Спецификация

- [x] 3.1 Обновить `openspec/specs/leaderboard-ui/spec.md` с учётом нового layout: единый контейнер, grid, расположение истории, адаптивность.
