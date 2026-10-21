# Tasks

## 1. Карточка «Рейтинг» в консоли

- [x] 1.1 В `build_rating_svg()` (`tools/render_helpers.py`) убрать подпись
  «место не определено» и маркер `⋯`; добавить `<title>` к полосе группы
  (размер группы, «интервалы соседей перекрываются», для разрезанной группы —
  «продолжается на соседней странице») и к знаку `≈` у места. Проверка:
  `uv run python tools/test_analytics.py` — тесты SVG зелёные.
- [x] 1.2 В `rating_page()` передавать строкам размер их группы (`group_size`),
  чтобы тултип полосы считал по всему пулу, а не по видимому фрагменту.
  Проверка: тест разрезанной группы видит полный размер группы.
- [x] 1.3 В `tools/server.py` добавить в карточку «Рейтинг» строку-легенду с
  объяснением пометки «≈» (показывается, только если в пуле есть группы) и
  передать в контекст страницы число групп. Проверка:
  `uv run python tools/test_data_cache.py` — в HTML есть легенда и нет подписи
  «место не определено».

## 2. Статическое зеркало

- [x] 2.1 В `tools/static/js/mirror.js` повторить правки SVG: без подписи и
  маркера, `<title>` у полосы группы и у знака `≈`, размер группы в
  `ratingPage()`. Проверка: `uv run python tools/test_export.py` и
  `tools/test_data_cache.py` зелёные.
- [x] 2.2 В `mirror.js` прятать легенду, когда в отобранном под фильтр составе
  нет групп неразличимых мест. Проверка: `tools/test_export.py` — в слепке есть
  маркер `rating-legend` и легенда карточки.
- [x] 2.3 Удалить из `tools/static/css/console.css` правила
  `.interval-group-label` и `.interval-group-cut`. Проверка: поиск по репозиторию
  не находит этих классов в коде.

## 3. Тесты, документация, проверки

- [x] 3.1 Обновить `tools/test_analytics.py`: вместо проверки подписи — проверка
  тултипов полосы и `≈`, отсутствия надписи над строками и размера группы по
  всему пулу.
- [x] 3.2 Обновить `tools/test_data_cache.py`: проверка легенды в HTML и
  отсутствия подписи «место не определено».
- [x] 3.3 Добавить пункт в `## [Unreleased]` файла `CHANGELOG.md`
  (категория **Изменено**) с инженерными деталями в `### Изменено`. Проверка:
  `uv run python scripts/check-version.py` проходит.
- [x] 3.4 Прогнать проверки репозитория: `uv run python tools/test_elo.py`,
  `tools/test_data_cache.py`, `tools/test_export.py`, `tools/test_analytics.py`,
  `tools/test_trends.py`, `tools/test_migrate_journal.py`,
  `tools/test_pairing.py` и `openspec validate --all` — всё зелёное.

## Workflow follow-up

- Синхронизировать дельту в основную спеку `openspec/specs/leaderboard-ui/spec.md`
  и `openspec/specs/static-mirror/spec.md` и заархивировать изменение.
- Коммит и релиз — по отдельному указанию владельца.
