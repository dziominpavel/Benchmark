## 1. Статистика пары в server.py

- [x] 1.1 Заменить `get_pair_game_counts` на `get_pair_stats` в `tools/server.py`: один проход по `load_matchups()`, пропуск tombstone- и аннулированных вердиктов, возврат `{frozenset({a, b}): {"games": int, "wins": {model_id: int}}}`; `winner: "a"/"b"` маппится на id через `resolve_matchup_models`, `draw` увеличивает только `games`. Проверка: `python -c "import sys; sys.path.insert(0,'tools'); import server; print(server.get_pair_stats())"` возвращает словарь без ошибок.
- [x] 1.2 Обновить `get_recommendations`: использовать `get_pair_stats`, в запись добавить `pair_wins_a`, `pair_wins_b` и `h2h_label` («личные встречи: N · счёт W_a:W_b» для сыгранной пары, «личные встречи: не встречались» для `pair_games == 0`); удалить формирование и поле `reason`. Сортировку `(pair_games, tier, -score)` не менять. Проверка: `python -c "import sys,json; sys.path.insert(0,'tools'); import server; idx=json.load(open('index.json',encoding='utf-8')); print(server.get_recommendations(idx))"` — в записях есть `h2h_label`, нет `reason`.

## 2. Шаблон карточки рекомендации

- [x] 2.1 В `INDEX_TEMPLATE` заменить `<div class="rec-reason">{{ rec.reason }}</div>` на строку личных встреч `{{ rec.h2h_label }}`; CSS-класс переименовать в `rec-h2h` (стили те же) либо переиспользовать `rec-reason` по решению design D5. Проверка: `python tools/server.py`, открыть http://localhost:5000 — в карточке под парой видна строка личных встреч, текста причины («близкий рейтинг», «рематч») нет.

## 3. Тесты

- [x] 3.1 Обновить `tools/test_pairing.py`: мок `server.get_pair_game_counts` заменить на мок `server.get_pair_stats` с фейковой статистикой `{games, wins}`; assert `"рематч" in first["reason"]` заменить на проверку `first["pair_games"] == 1` и `first["h2h_label"].startswith("личные встречи:")`; печать `first['reason']` заменить на `first['h2h_label']`. Проверка: `python tools/test_pairing.py` — exit 0.

## 4. Ручная проверка UI

- [x] 4.1 Запустить `python tools/server.py`, открыть главную: для пары с историей видно «личные встречи: N · счёт A:B», для пары без встреч — «личные встречи: не встречались»; листание «→» и кнопка «Прогнать» работают как раньше. Если в журнале есть ничьи — убедиться, что они входят в N, но не в счёт.
