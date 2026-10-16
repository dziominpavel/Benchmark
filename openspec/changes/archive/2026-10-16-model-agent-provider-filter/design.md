# Design

## Context

- `data/models.yaml` — источник истины, 34 записи. В формате уже есть `provider`,
  но он заполнен лишь у двух записей, причём значением-агентом (`Cursor`,
  `OpenCode`), и нигде не используется. Поля `agent` нет.
- Сериализация реестра — `parse_existing` / `format_model` в
  `tools/register_model.py`; им пользуются `register_model.py`,
  `archive_model.py` и сервер (`update_model`, `add_model`). Round-trip
  пересобирает запись целиком, поэтому любое незнакомое поле молча стирается —
  `format_model` обязан знать новые поля.
- Кэш — `generate_index()` в `tools/elo.py`: `models.<id>` сейчас содержит
  `name`, `provider`, `added`, `status`, `elo`, `games/wins/losses/draws`.
  Устаревание — `is_index_stale()`: digest журнала, множество id и метаданные
  (`name`, `provider`, `status`, `added`). Сервер читает кэш через `ensure_index()`.
- Страницы консоли, которые предстоит затронуть: `/` (таблица, архивная секция,
  фильтр `active|all|inactive`), `/settings` (сворачиваемые списки моделей,
  матрица ответов с `answer_filter` и сохранением скрытых флагов, очередь),
  `/stats` (пул для графика), `/history` (выпадайка, `include_inactive`,
  пагинация), `/add`, `/edit/<id>`, `/model/<id>`.
- Ограничения проекта: код на stdlib (без новых зависимостей), UI — серверные
  шаблоны Flask без JS-фреймворков; витрина `web/` вне скоупа (см. proposal.md).

## Goals / Non-Goals

**Goals:**

- Поле `agent` в реестре + осмысленное `provider` (фирма); значения для всех
  34 записей.
- Мультифильтр по агенту/фирме на всех списках моделей, состояние в URL,
  совместимость с существующими фильтрами и пагинацией.
- Подпись `Фирма · Агент` во всех местах перечисления моделей.
- Ввод значений при регистрации/редактировании (CLI + веб-формы) без риска
  потерять поля записи.
- Кэш и staleness осведомлены о новых полях.

**Non-Goals:**

- Витрина `web/` (отложена до будущей переделки; данные в `index.json` появятся).
- Фильтрация инструментов прогона (форма вердикта, очередь рекомендаций).
- Пересчёт ELO/пар/медалей/d5 под фильтром — фильтр только скрывает строки.
- Обязательность полей и валидация значений по справочнику — свободный ввод.
- Переход с мини-парсера YAML на PyYAML.

## Decisions

### D1. Поле `agent` + переиспользование `provider` как фирмы

Вариант A (выбран): новое поле `agent`; у существующего `provider` закрепляется
смысл «фирма-разработчик модели» и он заполняется. Вариант B (два новых поля
`agent`+`company`, `provider` удалить) отвергнут: лишняя миграция формата,
кэша и документации при нулевой пользе, а `provider` и задумывался под это.

Значения — короткие бренды, как принято в интернете: `OpenAI`, `Anthropic`,
`Google`, `xAI`, `Moonshot AI`, `DeepSeek`, `Z.ai`, `Cognition`, `Cursor`,
`Reflection AI`, `Meta`, `MiniMax`, `Meituan`, `Xiaomi`, `Ant Group`, `NVIDIA`,
`StepFun`, `Unknown`. `Cursor` и агент, и фирма (Composer 2.5 — модель Cursor);
для Composer 2.5 `provider: Cursor`. `Unknown` — обычное значение фильтра и
подписи. Агенты: `Codex`, `Cursor`, `Devin`, `OpenCode`.

### D2. Карта бэкфилла 34 записей

