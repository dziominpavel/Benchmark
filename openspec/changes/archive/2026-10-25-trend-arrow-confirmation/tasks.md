# Tasks

## 1. Правило состояния

- [x] 1.1 В `tools/render_helpers.py` добавить `_momentum_state`: непрерывный ряд последних срезов с `|z| >= 1.5` в одну сторону, вход при подтверждении дельтой после самой старой игры ряда, пауза больше 14 дней обрывает ряд. Проверка: Fable 5.1 (Δ62, z 1.66, последняя −1) без стрелки; Space Bunny и Astra Max — `↑`, North Mini Code — `↓`.
- [x] 1.2 Подключить состояние в `compute_rating_momentum` вместо прямой проверки `last_delta`; `Δ` и `z` считать по окну 10, `trend_value` оставить равным `Δ10`. Проверка: на текущем `data/index.json` те же 2↑/1↓, что и до правила.
- [x] 1.3 В `tools/test_trends.py` добавить эталонный автомат и сценарии: удержание при малой потере, выход при провале, возврат только по двум срезам, нулевая дельта (вход и удержание), пауза 14+ дней. Проверка: `uv run python tools/test_trends.py` печатает `ALL TRENDS TESTS PASSED`.

## 2. Документация

- [x] 2.1 Обновить `CHANGELOG.md`: пользовательский пункт и инженерная деталь про вход по двум срезам и удержание. Проверка: `uv run python scripts/check-version.py` завершается с кодом 0.

## 3. Интеграция

- [x] 3.1 Прогнать `uv run python tools/test_trends.py`, `tools/test_data_cache.py`, `tools/test_export.py`, `tools/test_perf.py`, `tools/test_elo.py`. Проверка: код 0.
- [x] 3.2 Прогнать `openspec validate --all`. Проверка: код 0, дельта `trend-arrow-confirmation` валидна.
- [x] 3.3 Проверить на текущем `index.json`: стрелок вверх 2 (Space Bunny, Astra Max), вниз 1 (North Mini Code), у Fable стрелки нет; после гипотетической победы +5 у Fable стрелка появляется.
