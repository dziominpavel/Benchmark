## Why

Пользователю нужна интуитивная метрика для быстрой оценки моделей в leaderboard: процент побед (wins / games) показывает, какая доля матчей закончилась победой. ELO остаётся основным рейтингом, но `Winrate` дополняет его и позволяет быстро сравнить модели без погружения в абсолютные ELO-значения.

## What Changes

- Добавить колонку `Винрейт, %` в таблицу leaderboard:
  - серверная страница `tools/server.py`;
  - статический экспорт `tools/generate_html.py`.
- Вычислять значение **при рендеринге** из существующих `wins` и `games`.
- Формат: `X.Y%` (один знак после запятой); при `games == 0` отображать `—`.
- Колонка размещается **после** `games` / `Всего`.
- Сортировка таблицы остаётся по ELO; `winrate` не влияет на ранжирование.
- Добавить общий helper `format_winrate(wins, games)` в `tools/render_helpers.py`, чтобы избежать дублирования между сервером и статическим HTML.
- Обновить `openspec/specs/leaderboard-ui/spec.md` — новое требование о колонке.

## Capabilities

### New Capabilities

<!-- Нет новых capability; изменение существующего UI. -->

### Modified Capabilities

- `leaderboard-ui`: добавить требование о том, что таблица leaderboard SHALL отображать колонку `Винрейт, %`, вычисляемую как `wins / games * 100`, с форматированием `X.Y%` и `—` при `games == 0`.

## Impact

- `tools/server.py` — шаблон таблицы leaderboard.
- `tools/generate_html.py` — строка `ROW_TEMPLATE` и генерация данных.
- `tools/render_helpers.py` — новый helper `format_winrate`.
- `openspec/specs/leaderboard-ui/spec.md` — новое/изменённое требование.
