## Context

См. `proposal.md` (Why). Факты: после шага 1 (`path-hygiene`) все пути к данным — константы `tools/elo.py` (`REPO_ROOT`, `DATA_DIR` отсутствует — ввести; `MATCHUPS_DIR`, `ANSWERS_DIR`, `TASKS_DIR`, `INDEX_PATH`, `STATE_PATH`, `SETTINGS_PATH`, `MODELS_PATH`). Остальной код импортирует их. Переезд = `git mv` + смена значений констант + механическая замена префиксов в docs/skills. Поведение (форматы, протокол участника) не меняется.

## Goals / Non-Goals

**Goals:**
- Все данные прогонов под `data/`, код в `tools/`, лаунчеры в корне.
- После переезда `test_elo.py`, `test_pairing.py`, `elo.py --check` зелёные; сервер показывает те же цифры (сверка хеша `generate_index()` до/после).

**Non-Goals:**
- Удаление `judges.yaml` (отдельный микро-change).
- Смена форматов файлов, протокола слотов, нумерации — только префиксы путей.
- Миграции `migrate_*` не трогаем (заморожены).

## Decisions

1. **Новая константа `DATA_DIR = REPO_ROOT / "data"`, остальные — от неё.**
   `MATCHUPS_DIR = DATA_DIR / "matchups"`, `ANSWERS_DIR`, `TASKS_DIR` аналогично; `INDEX_PATH = DATA_DIR / "index.json"`, `MODELS_PATH = DATA_DIR / "models.yaml"`, `SETTINGS_PATH = DATA_DIR / "settings.yaml"`; `STATE_PATH = MATCHUPS_DIR / "state.json"` без изменений в коде (уже от `MATCHUPS_DIR`).
   Почему не просто поменять строки: при следующем переезде правится одна константа. Альтернатива (плоские константы без `DATA_DIR`) отвергнута — теряется видимость общего корня.
2. **Перемещение — `git mv` по одному объекту за раз, коммит один.**
   Порядок: `tasks/`, `answers/`, `matchups/`, `models.yaml`, `judges.yaml`, `settings.yaml`, `index.json`. `logs/` — не `git mv` (пуста и не трекается): создать `data/logs/` на диске; `.gitignore` `logs/*.pid` → `data/logs/*.pid`.
   Почему не всё одним `mv`: при ошибке на середине видно, что уже переехало.
3. **Лаунчеры остаются в корне, правятся только внутренности.**
   `start.bat`: `logs\` → `data\logs`; `launch.vbs`: `logDir = root & "\data\logs"`, запуск `python tools/server.py` без изменений (рабочая папка — корень); `stop.bat`: `logs\server.pid` → `data\logs\server.pid`.
   Почему не в `tools/`: единственный пользователь — двойной клик в Explorer; удобство важнее минус трёх файлов в корне (решение зафиксировано в explore-разборе).
4. **Skills/docs — замена префиксов `tasks/` → `data/tasks/`, `answers/` → `data/answers/` (только для путей данных, не для слов в прозе).**
   Почему вручную по grep-чеклисту, а не sed по всему репо: в прозе встречаются те же слова («tasks» как понятие); слепая замена поломает смысл. Каждое из 9 skills правится с чтением контекста строки.
5. **`state.json` остаётся в `data/matchups/`, `judges.yaml` переезжает как есть.**
   Счётчик журнала — рядом с журналом (аргумент из explore-разбора); пустой резерв не трогаем по содержимому.

## Risks / Trade-offs

- [Risk] Пропущенное упоминание пути в одном из 9 skills → skill пишет/читает мимо. Mitigation: grep-чеклист в tasks.md по трём путям во всех skills + `AGENTS.md` + `docs/`; финальный `openspec validate`.
- [Risk] Windows держит `logs/server.pid` или сервер запущен во время переезда → `git mv`/`mkdir` конфликты. Mitigation: перед стартом проверить `stop.bat` состояние (PID-файл отсутствует / процесс мёртв); сервер не запускать до конца работ.
- [Risk] `index.json` пересчитается с тем же содержимым, но другим порядком ключей → шумный дифф. Mitigation: сверка по хешу канонического JSON (`sort_keys=True`), а не побайтово файла; `elo.py --check` как арбитр.
- [Trade-off] 10 дельта-спек — много файлов ради префиксов. Принято: иначе спеки врут, а архивный синк не сможет их починить задним числом.
