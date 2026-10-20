# Tasks

## 1. Подготовка: состояние репозитория и параллельные change

- [x] 1.1 Сверить `git status --short`, `openspec list --json` и состояние незакрытых change `filter-settings-trigger` и `live-search`: зафиксировать порядок правок общих файлов (`tools/templates/_tag_filter.html`, `tools/templates/shell.html`, `tools/static/css/console.css`, `tools/test_data_cache.py`, `tools/test_export.py`) и не перезаписывать чужие изменения. Проверка: зафиксированный список файлов и их текущее состояние в заметках к задаче; `git diff` до начала правок сохранён.
  - Исходное состояние: HEAD `9cae0433`; изменены `CHANGELOG.md`, `tools/server.py`, `tools/static/css/console.css`, `tools/templates/_tag_filter.html`, `tools/templates/shell.html`, `tools/test_data_cache.py`, `tools/test_export.py`; новые `tools/static/js/filter-panel.js`, `tools/static/js/live-search.js`, `tools/templates/_history_results.html`. Снимки `git status --short` и `git diff` сохранены во временный каталог (`caption-baseline-status.txt`, `caption-baseline-diff.txt`).
  - По ходу работы параллельная сессия закрыла `filter-settings-trigger` (`2c72e57`) и `live-search` (`28617a8`) и закоммитила `console-wave6-analytics-scale` (`c6838c1`), переписав `tools/render_helpers.py` (`build_elo_distribution_svg`/`build_rating_intervals_svg` → `rating_page()`/`build_rating_svg()`). Контракт данных `caption` сохранён.
  - Первая попытка реализации (дефолт «подписи видны») свёрнута: по исходному ТЗ дефолт — флажок **выключен**, и при нём механизм радикально проще (скрытое поле-компаньон не нужно). Откат сделан (`git checkout --` по семи файлам), чужие правки соседней сессии не задеты.
- [x] 1.2 Зафиксировать исходный результат тестов: `uv run python tools/test_data_cache.py` и `uv run python tools/test_export.py`; отдельно отметить красные места, относящиеся к `live-search`, чтобы отличить их от регрессий этого change. Проверка: в заметках к задаче записан список падающих тестов до правок.
  - Baseline (через `.venv\Scripts\python.exe`, команды `uv` в PATH нет): `tools/test_data_cache.py` — exit 0, «ALL DATA CACHE TESTS PASSED»; `tools/test_export.py` — exit 0, «ALL EXPORT TESTS PASSED». Красных мест нет.

## 2. Сервер: параметр `captions` и флажок в панели

- [x] 2.1 В `tools/server.py` рядом с `valid_filter_view()` и `valid_chips_order()` добавить разбор состояния подписей: читать `request.args.get("captions")`; значение `show` — подписи видны, отсутствие или невалидное значение — скрыты (дефолт). Проверка: `GET /?captions=lol` и `GET /?` не выводят подписи, `GET /?captions=show` выводит; проверка покрыта тестом из 2.5.
  - Значение по умолчанию — «скрыты»: браузер не шлёт неотмеченный флажок, значит «скрыто» = «параметра нет», отдельное скрытое поле-компаньон не требуется.
  - `valid_captions_state()` переписан: валидное значение только `show`, всё прочее (включая `hide` и мусор) → «скрыты». Прежняя пара значений `show`/`hide` с дефолтом «show» и скрытым полем-компаньоном (change `filter-settings-trigger`, коммит `2c72e57`) заменена: дефолт нового change — подписи скрыты, компаньон не нужен.
- [x] 2.2 В `filter_panel_context()` разобрать состояние подписей, отдать его в контекст (`filter_captions_hidden`), добавить часть «подписи видны» в бейдж свёрнутой раскрывашки, а при видимых подписях — `captions=show` в hidden-поля `filter_hidden()` и в параметры ссылки «Сбросить». Проверка: `GET /?captions=show` содержит `captions=show` в hidden-полях и в ссылке «Сбросить», бейдж содержит «подписи видны»; без параметра — ни того, ни другого.
  - Заодно `captions=show` переносится в redirect'ах POST-форм `/settings` (`_settings_filter_params`) и в ссылках пагинации истории/аналитики (`history_params`, `_stats_url`).
  - Ключ контекста `filter_captions_hidden` сохранён (его использует соседний change `history-row-grid`), инвертировано только его значение: True = подписи скрыты.
