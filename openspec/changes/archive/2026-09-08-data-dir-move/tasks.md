## 1. Подготовка и переезд файлов

- [x] 1.1 Убедиться, что сервер остановлен (`logs/server.pid` отсутствует) и зафиксировать хеш `generate_index()` (канонический JSON, `sort_keys=True`) как baseline; проверить: `elo.py --check` зелёный до старта
- [x] 1.2 Выполнить `git mv` по одному объекту: `tasks/`, `answers/`, `matchups/`, `models.yaml`, `judges.yaml`, `settings.yaml`, `index.json` → `data/`; создать `data/logs/` на диске; проверить: `git status` показывает только переименования, `elo.py --check` красный (ожидаемо — пути ещё старые), тесты не запускать

## 2. Код и лаунчеры

- [x] 2.1 Ввести `DATA_DIR` в `tools/elo.py` и перевесить на неё `MATCHUPS_DIR`, `ANSWERS_DIR`, `TASKS_DIR`, `INDEX_PATH`, `MODELS_PATH`, `SETTINGS_PATH`; обновить `.gitignore` (`logs/*.pid` → `data/logs/*.pid`); проверить: `elo.py --check` снова зелёный, хеш `generate_index()` совпал с baseline из 1.1
- [x] 2.2 Обновить лаунчеры (остаются в корне): `start.bat` (`logs\` → `data\logs`), `launch.vbs` (`logDir`, пути лога/pid), `stop.bat` (путь pid); проверить: `test_elo.py` и `test_pairing.py` зелёные

## 3. Skills, docs, спеки

- [x] 3.1 Обновить префиксы путей (`tasks/` → `data/tasks/`, `answers/` → `data/answers/`) в 9 skills (judge/run-a/run-b × `.opencode/.cursor/.devin`: в judge — строки ~17,25-27; в run-a/run-b — description, строки ~18,34,74) и в `AGENTS.md`; проверить: grep по skills и `AGENTS.md` не находит старых префиксов в путях данных
- [x] 3.2 Обновить `README.md` и `docs/*` (структурная схема + упоминания путей); проверить: grep по `README.md` и `docs/` не находит старых корневых путей данных

## 4. Финальная проверка

- [x] 4.1 Сервер стартует из корня, главная/`history`/`settings` показывают те же цифры, что до переезда; `elo.py --check` зелёный; `openspec validate "data-dir-move"` валиден; зафиксировать результат отметками