| id | agent | provider |
| --- | --- | --- |
| codex-gpt-5-6-terra-09-2026 | Codex | OpenAI |
| cursor-composer-2-5 | Cursor | Cursor |
| cursor-fable-5-1-1m-max | Cursor | Anthropic |
| cursor-gemini-3-8-flash-high | Cursor | Google |
| cursor-grok-4-6 | Cursor | xAI |
| cursor-grok-4-6-low | Cursor | xAI |
| cursor-kimi-k3-max | Cursor | Moonshot AI |
| cursor-sonnet-5-5-1m-max | Cursor | Anthropic (исправление: было `Cursor`) |
| devin-deepseek-v4-1-flash-max | Devin | DeepSeek |
| devin-deepseek-v4-pro-max | Devin | DeepSeek |
| devin-glm-5-2-high | Devin | Z.ai |
| devin-glm-5-3-flash-max | Devin | Z.ai |
| devin-gpt-5-6-sol-max | Devin | OpenAI |
| devin-gpt-6-astra-max | Devin | OpenAI |
| devin-gpt-6-astra-max-2 | Devin | OpenAI |
| devin-kimi-k3-max | Devin | Moonshot AI |
| devin-swe-1-7-max | Devin | Cognition |
| devin-swe-2-max | Devin | Cognition |
| opencode-beam-free-max | OpenCode | Reflection AI |
| opencode-deepseek-v4-1-flash-free-max | OpenCode | DeepSeek |
| opencode-fledge-alpha-free | OpenCode | Unknown |
| opencode-gemini-4-argon-high | OpenCode | Google |
| opencode-glm-5-3-flash-free | OpenCode | Z.ai |
| opencode-grok-4-7-xhigh | OpenCode | xAI |
| opencode-ling-3-0-flash-fin-free | OpenCode | Ant Group |
| opencode-ling-3-1-flash-free | OpenCode | Ant Group |
| opencode-ll-alpha-free-max | OpenCode | Unknown |
| opencode-longcat-2-5-preview-free | OpenCode | Meituan |
| opencode-mimo-v2-5-free | OpenCode | Xiaomi |
| opencode-mimo-v2-6-flash-free | OpenCode | Xiaomi |
| opencode-muse-spark-1-3-free-xhigh | OpenCode | Meta |
| opencode-nemotron-3-5-super-vl-free-xhigh | OpenCode | NVIDIA (исправление: было `OpenCode`) |
| opencode-space-bunny-free-max | OpenCode | MiniMax |
| opencode-step-5-preview-free-high | OpenCode | StepFun |

Источники по спорным моделям — веб-поиск (анонсы Reflection AI, Meta AI,
OpenCode); `Unknown` у LL Alpha и Fledge Alpha — фирма публично не раскрыта.

### D3. Порядок полей и сериализация

Порядок в записи: `id`, `name`, `agent`, `provider`, `version`, `released?`,
`added`, `status`, `notes?`. `parse_existing` и `load_models_yaml` парсят любые
ключи и уже читают `agent` без изменений — правки нужны только в `format_model`
(новая строка `    agent: ...` после `name`) и в docstring/шапке файла.
Альтернатива — перейти на PyYAML — отклонена: мини-парсер осознанный и
поддерживает комментарии-шапку; смена парсера — отдельная задача.

### D4. CLI

`register_model.py` получает `--agent`; `--provider` и `--agent` опциональны в
любом режиме (снимается проверка `--provider обязателен без --auto`),
`--version` в обычном режиме остаётся обязательным. `--auto` при существующем
id по-прежнему ничего не меняет. `--force` перезаписывает запись целиком,
включая новые поля.

### D5. Веб-формы

`/add`: поля «Название модели» (обязательно), «Агент», «Фирма» — оба опциональны,
`<datalist>` с уже введёнными значениями (distinct, только непустые). `/edit`:
к тем же полям добавляется статус; страница берёт `agent`/`provider` из
`index.json`. `update_model(model_id, name, status, agent, provider)` — правка
через тот же round-trip, остальные поля (`version`, `released`, `added`,
`notes`) не трогаются. Значения тримим; пустое значение допустимо.

### D6. Кэш и staleness

`generate_index`: в `models.<id>` добавляется `agent` (рядом с `provider`).
`is_index_stale`: в список сверяемых метаданных добавляется `agent`
(`provider` уже есть), обновляется комментарий. Так правка реестра руками или
через CLI лениво подхватывается при следующем старте сервера; ручной пересбор —
`python tools/elo.py`.

### D7. Семантика фильтра и представление в URL

Параметры `agents` и `providers` — CSV (URL-энкодинг значений с пробелами
штатный). Токен `none` означает «без агента»/«без фирмы» (значение поля пустое).
Парсер: split, trim, декодирование, отбрасывание пустых и незнакомых значений
(незнакомые не ломают страницу — фильтр просто не сужает), дедупликация;
доступные значения строятся из всех моделей (включая архивные), сортировка
case-insensitive по алфавиту, пункты «без агента»/«без фирмы» показываются
только если такие модели есть. Проверка: `passes = (agents пусто ∨ agent ∈ agents)
∧ (providers пусто ∨ provider ∈ providers)`, где `agent ∈ agents` включает
`none` ⇔ пустой `agent`. Альтернатива с пустой строкой вместо токена `none`
отвергнута: неразличимость «параметр пуст» и «выбран пункт пустого значения».

### D8. UI фильтра

Панель — свёрнутый `<details>` с двумя группами чекбоксов, кнопкой «Показать»
и «Сбросить»; отправка GET-формой (без JS). Все остальные контролы страниц
(«Показывать» на главной и в настройках, пагинация истории, списки и кнопки
настроек) сохраняют `agents`/`providers` через hidden-поля и параметры ссылок.
На главной фильтр применяется к строкам таблицы и к секции архива; места,
медали топ-3 и индикаторы d5 считаются как раньше (роут фильтрует строки
после расчётов). Пустой результат — пустое состояние с подсказкой сброса.
Инструменты прогона (форма вердикта, очередь рекомендаций) не фильтруются.