- [x] 2.3 В `tools/templates/_tag_filter.html` добавить в раскрывашку «Настройки фильтра» третий пункт — флажок «Отражать агент-компанию» (снят по умолчанию) со значением `show` и `onchange="this.form.submit()"`. Проверка: в HTML есть `input[type=checkbox][name=captions][value=show]`; при отсутствии `captions` в адресе флажок снят.
  - Скрытое поле-компаньон не нужно: снятый флажок = «параметра нет» = дефолт «скрыты».
  - Колонка подписи панели — «Подпись модели» (как требует сценарий спеки «Подписи сегментов настроек»).
- [x] 2.4 В `tools/static/css/console.css` оформить пункт с флажком в панели настроек (колонка подписи, выравнивание, отмеченное состояние) для тёмной и светлой тем; проверить, что бейдж «подсветка · чипы по ELO · подписи видны» не ломает вёрстку раскрывашки. Проверка: скриншот/ручной прогон на 360 px в обеих темах.
  - Правила `.filter-check` (галочка `accent-color`, подпись, отмеченное состояние) — обе темы берут свои токены, отдельных правил не нужно; бейдж не разрывает строку — `overflow-wrap: anywhere` у кнопки настроек.
  - Проверка без скриншота (окно браузера в этой среде недоступно для съёмки): замеры в DOM. На 360 px (страница вложена в iframe шириной 360 px) горизонтального переполнения нет (`scrollWidth` = `clientWidth` = 345), бейдж переносится на две строки (высота 46 px), флажок видим (16×16). Тёмная тема: подпись `rgb(233,237,244)`, акцент `rgb(122,165,255)`; светлая: `rgb(23,27,34)`, акцент `rgb(29,78,216)`; отмеченное состояние — цвет текста и насыщенность 600.
- [x] 2.5 Дополнить `tools/test_data_cache.py` тестами на серверную часть: дефолт (флажок снят, подписи скрыты), `captions=show` (подписи видны, бейдж «подписи видны»), невалидное значение → дефолт, ссылка «Сбросить» сохраняет `captions=show`, hidden-поля содержат `captions=show` только при видимых подписях. Проверка: `uv run python tools/test_data_cache.py` — новые тесты зелёные.
  - Новый тест `test_caption_toggle_server`; прогон: `tools/test_data_cache.py` — «ALL DATA CACHE TESTS PASSED».

## 3. Гашение подписи в выводе страниц

- [x] 3.1 Главная (наполнение `caption` в строках рейтинга и списка «Модели»): пока подписи скрыты, не наполнять поле, чтобы подпись не попадала в HTML. Проверка: `GET /?captions=show` содержит `model-caption` у моделей; без параметра — нет.
  - Архивный список собирать копиями строк, а не правкой memo-индекса: значение зависит от запроса и иначе залипло бы между запросами.
  - Рейтинг и список «Модели» берут подпись из `page_caption()` — общий помощник с `history-row-grid`.
- [x] 3.2 `/add`, `/settings`, `/history`: пока подписи скрыты, не наполнять `caption` и `caption_map`; подписи страницы задачи (идентификатор таски, «Проект:», «baseline:») MUST NOT затрагиваться. Проверка: `GET /settings?captions=show`, `GET /add?captions=show`, `GET /history?captions=show` содержат подписи агента-компании; без параметра — нет; `GET /task/<id>` содержит «baseline:».
  - `/task/<id>` и `/model/<id>` блока «Фильтр» не имеют — там подпись выводится всегда (`format_model_caption`), как и решает design (п. 5).
- [x] 3.3 `/stats`: пока подписи скрыты, карта подписей для SVG-баров пуста — `dist-caption` не выводится (`tools/render_helpers.py`). Проверка: `GET /stats?captions=show` содержит `dist-caption`, без параметра — нет.
  - Правки в `tools/render_helpers.py` не потребовались: `build_rating_svg()` берёт подпись из строки, а строка гасится на уровне данных (`page_caption()` в маршруте `/stats`).
- [x] 3.4 Экспорт данных: подпись остаётся в данных независимо от `captions` — это данные, а не вид. Проверка: `GET /export/rating.csv?captions=show` сохраняет колонки «Компания»/«Агент», JSON — поля `provider`/`agent`; остров реестра слепка сохраняет ключ `c`.
  - Экспорт берёт `provider`/`agent` из строк реестра, а не поле `caption`, поэтому гашение подписи его не затрагивает; остров слепка (`build_models_island`) по-прежнему кладёт `c` = `format_model_caption(...)`.
