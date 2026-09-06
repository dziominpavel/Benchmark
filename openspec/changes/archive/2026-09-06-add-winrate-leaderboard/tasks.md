## 1. Общий helper форматирования

- [x] 1.1 Добавить функцию `format_winrate(wins, games)` в `tools/render_helpers.py`.
  - **Verification:** `python -c "import sys; sys.path.insert(0, 'tools'); from render_helpers import format_winrate; print([format_winrate(0, 0), format_winrate(3, 9), format_winrate(6, 10)])"` — должно вернуть `['—', '33.3%', '60.0%']`.
- [x] 1.2 Убедиться, что функция защищена от `ZeroDivisionError` (`games == 0` → `—`) и использует `:.1f` для форматирования.

## 2. Серверная таблица leaderboard

- [x] 2.1 Добавить заголовок `<th>Винрейт, %</th>` в `INDEX_TEMPLATE` в `tools/server.py` сразу после `<th>Всего</th>`.
- [x] 2.2 Добавить ячейку `<td class="winrate">{{ format_winrate(m.wins, m.games) }}</td>` в строку таблицы `INDEX_TEMPLATE` после ячейки `m.games`.
- [x] 2.3 Передать `format_winrate=format_winrate` в контекст `render_template_string(...)` в маршруте `leaderboard()`.
  - **Verification:** запустить `python tools/server.py`, открыть URL в браузере и увидеть новую колонку с правильными значениями; убедиться, что сортировка осталась по ELO.

## 3. Статический экспорт `leaderboard.html`

- [x] 3.1 Добавить заголовок `<th>Винрейт, %</th>` в строку заголовков таблицы в `tools/generate_html.py` после заголовка `games`.
- [x] 3.2 Добавить плейсхолдер `<td>{winrate}</td>` в `ROW_TEMPLATE` после `{games}`.
- [x] 3.3 В цикле генерации строк вычислить `winrate = format_winrate(m.get("wins", 0), m.get("games", 0))` и добавить `.replace("{winrate}", winrate)` в цепочку замен.
  - **Verification:** запустить `python tools/generate_html.py`, открыть `leaderboard.html` и увидеть новую колонку с `—` для моделей с `games == 0` и `X.Y%` для остальных.

## 4. Валидация и синхронизация спеки

- [x] 4.1 Запустить `python tools/test_elo.py` и `python tools/test_pairing.py`; убедиться, что регрессий нет.
- [x] 4.2 Запустить `openspec validate --change add-winrate-leaderboard` и исправить найденные замечания.
- [x] 4.3 При архивации чейнджа синхронизировать delta-спеку `openspec/changes/add-winrate-leaderboard/specs/leaderboard-ui/spec.md` в `openspec/specs/leaderboard-ui/spec.md` (через `openspec-sync-specs` или вручную).
