## 1. Данные: поле и бэкфилл

- [x] 1.1 Бэкфилл `added` для существующих моделей `data/models.yaml`: для
      каждой записи без даты — первое появление строки `- id: <slug>` в
      git-истории `models.yaml` + `data/models.yaml` (обе копии пути, минимум
      по дате коммита); запись, которой нет в истории (не закоммичена), —
      текущая дата. Проверка: `git diff data/models.yaml` — только строки
      `added` (плюс шапка), порядок и остальные поля не изменились
- [x] 1.2 Шапка `data/models.yaml`: строка про `added` в описании формата и
      `[--added <YYYY-MM-DD>]` в примере команды регистрации.
      Проверка: `python tools/register_model.py --help` и текст шапки
      согласованы

## 2. Инструменты

- [x] 2.1 `tools/register_model.py`: `--added` (по умолчанию текущая дата),
      запись поля в новую модель, вывод строки в `format_model` только при
      непустом значении. Проверка: регистрация без флага даёт `added` =
      сегодня; с флагом — указанную дату; `--force` перезаписывает дату
- [x] 2.2 `tools/elo.py`: `generate_index` копирует `added` в `models.<id>`
      (пустая строка при отсутствии); `is_index_stale` сравнивает `added`
      с дефолтом пустой строки. Проверка: после бэкфилла `uv run python
      tools/elo.py` кладёт даты в index; ручная правка `added` в реестре
      делает `uv run python tools/elo.py --check` красным до пересчёта
- [x] 2.3 `tools/server.py`: маршрут `/add_model` проставляет
      `added: date.today()`. Проверка: добавление модели через веб-форму
      даёт в реестре сегодняшнюю дату

## 3. Спеки

- [x] 3.1 Delta-спеки change'а (`model-registry`, `data-storage`) содержат
      полные блоки `### Requirement` с сохранёнными исходными сценариями.
      Проверка: `openspec validate model-registration-date --strict` без ошибок
- [x] 3.2 Main-спеки синхронизируются шагом `openspec archive` (CLI складывает
      дельты в `openspec/specs/`). Проверка: `openspec validate --all` —
      exit 0; `--strict` остаётся красным на baseline-предупреждениях
      (длинные требования в 9 спеках) — известное состояние вне scope
      change'а

## 4. Регрессия

- [x] 4.1 `uv run python tools/test_elo.py` — зелёный; `uv run python
      tools/elo.py --check` — зелёный на пересчитанном индексе. Проверка:
      команды завершаются с exit 0
- [x] 4.2 Сверить состав изменений: `tools/register_model.py`,
      `tools/elo.py`, `tools/server.py`, `data/models.yaml`,
      `data/index.json` + артефакты change; журнал `data/matchups/`
      не тронут. Проверка: `git status --short` показывает ожидаемый набор
- [x] 4.3 `uv run python scripts/check-version.py` — версия и changelog
      согласованы (changelog не трогаем: UI-эффекта у поля пока нет).
      Проверка: exit 0