- [x] 3.5 Дополнить `tools/test_data_cache.py` тестами на гашение подписи по страницам (главная, `/add`, `/settings`, `/history`, `/stats`, страница задачи) и на неизменность поля подписи в экспорте. Проверка: `uv run python tools/test_data_cache.py` — новые тесты зелёные.
  - Новый тест `test_caption_hidden_per_page`; прогон: `tools/test_data_cache.py` — «ALL DATA CACHE TESTS PASSED».

## 4. Статический слепок

- [x] 4.1 В `tools/static/js/mirror.js` применить параметр `captions=show` из адреса: показать подписи, которых в статике нет по умолчанию, — то есть в слепке подписи выводятся только при `captions=show` (механизм применения фильтров из адреса в слепке уже есть). Проверка: в собранном слепке страница с `?captions=show` показывает подписи, без параметра — не показывает.
  - Витрина не отличается от живой консоли: тот же флажок, тот же параметр, то же поведение; разница только в запрете менять данные.
  - В слепке подписи предрендерены (это данные), а показ ведёт клиент: `applyCaptions()` ставит класс `captions-off`, если `captions=show` в адресе нет; флажок панели синхронизируется с адресом (`syncFromUrl`), состояние живёт в форме и попадает в `writeUrl` — как остальные настройки блока.
  - Класс `captions-off` не ставится на страницах без блока «Фильтр» (страница модели, страница задачи): там подпись видна всегда.
  - Проверка на собранном слепке: главная без параметра — `body.captions-off`, подписи в DOM (37), видимых 0; с `?captions=show` — видимы все 37, бейдж «подписи видны», флажок отмечен. История: 1350 подписей в DOM, видимы 20 записей (по 2 стороны) вместе с разделителями «·». «Аналитика»: 32 подписи в SVG (`dist-caption`) скрыты, с параметром — видимы. Клик по флажку в слепке применяет состояние без перезагрузки и пишет `?captions=show` в адрес.
- [x] 4.2 В `tools/export_web.py` проверить, что подписи в payload зеркала остаются (это данные), а состояние `captions` доступно клиенту. Проверка: в собранном слепке payload содержит подписи, а `mirror.js` умеет их показывать по `captions=show`.
  - Страницы слепка собираются с `captions=show` (`CAPTIONS_QUERY`) — подписи попадают в статику; остров реестра по-прежнему несёт `c` = подпись (`build_models_island`).
  - Чтобы слепок открывался в состоянии «подписи скрыты», в разметку body добавляется класс `captions-off` (`_body_with_captions_off`), а из запечённых ссылок параметр убирается (`_strip_captions`) — состояние подписей, как и остальных настроек, ведёт клиентский слой.
- [x] 4.3 Дополнить `tools/test_export.py`: в слепке есть флажок «Отражать агент-компанию» в панели настроек, `mirror.js` обрабатывает `captions`, подписи в payload сохранены. Проверка: `uv run python tools/test_export.py` — новые тесты зелёные.
  - Новый тест `test_export_captions_toggle`; прогон: `tools/test_export.py` — «ALL EXPORT TESTS PASSED».

## 5. Changelog

- [x] 5.1 В `CHANGELOG.md` в секцию `[Unreleased]` в пользовательский блок добавить пункт в категорию «Добавлено» (строка ≤140 символов, без обратных кавычек): переключатель «Отражать агент-компанию» в настройках фильтра, по умолчанию скрывающий подпись «Компания · Агент». Проверка: `python scripts/check-version.py` завершается с кодом 0.
  - Пункт: «Переключатель «Отражать агент-компанию» в настройках фильтра: подпись «Компания · Агент» по умолчанию скрыта.»
- [x] 5.2 В `CHANGELOG.md` в инженерный подраздел `### Добавлено` добавить детали: change-id `caption-visibility-toggle`, файлы (`tools/server.py`, `tools/templates/_tag_filter.html`, `tools/static/css/console.css`, `tools/static/js/mirror.js`, `tools/export_web.py`), параметр `captions`, тесты в `tools/test_data_cache.py` и `tools/test_export.py`. Проверка: `python scripts/check-version.py` — код 0, формат блока не нарушен.
  - `python scripts/check-version.py` — код 0 (1 предупреждение о накопленных пунктах, 0 ошибок).

## 6. Интеграционная проверка

