## Why

Пути к данным (`tasks/`, `answers/`, `matchups/`, `index.json`, `models.yaml`) объявлены константами в `tools/elo.py`, но тот же код дублирует их инлайн: `elo.py:554,599-601`, `server.py:54-56,68,272,1599`. Любой переезд файлов (шаг 2 очереди) размажет эти дубли по новым путям и удвоит места рассинхрона. Чистим сейчас, пока change маленький и безопасный.

## Что меняется

- Все инлайн-пути в `tools/elo.py` заменяются на собственные константы (`REPO_ROOT`, `MATCHUPS_DIR`, `ANSWERS_DIR`, `TASKS_DIR`, `INDEX_PATH`, `STATE_PATH`, `SETTINGS_PATH`).
- `tools/server.py` перестаёт переопределять `*_DIR` локально и хардкодить `index.json`/`models.yaml` — только импорт из `elo.py`.
- Проверка: `grep` по `tools/*.py` не находит строковых литералов `"tasks"`, `"answers"`, `"matchups"`, `"index.json"`, `"models.yaml"` вне `elo.py`.
- Поведение не меняется: `test_elo.py`, `test_pairing.py`, `elo.py --check` зелёные до и после.

## Возможности

### Новые возможности

Нет.

### Изменяемые возможности

Нет — чистый рефакторинг без изменения поведения, поэтому в `.openspec.yaml` выставлен `skip_specs: true`.

## Влияние

- Только `tools/elo.py`, `tools/server.py`. Skills, спеки, docs, данные не затрагиваются.
- Риск минимальный: замена литералов на константы с тем же значением.

## Порядок реализации (очередь из 4)

| # | Change | Статус |
|---|---|---|
| 1 | `path-hygiene` (этот) | Первый, prerequisite нет |
| 2 | `data-dir-move` | Старт только после `archive path-hygiene` |
| 3 | `model-page-and-pairing` | Старт только после `archive data-dir-move` |
| 4 | `index-diet` | Старт только после `archive model-page-and-pairing`, последний |

Правило очереди: следующий change начинается только после архивации предыдущего (`openspec archive`). Порядок зафиксирован дублирующимися блоками в proposal каждого change.
