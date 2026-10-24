# Tasks

## 1. Расчёт движения рейтинга

- [x] 1.1 В `tools/render_helpers.py` добавить `compute_rating_momentum(elo_history, pool_ids, current_elo, window=10, min_games=16, z_threshold=1.5, max_age_days=14)`: один проход по истории, `Δ10`, `sd` по K и ожидаемым счётам, `z`, `fresh_date = max(date)`; импортировать `expected_score` и `k_factor` из `elo`. Проверка: на `data/index.json` при реализации получено 3 стрелки вверх (Space Bunny `+75`, z 1.83; Astra Max `+56`, z 1.74; Fable `+62`, z 1.66), вниз — ноль; Sonnet при `+47` даёт z 1.48 и стрелки не получает.
- [x] 1.2 Удалить из `tools/render_helpers.py` `compute_rank_trends`, `_rank_positions`, `_Fenwick`, `TREND_WINDOW`, `TREND_MIN_GAMES`, `STALE_GLOBAL_GAP`. Проверка: `Select-String -Path tools/*.py -Pattern "compute_rank_trends|STALE_GLOBAL_GAP|_Fenwick"` не находит совпадений.
- [x] 1.3 Переписать `tools/test_trends.py` под новую функцию: эталонная наивная реализация, сверка словарей, краевые случаи (пустая история, пул из одной модели, участники вне пула, ничьи, ровно 15 и 16 игр, порог `z` на границе 1.5, свежесть 14 и 15 дней, независимость от новичков). Проверка: `uv run python tools/test_trends.py` печатает `ALL TRENDS TESTS PASSED`.

## 2. Таблица рейтинга

- [x] 2.1 В `tools/server.py` перевести `rating_selection` на `compute_rating_momentum`, заменить кэш-ключ `trends:*` на `momentum:*` и положить в строку `trend_arrow`, `trend_class`, `trend_title`, `trend_value`; удалить `trend_num` и `trend_label`. Проверка: `uv run python tools/test_data_cache.py` проходит, в HTML главной у Space Bunny есть `<span class="trend-arrow">↑</span>` и нет `<span class="trend-num">`.
- [x] 2.2 В шаблоне таблицы (`tools/server.py`, строка рейтинга) убрать числовую часть стрелки, оставить только `<span class="trend-arrow">` с `title`; тултип собирать как `За 10 игр рейтинг +75: 7 побед, 2 ничьи, 1 поражение. Последняя игра 24.10.` Проверка: тест главной проверяет текст тултипа и отсутствие `trend-num`.
- [x] 2.3 Перевести сортировку по тренду на `trend_value` (Δ10): модели без значения (`games < 16` или нет свежих игр) — последними в обоих направлениях. Проверка: `/?sort=trend&dir=desc` ставит первым максимальный Δ10, `/?sort=trend&dir=asc` — минимальный; строки без значения идут последними.
- [x] 2.4 Обновить легенду под таблицей на `... · прогрев <10 игр · тренд ↑/↓ за 10 игр`. Проверка: тест главной ищет новую строку и не находит `за 5 личных`.
- [x] 2.5 Обновить сценарии главной в `tools/test_data_cache.py`: стрелка при `z >= 1.5`, отсутствие стрелки при движении ниже порога, отсутствие стрелки при 15 играх, отсутствие стрелки при последней игре 30 дней назад, неизменность чужих стрелок после добавления новичка. Проверка: `uv run python tools/test_data_cache.py` проходит целиком.

## 3. Профиль модели

- [x] 3.1 В `tools/server.py` (роут `/model/<id>`) перевести блок тренда на `compute_rating_momentum` с кэш-ключом `momentum:profile`; выводить стрелку без цифры, а при её отсутствии — пояснение `мало игр для тренда: нужно 16+ личных игр` или `нет личных игр в последних 14 днях`. Проверка: тест профиля видит `↑` без `trend-num` и пояснение для модели с малым числом игр.
- [x] 3.2 Обновить `test_wave4_profile` в `tools/test_data_cache.py`: синтетическая история не короче 16 игр, стрелка появляется только при `z >= 1.5`, архивная модель остаётся без места и индикатора. Проверка: `uv run python tools/test_data_cache.py` проходит целиком.

## 4. Оформление и документация

- [x] 4.1 Удалить из `tools/static/css/console.css` правило `.trend-num`; проверить, что стили `.trend`, `.trend-arrow` и цветовые классы `history-delta-up/down` остаются. Проверка: в отрендеренной главной нет класса `trend-num`, стрелка окрашена.
- [x] 4.2 Добавить запись в `CHANGELOG.md` (пользовательский блок и инженерные детали): индикатор тренда теперь показывает заметное движение рейтинга за 10 игр без цифры. Проверка: `python scripts/check-version.py` завершается с кодом 0.

## 5. Интеграция

- [x] 5.1 Прогнать `uv run python tools/test_trends.py`, `uv run python tools/test_data_cache.py`, `uv run python tools/test_export.py`, `uv run python tools/test_perf.py`. Проверка: все команды завершаются с кодом 0.
- [x] 5.2 Прогнать `openspec validate --all` и убедиться, что дельта `trend-elo-momentum` и основная спека согласованы. Проверка: `14 passed, 0 failed`, код 0.
- [x] 5.3 Проверить на текущем `data/index.json`, что на главной 3 стрелки вверх, а у моделей с 15 и менее играми стрелок нет. Проверка: рендер главной даёт 3 стрелки (Space Bunny, Astra Max, Fable), `trend-num` отсутствует.

## Workflow follow-up

- Заархивировать change после ревью и проверок.
- Проверить, что `openspec/specs/leaderboard-ui/spec.md` после архивации не содержит упоминаний d5 и `↑N`/`↓N`.
