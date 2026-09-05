## 1. Миграция данных

- [x] 1.1 Создать `tools/migrate_recorded_at.py`, который проходит по `matchups/**/*.json` и дополняет `recorded_at` синтетическим значением (`{date}T00:00:{02+seq:02d}+00:00`) для файлов без поля. Проверка: запустить скрипт, убедиться, что все `matchups/general/*.json` теперь содержат `recorded_at`, и `python tools/elo.py --check` проходит без предупреждений.
- [x] 1.2 Закоммитить изменённые `matchups/*.json` и `index.json` после миграции. Проверка: `git diff --stat` показывает только ожидаемые `recorded_at` и перегенерированный `index.json`.

## 2. Ядро ELO

- [x] 2.1 Изменить `recalculate` в `tools/elo.py` на генерацию match-centric `elo_history` (одна запись на матч с `elo_a`/`elo_b`). Проверка: `python tools/test_elo.py` проходит, включая обновлённый `test_elo_history`.
- [x] 2.2 Обновить `verify_snapshots` в `tools/elo.py`: `recorded_at` обязателен, монотонность проверяется строго. Проверка: `python tools/elo.py --check` проходит после миграции и падает, если искусственно удалить `recorded_at` из одного файла.
- [x] 2.3 Обновить `generate_index` в `tools/elo.py`: `index.version = 2`, `index.models[<id>]` содержит `status`, `collect_tasks_info` возвращает `T-001` для `T-001-recurrence-bugs`. Проверка: `python tools/elo.py && python -c "import json; d=json.load(open('index.json')); print(d['version'], d['models'][list(d['models'].keys())[0]]['status'], d['tasks'].keys())"`.
- [x] 2.4 Исправить `next_matchup_path` в `tools/elo.py` и `tools/server.py` на `max + 1` вместо `len + 1`. Проверка: удалить `matchups/general/002.json`, записать новый вердикт, убедиться, что создаётся `004.json`, а не перезаписывается `002.json`.

## 3. Тесты

- [x] 3.1 Обновить `tools/test_elo.py`: `test_elo_history` проверяет 1 запись на матч, добавить тест на `recorded_at`, статус в `index.json`, корректный `task_id`. Проверка: `python tools/test_elo.py` зелёный.
- [x] 3.2 Добавить `tools/test_pairing.py` или расширить тесты `server.py` на фильтрацию архивных моделей. Проверка: при `status: archived` для одной модели рекомендации не содержат пар с ней.

## 4. UI и рендеринг

- [x] 4.1 Создать `tools/render_helpers.py` с функцией `format_history_item(item, name_map)` и `render_matchup_history(history, name_map)`, используемой и `server.py`, и `generate_html.py`. Проверка: оба скрипта импортируют функцию и рендерят одинаковый формат истории.
- [x] 4.2 Обновить `tools/server.py`: история на главной — одна строка на матч, отображается `recorded_at` (дата/время), архивные модели помечаются, рекомендации исключают архивные. Проверка: запустить `python tools/server.py`, открыть `/`, записать тестовый вердикт, убедиться, что история — одна строка с двумя ELO и временем.
- [x] 4.3 Обновить `tools/generate_html.py`: статичный экспорт использует `render_helpers.py`, отображает историю одной строкой на матч, `recorded_at`, архивные модели серым/со звёздочкой. Проверка: `python tools/generate_html.py` создаёт `leaderboard.html`, открыть в браузере — история и таблица соответствуют спекам.

## 5. Архивные модели

- [x] 5.1 Обновить `tools/archive_model.py` и `tools/server.py`, чтобы `index.json` пересчитывался с `status` после архивации/разархивации. Проверка: заархивировать модель, `python tools/elo.py --check` зелёный, рекомендации не содержат архивную модель, в `index.json` `status` = `archived`.
- [x] 5.2 Обновить `tools/server.py` и `tools/generate_html.py`: архивные модели в таблице имеют визуальный маркер. Проверка: в таблице сервера и `leaderboard.html` архивная модель отличается от активной.

## 6. Документация и валидация

- [x] 6.1 Обновить `docs/architecture.md` и `docs/elo-mechanics.md` под match-centric `elo_history` и `recorded_at`. Проверка: `grep` находит только актуальные примеры формата.
- [x] 6.2 Обновить `openspec/specs/` main specs (или оставить delta для последующего `openspec sync`/`archive`). Проверка: `openspec validate --all` проходит без ошибок.
- [x] 6.3 Запустить `python tools/elo.py --check` и `python tools/test_elo.py` после всех изменений. Проверка: обе команды завершаются с exit 0.