### D9. Настройки

Фильтр показывается в секции «Модели» и в секции «Наличие ответов»; состояние
общее (один URL). Счётчики «Активных»/«Неактивных (архив)» отражают
отфильтрованный состав списков, «Всего в реестре» — всегда полный размер
реестра. Матрица: видимый набор строк = режим `answer_filter` ∩ теги;
`save_answer_flags_route` получает `agents`/`providers` из args/form, сохраняет
флаги только видимых строк, скрытые — как было (существующий механизм), и
возвращает их же в redirect. Секция «Очередь рекомендаций» не фильтруется.

### D10. История

Состав выпадайки — модели по статусу чекбокса `include_inactive`, дополнительно
суженные тегами; выбранная модель остаётся в списке, даже если не проходит
фильтр. Записи: при «Все» — записи, где хотя бы один участник проходит теги;
при конкретной модели теги на записи не влияют (только на выпадайку).
Пагинация и ссылки сохраняют `model`, `include_inactive`, `agents`, `providers`.

### D11. Аналитика

Пул для графика и сводки = режим `Показывать` ∩ теги; пустой пул — существующее
пустое состояние карточки. Значения фильтра берутся из `index.json`.

### D12. Подписи

Хелпер `model_caption(info)` → строка `Фирма · Агент` из непустых частей
(обе пусты → пустая строка, одна часть → только она), `Unknown` — обычное
значение. Разметка: `<span class="model-caption">` сразу под именем модели:
таблица рейтинга и секция архива, списки и матрица `/settings`, лейблы баров
`/stats`, строки `/history` (под именем каждого участника), список `/add`,
шапка `/model/<id>`. В выпадайках (`<option>`) подпись не показывается.
Альтернатива «отдельные колонки» отклонена: раздувает ширину таблицы.

### D13. Тесты и проверки

Расширить `tools/test_elo.py`: round-trip `format_model`/`parse_existing` с
`agent`/`provider` (в т.ч. что правка не теряет другие поля) и реакция
`is_index_stale` на изменение `agent`/`provider`. Прогнать
`uv run python tools/test_elo.py`, `uv run python tools/elo.py --check`.
Ручная проверка страниц — локальный сервер на синтетическом `index.json`:
фильтры на всех пяти страницах, сохранение флагов матрицы под фильтром,
пагинация истории, подписи, пустые состояния. Внешних обращений нет.

### D14. Документация и changelog

По правилам репозитория фича видимая → пункт в `CHANGELOG.md` (`## [Unreleased]`:
пользовательский блок + инженерная секция, см. `docs/versioning.md`).
`docs/architecture.md` — состав полей реестра; `README.md` и шапка
`data/models.yaml` — формат и примеры команд с `--agent`.

### D15. Совместимость

Миграции данных не требуются: `agent`/`provider` — метаданные, ELO и вердикты
не трогаются. Незнакомые поля в старых записях сохраняются round-trip'ом.
Значения фильтра в URL при переименовании/удалении значения просто перестают
сужать список.

## Risks / Trade-offs

- [Незнакомое поле стирается при `/edit` или архивации] → `format_model` знает
  `agent`; round-trip-тесты в `test_elo.py`; проверка «`added`/`version` не
  изменились» в сценариях дельты.
- [Правка `agent` не долетает до UI] → `is_index_stale` сверяет `agent`;
  тест на staleness.
- [Свободный ввод фирм плодит синонимы/опечатки] → канонический список в
  docs/шапке, datalist-подсказки, `Unknown` как согласованная заглушка.
- [Незнакомые значения в URL ломают вид] → парсер отбрасывает неизвестные
  токены; фильтр не сужает.
- [Подписи добавляют высоту строк] → мелкий серый шрифт, `display:block`,
  `line-height` компактный; проверка на широком и узком экране.
- [Сохранение матрицы под фильтром теряет флаги] → видимый набор считается как
  режим ∩ теги; скрытые строки сохраняются как были (механизм уже есть для
  статусов тасков и `answer_filter`), плюс сценарий в дельте.
- [Устаревшие URL с фильтрами в закладках] → неизвестные значения отбрасываются,
  пустой результат показывает подсказку сброса.

## Migration Plan

1. `format_model` + docstring/шапка + `elo.py` (`generate_index`,
   `is_index_stale`) + тесты — проверить на неизменённом реестре.
2. Бэкфилл `data/models.yaml` по таблице D2 → `python tools/elo.py` →
   `data/index.json` (проверка `--check`).
3. `server.py`: фильтры (D7–D11), подписи (D12), формы (D5).
4. CHANGELOG и docs (D14).

Откат: revert затронутых файлов; `data/matchups/` и ELO не мигрируют, поэтому
откат безопасен в любой момент. Порядок 1→2 обязателен: без правки
`format_model` пересборка реестра стёрла бы новые поля.
