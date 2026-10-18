# Tasks

## 1. Счётчик записей в заголовке истории (п. 11)

- [x] 1.1 `plural_ru(n, one, few, many)` в `tools/render_helpers.py` (11–14 → many, модуль числа); проверить: `py -3 tools/test_analytics.py` — `test_plural_ru` (0/1/2/5/11/21/102/595/602).
- [x] 1.2 `history_page`: лейбл `history_found_label` по `history_found`; блок `title` истории — «История — {{ history_found_label }} — ELO Benchmark»; проверить: `py -3 tools/test_data_cache.py` — `test_wave5_history_title` («1 запись» без фильтров и с `model=alpha`, «0 записей» на пустой выборке).

## 2. Кликабельность графиков (ревизия 2 к п. 4)

- [x] 2.1 «Распределение Elo»: `id` в entries `stats_page`; бар и имя обёрнуты в `/model/<id>` (`dist-link`), hover-цвет имени; проверить: `test_elo_distribution_links`, зеркало — `class="dist-link"` в `test_export_stats_analytics`.
- [x] 2.2 «Динамика ELO»: хит-слой `chart-line-hit` (stroke-width 12, `pointer-events: stroke`) со ссылкой `/model/<id>`, конец линии в том же якоре; серия без `id` — без ссылки; проверить: `test_elo_multiline_svg`.
- [x] 2.3 «Активность по дням»: `links=True/False`; столбик дня — `/history?from=D&amp;to=D`, нулевой — без ссылки; вызов `links=not read_only()`; проверить: `test_activity_bars_svg`, `test_wave5_chart_links` (read-only без ссылок дат), `test_export_stats_analytics` (`/history?from=` вне слепка).
- [x] 2.4 График профиля: `point_links` в `get_model_detail` ([None] + {url, title} на матч); `build_elo_svg(links=...)` — хит-круг r=9 `chart-dot-hit` со ссылкой `/history?v=<seq>#v-<seq>`; проверить: `test_elo_svg_point_links`, `test_wave5_chart_links`, `test_export_profile` (`chart-dot-link` в слепке).
- [x] 2.5 Стили `console.css` (хит-слои, hover `dist-link`); проверить: `py -3 tools/test_perf.py` (бюджеты), `py -3 tools/test_elo.py`.

## 3. Доки и changelog

- [x] 3.1 `docs/ui-ux-review.md`: ревизия 7, карта роутов (`/task/<id>`, дашборд `/stats`), разрывы 114–117, статусы разделов 4/8/9/11, «Сделано (волна 5)», роадмап (волна 5).
- [x] 3.2 `CHANGELOG.md` `[Unreleased]`: пользовательские пункты (графики-точки входа, точки профиля, счётчик в заголовке) и инженерные детали `console-wave5-links`.
- [x] 3.3 Проверки: `py -3 tools/test_analytics.py`, `py -3 tools/test_data_cache.py`, `py -3 tools/test_export.py`, `py -3 tools/test_perf.py`, `py -3 tools/test_elo.py`, `py -3 scripts/check-version.py`, `openspec validate console-wave5-links --strict`.
