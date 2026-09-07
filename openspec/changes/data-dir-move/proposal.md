## Why

Корень репозитория разрастается вширь: `tasks/`, `answers/`, `matchups/`, `models.yaml`, `judges.yaml`, `settings.yaml`, `index.json`, `logs/` лежат рядом с кодом и метафайлами. Пожелание владельца: меньше корневых папок, рост вглубь, назначение каждой папки понятно человеку. Переезд консолидирует все данные прогонов в одном месте `data/`, а код остаётся в `tools/`.

## Что меняется

- `git mv` (с сохранением истории) в `data/`: `tasks/`, `answers/`, `matchups/` (включая `matchups/state.json` — счётчик журнала остаётся рядом с журналом), `models.yaml`, `judges.yaml`, `settings.yaml`, `index.json`, `logs/`.
- Константы путей в `tools/elo.py` обновляются на новые; остальной код правок не требует (все импортируют из `elo.py` — гарантировано шагом 1 очереди).
- Обновляются ссылки на пути: `AGENTS.md` + 9 `SKILL.md` (зеркала `.devin/`, `.cursor/`, `.opencode`), `README.md`, `docs/*`, дельта-спеки.
- Лаунчеры `start.bat`, `stop.bat`, `launch.vbs` **остаются в корне** (двойной клик из Explorer); меняются только внутренние пути к `logs/` и `tools/server.py`.
- Протокол участника не ломается: слоты `modelA/modelB`, структура `T-NNN`, формат вердиктов без изменений — меняются только префиксы путей.
- Валидация переезда: `elo.py --check`, `test_elo.py`, `test_pairing.py`, сервер стартует и показывает те же цифры.

## Возможности

### Новые возможности

Нет.

### Изменяемые возможности

- `data-storage`: корневые пути данных меняются на `data/`-префикс (места хранения `settings.yaml`, `index.json`, `tasks/`, `matchups/`, счётчика `state.json`).
- `answer-management`: путь слотов ответов `answers/T-NNN/` → `data/answers/T-NNN/`.
- `task-management`: путь задач `tasks/` → `data/tasks/`.
- `matchup-management`: путь журнала `matchups/` → `data/matchups/`.
- `model-registry`: путь реестра `models.yaml` → `data/models.yaml`.
- `benchmark-workflow`: сквозные пути прогона в описании workflow.

## Влияние

- Код: только константы `tools/elo.py` (после шага 1 — единственное место).
- Docs/skills/specs: массовая, но механическая замена префиксов путей; главный риск — пропущенное упоминание в одном из 9 skills (лечится grep-чеклистом в tasks.md).
- Данные: физического пересчёта нет, только перемещение файлов.

## Порядок реализации (очередь из 4)

| # | Change | Статус |
|---|---|---|
| 1 | `path-hygiene` | MUST быть заархивирован до старта этого change |
| 2 | `data-dir-move` (этот) | Старт только после `archive path-hygiene` |
| 3 | `model-page-and-pairing` | Старт только после `archive data-dir-move` |
| 4 | `index-diet` | Старт только после `archive model-page-and-pairing`, последний |

Явный запрет: НЕ начинать `design`/`tasks` этого change, пока `path-hygiene` не заархивирован. `judges.yaml` в рамках этого change не удаляется (отдельный микро-change позже).