- [x] 6.1 Ручной прогон в браузере на `/`, `/stats`, `/history`, `/add`, `/settings`: флажок в панели, применение по клику без кнопки, подписи появляются и исчезают, «Сбросить» сохраняет состояние, бейдж в свёрнутом виде, обе темы, экран 360 px. Проверка: зафиксированные наблюдения в заметках к задаче; расхождений со спецификациями нет.
  - Живая консоль (`http://127.0.0.1:5001`): без параметра подписи скрыты на всех пяти страницах (0 элементов `.model-caption` / `.dist-caption`), бейдж «Настройки фильтра», флажок снят; с `?captions=show` — подписи на месте (главная 37, `/stats` 32 подписи в SVG, `/history` 40, `/add` 37, `/settings` 69), бейдж «Настройки фильтра — подписи видны», флажок отмечен, ссылка «Сбросить» сохраняет `?captions=show`.
  - Применение по клику без кнопки: снятие флажка отправляет форму (GET) — адрес становится без `captions`, подписи исчезают, бейдж пустеет.
  - Слепок (собран `tools/export_web.py`, отдан статикой): по умолчанию `body.captions-off` и 0 видимых подписей, с `?captions=show` — видны; флажок кликается и меняет состояние без перезагрузки.
  - Скриншоты в этой среде недоступны (окно браузера не отдаёт кадры) — проверка сделана замерами в DOM, включая 360 px через iframe.
- [x] 6.2 Прогнать `uv run python tools/test_data_cache.py`, `uv run python tools/test_export.py` и `openspec validate --all` — всё зелёное. Проверка: вывод команд и список известных отклонений.
  - Известное отклонение (на 20.10.2026): `openspec validate --all` даёт 14/15 из-за чужого change `fix-elo-dynamics-model-picker` (создан параллельной сессией, дельт нет).
  - Факт (21.10.2026): `tools/test_data_cache.py` — exit 0, «ALL DATA CACHE TESTS PASSED»; `tools/test_export.py` — exit 0, «ALL EXPORT TESTS PASSED»; `openspec validate --all` — «Totals: 15 passed, 0 failed», exit 0 (прежнее отклонение по `fix-elo-dynamics-model-picker` больше не воспроизводится — change закрыт). Дополнительно зелёные: `tools/test_analytics.py`, `tools/test_trends.py`, `tools/test_elo.py`, `tools/test_migrate_journal.py`.
  - Отклонение: `tools/test_perf.py` — «главная, холодная (типовое покрытие, 100 флагов)» 0.567 с при бюджете 0.5 с. Причина — нагрузка машины (параллельная сессия), а не change: A/B-замер в одном процессе (только `page_caption` ↔ `format_model_caption`) даёт 0.462 с против 0.498 с, а на baseline-коммите `26a577c` (до этого change) тот же бюджет превышается сильнее — 0.772 с, плюс превышен предельный бюджет.
- [x] 6.3 Сверить итоговый `git status --short` и `git diff` с начальным состоянием: изменения только в файлах этого change и ожидаемых общих файлах; чужие правки соседних сессий сохранены; HEAD не менялся. Проверка: diff не содержит удаления чужих изменений.
  - Файлы этого change: `tools/server.py` (валидатор, контекст панели, гашение подписи на страницах с блоком «Фильтр», redirect'ы и пагинация), `tools/templates/_tag_filter.html` (флажок), `tools/static/css/console.css` (`.filter-check`, перенос бейджа), `tools/static/js/mirror.js` (состояние подписей в клиентском слое), `tools/export_web.py` (предрендер подписей и класс в разметке), `tools/test_data_cache.py` и `tools/test_export.py` (тесты), `CHANGELOG.md` (пункт и детали).
  - Правки в `tools/server.py`, `tools/static/css/console.css`, `tools/static/js/mirror.js` и `tools/test_data_cache.py` попали в коммит `93e3a92` соседней сессии (она закоммитила общую рабочую копию целиком) — изменения этого change в них сохранены; не закоммичены `tools/export_web.py`, `tools/templates/_tag_filter.html`, `tools/test_export.py`, `CHANGELOG.md` и каталог change.
  - Чужие изменения на месте: `data/index.json`, `data/models.yaml` (данные соседней сессии) не тронуты; правки соседнего change `history-row-grid` (сетка колонок ленты, `page_caption()` в истории, `body.captions-off`) сохранены, его тест `test_history_caption_divider` переведён на новую полярность `captions=show` и проходит.
  - HEAD в начале работы — `084771e`, в конце — `93e3a92`: коммиты сделала соседняя сессия (история переписана rebase), этот change HEAD не двигал.

## Workflow follow-up

- Применить дельту к `openspec/specs/leaderboard-ui/spec.md` (требования «Состав блока «Фильтр»» и «Подпись агента и фирмы у модели»).
- Архивировать change после приёмки.
