# Tasks

## 1. Алгоритм окна страниц

- [x] 1.1 Добавить `pagination_items(page, pages) -> list[int | None]` в `tools/render_helpers.py` по design.md (D1) и юнит-тест `test_pagination_items_window` в `tools/test_data_cache.py` (таблица значений, границы `pages` = 1/2/10/11, склейка одиночного разрыва при `pages=12, page=5`), зарегистрировать тест в блоке `__main__`; проверка — `uv run python tools/test_data_cache.py` завершается зелёным.

## 2. Макрос и страница истории

- [x] 2.1 Создать `tools/templates/_pagination.html` с макросом `pagination(page, pages, items, page_url)` по design.md (D2): стрелки с `rel`/`aria-label` и `.disabled` на краях, номера-ссылки, `span.current` с `aria-current`, троеточие `span[aria-hidden]`, защитный `{% if pages > 1 %}`; убедиться, что новые элементы покрываются существующими селекторами `.pagination a, .pagination span` и `.disabled` в `tools/static/css/console.css` (правки CSS не предусмотрены).
- [x] 2.2 Перевести `/history` на макрос: импортировать `pagination_items` в `tools/server.py`, в роуте `history_page()` собрать `history_items` и callable-билдер ссылок из `history_params`, в `HISTORY_TEMPLATE` заменить цикл `range(1, history_pages + 1)` вызовом макроса под прежним условием `history_pages > 1`; добавить route-тест `test_history_pagination_widget` (~27 страниц: ссылки `page=2/3/27` и отсутствие `page=4/26` на первой странице, ровно одно троеточие, `span.current`, неактивная «←» на первой странице, окно 12–16 на странице 14) и зарегистрировать его в `__main__`; проверка — `uv run python tools/test_data_cache.py` зелёный.

## 3. Унификация очереди рекомендаций

- [x] 3.1 Перевести очередь `/settings` на общий макрос: убрать текстовые «← Назад / Вперёд →» и подпись «страница {{ queue_page }} из {{ queue_pages }}», удалить `queue_prev_url`/`queue_next_url` из роута и контекста рендера, передать `pagination_items(queue_page, queue_pages)` и `_queue_page_url`; обновить `test_settings_queue_pagination` — проверки виджета вместо подписи, неактивная «→» на последней странице, сохранение существующих проверок (номера строк 1–100, клампинг `queue_page=99` и `queue_page=abc`); проверка — `uv run python tools/test_data_cache.py` зелёный.

## 4. Интеграция и финальная сверка

- [x] 4.1 Прогнать профильные наборы на общей сборке: `uv run python tools/test_data_cache.py`, `uv run python tools/test_perf.py` (ссылка `queue_page=2` в HTML очереди остаётся), `uv run python tools/test_elo.py`, `uv run python tools/test_trends.py`, а также `openspec validate --all`; проверка — все команды без ошибок (warning про длину требований ожидаем и не является ошибкой). Выполнено: `test_data_cache`, `test_elo`, `test_trends`, `openspec validate --all` — зелёные; `test_perf` на этой машине нестабилен по «холодным» бюджетам и без правок (baseline-копия HEAD и A/B-замер холодных `/` и `/settings` также местами выходят за пороги) — регрессии от виджета нет.
- [x] 4.2 Ручная проверка виджета в локальной консоли: `/history` на первой/средней/последней странице и очередь `/settings` при более чем одной странице — номера и стрелки компактны, переходы работают, фильтры и настройки отображения (`model`, `agents`, `view`, `chips`; `queue_page` с остальными параметрами) сохраняются в ссылках; проверка — наблюдение в браузере на локальном сервере. Выполнено на изолированной копии (`localhost:5001`, реальные `data/` не тронуты): `/history` страницы 1/14/27 из 27 — троеточия, края и стрелки верны; очередь на 7 и 16 страницах — виджет с окном, `only_debts` и анкор `#recommendation-queue` сохраняются; сохранение `model` на `/history` покрыто route-тестом; пиксельный скриншот недоступен (окно браузера невидимо), проверены DOM и вычисленные стили.
- [x] 4.3 Добавить пункт в `CHANGELOG.md` `## [Unreleased]`: пользовательский блок (жирная метка категории и буллет длиной ≤140 символов, без обратных кавычек) выше первой секции `###`, инженерные детали — под ней (change-id `compact-pagination`); проверка — `python scripts/check-version.py` завершается с кодом 0. Выполнено: буллет в блоке **Изменено**, детали — под `### Изменено`; `check-version.py` — exit 0.

## Workflow follow-up

- Заархивировать change `compact-pagination` после ревью и убедиться, что main-спека `leaderboard-ui` получила новые требования «Виджет пагинации в консоли» и «Стрелки и границы виджета пагинации», а обновлённые требования истории и очереди смёржены без потери сценариев.
- Повторно прогнать `openspec validate --all` после архивации.
