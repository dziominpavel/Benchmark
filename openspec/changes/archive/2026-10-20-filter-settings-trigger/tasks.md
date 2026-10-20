# Tasks

## 1. Шаблон: триггер в шапке и подписи

- [x] 1.1 Перенести `<details class="filter-settings">` в `.filter-head` внутрь обёртки `.filter-head-actions` перед условной ссылкой «Сбросить» (при скрытой ссылке кнопка остаётся справа); актуализировать шапку-комментарий макроса `filter_panel()`; проверить на `GET /` в тестовом клиенте, что `filter-head-actions` содержит `filter-settings`, а `.filter-rows` идут после шапки.
- [x] 1.2 Переименовать подписи сегментов на «Режим отображения» и «Сортировка чипов» (видимый текст и `aria-label`); проверить, что на страницах с блоком «Фильтр» есть новые подписи и нет старых «>Режим<» и «>Чипы<».
- [x] 1.3 Дополнить `tools/test_data_cache.py`: триггер в шапке внутри `.filter-head-actions`, новые подписи сегментов, бейдж «Настройки фильтра — подсветка · чипы по ELO» при `?view=highlight&chips=elo`; запустить `uv run python tools/test_data_cache.py` — зелёный.

## 2. CSS: кнопка-триггер и панель-поповер

- [x] 2.1 Оформить `summary` как кнопку (паддинг, рамка `--border-strong`, фон `--surface`, `--r-sm`, ховер и открытое состояние — `--elevated` + акцентная рамка, `list-style: none`, `::-webkit-details-marker`), шеврон через `summary::after` (`\25B8` / `\25BE`); убрать прежний `margin-bottom` у `.filter-settings`; проверить в браузере на локальном сервере, что триггер без клика читается кнопкой, а шеврон меняет направление при раскрытии.
- [x] 2.2 Оформить панель: `.filter-settings[open] > .filter-settings-body` — абсолютное позиционирование под триггером по правому краю, `width: min(460px, calc(100vw - 64px))`, фон `--elevated`, `box-shadow: var(--shadow-2)`, `z-index`; `.filter-settings-body .filter-label { min-width: 128px; }`; медиазапрос узких экранов (панель по ширине карточки, шапка переносится); проверить в браузере: панель поверх содержимого, чипы не сдвигаются, ничего не обрезается на 360/480/768px, тёмная и светлая темы.

## 3. Скрипт закрытия, слепок и changelog

- [x] 3.1 Добавить `tools/static/js/filter-panel.js` (клик вне панели снимает `open`; Escape снимает `open` и возвращает фокус на `summary`; шапка-комментарий в стиле `combobox.js`) и подключить его в `tools/templates/shell.html` безусловно с `defer`; проверить в браузере: клик вне закрывает панель, Escape закрывает и ставит фокус на кнопку, повторный клик по кнопке работает, без скрипта страница остаётся рабочей (нативное сворачивание).
- [x] 3.2 Дополнить `tools/test_export.py`: `static/js/filter-panel.js` есть в файлах сборки и подключён на страницах слепка относительной ссылкой; запустить `uv run python tools/test_export.py` — зелёный.
- [x] 3.3 Добавить пункт в `CHANGELOG.md` (`[Unreleased]`): пользовательский буллет в блок «**Добавлено**» и инженерные детали под `### Добавлено` по `docs/versioning.md`; проверить `python scripts/check-version.py` — exit 0.

## 4. Интеграционная проверка

- [x] 4.1 Ручной прогон блока «Фильтр» на `/`, `/stats`, `/history`, `/add`, `/settings`: триггер в шапке, панель поверх, закрытие повторным кликом / кликом вне / Escape, Tab-порядок, бейдж не-дефолтных настроек, обе темы.
- [x] 4.2 Пересобрать статический слепок штатным экспортом и проверить в браузере: кнопка и поповер работают, закрытие вне/Escape есть, фильтры зеркала (`mirror.js`) и подпись-бейдж не сломаны.
- [x] 4.3 Прогнать `uv run python tools/test_data_cache.py`, `uv run python tools/test_export.py` и `openspec validate --all` — всё зелёное.
  - `tools/test_data_cache.py` — ALL DATA CACHE TESTS PASSED (включая `filter settings trigger: OK`).
  - `tools/test_export.py` — ALL EXPORT TESTS PASSED.
  - `openspec validate filter-settings-trigger --type change` — valid; `openspec validate --all` — 16 passed, 2 failed: падают только посторонние change'ы других агентов (`console-wave6-analytics-scale` — нет дельт, `drop-settings-about-card` — MODIFIED без сценариев). Наш change, спеки и `live-search` проходят.

## Workflow follow-up

- [x] Архивировать change после приёмки и убедиться, что дельта применилась к `openspec/specs/leaderboard-ui/spec.md` (сделано: дельта слита в основную спеку, change перенесён в `openspec/changes/archive/2026-10-20-filter-settings-trigger/`).
