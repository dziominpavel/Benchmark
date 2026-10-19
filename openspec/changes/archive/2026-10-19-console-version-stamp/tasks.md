# Tasks

Все задачи уже выполнены (фича сделана и проверена до оформления change);
чекбоксы отмечены по факту — при архивации дельта-спека вливается в
`openspec/specs/console-shell/spec.md`.

## 1. Резолверы версии и сборки (tools/server.py)

- [x] 1.1 Общий помощник `_run_git(root, *args)` — один вызов `subprocess.run` с `CREATE_NO_WINDOW` и таймаутом 5 с; `_git_version` переведён на него; проверить: `tools/test_data_cache.py` — `test_version_badge` (правки не меняют поведение резолверов).
- [x] 1.2 `resolve_build_time(root)`: время последнего коммита `git show -s --format=%cI HEAD` в локальной зоне, формат `%d.%m.%Y %H:%M`; фолбэк — mtime `pyproject.toml`; без источников — пустая строка; проверить: `test_version_badge` (фолбэк файла, приоритет git, пустой каталог).
- [x] 1.3 Константы `_APP_VERSION`/`_APP_BUILD_TIME` (резолв при импорте, вне пути запроса) и jinja-глобалы `app_version()`/`app_build_time()`; проверить: `tools/test_perf.py` (бюджеты холодной главной не изменились) и `tools/test_elo.py`.

## 2. Вывод в UI (оболочка и настройки)

- [x] 2.1 Подвал `tools/templates/shell.html`: маркеры `.footer-version` (титл «Версия консоли») и `.footer-build` («сборка ДД.ММ.ГГГГ ЧЧ:ММ»), скрытие блоков без источника; проверить: `test_version_badge` (подвал всех страниц live и read-only) и `tools/test_export.py` (значения запечены в слепок).
- [x] 2.2 `SETTINGS_TEMPLATE` в `tools/server.py`: пункт «О консоли» в навигации и карточка `id="about"` с парами «Версия»/«Сборка» и подсказкой о происхождении значений; проверить: `test_version_badge` (секция «О консоли» в `/settings`).
- [x] 2.3 Стили `tools/static/css/console.css`: `.about-meta`/`.about-row`, числовая типографика маркеров подвала; бейдж шапки и его стили удалены; проверить: визуальный просмотр тёмной и светлой тем на живом сервере.

## 3. Changelog и интеграционные проверки

- [x] 3.1 `CHANGELOG.md` `[Unreleased]`: пользовательский пункт (версия и сборка в подвале и настройках) и инженерные детали (резолверы, фолбэки, тесты, запекание в слепке).
- [x] 3.2 Полный прогон: `tools/test_data_cache.py`, `tools/test_export.py`, `tools/test_elo.py`, `scripts/check-version.py` — все exit 0.

## Workflow follow-up

- Заархивировать change после проверки: `openspec archive console-version-stamp` (дельта вливается в `openspec/specs/console-shell/spec.md`).
- Проверить `openspec validate --all --strict` после архивации.
