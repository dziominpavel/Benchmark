## 1. Константы в elo.py

- [x] 1.1 Добавить `MODELS_PATH` в блок констант `elo.py` и заменить инлайн `REPO_ROOT / "models.yaml"` в `load_models_yaml` (строка ~554); проверить: `python tools/elo.py --check` проходит как до правок
- [x] 1.2 Заменить локальные `tasks_dir/answers_dir/matchups_dir` в `collect_tasks_info` (строки ~599-601) на модульные `TASKS_DIR/ANSWERS_DIR/MATCHUPS_DIR`; проверить: вывод `generate_index()` побайтово совпадает с выводом до правок

## 2. Импорты вместо дублей

- [x] 2.1 Удалить локальные `ANSWERS_DIR/MATCHUPS_DIR/TASKS_DIR` из `server.py` (строки ~54-56), расширить `from elo import`, заменить инлайн `REPO_ROOT / "index.json"` (~68) и `REPO_ROOT / "models.yaml"` (~272, ~1599) на `INDEX_PATH`/`MODELS_PATH`; проверить: сервер стартует, главная и `/history` открываются с теми же цифрами
- [x] 2.2 Заменить собственные `REPO_ROOT`/`MODELS_PATH`/`INDEX_PATH` в `register_model.py`, `archive_model.py`, `test_pairing.py` импортом из `elo.py`; проверить: `python tools/test_elo.py` и `python tools/test_pairing.py` зелёные

## 3. Финальная проверка

- [x] 3.1 Grep-чек: по `tools/*.py` (кроме `migrate_*`) нет литералов `"tasks"`, `"answers"`, `"matchups"`, `"index.json"`, `"models.yaml"`, `"settings.yaml"` вне блока констант `elo.py`; `elo.py --check` зелёный; зафиксировать результат в этом файле отметками
