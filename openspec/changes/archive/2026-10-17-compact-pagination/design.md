# Design

## Context

См. `proposal.md` — Why. Текущее состояние, задающее рамки решения:

- Шаблоны консоли — Jinja, Flask подхватывает их из `tools/templates` (`app = Flask(__name__)` в `tools/server.py:66`); общий макрос-паттерн уже есть: `_tag_filter.html` импортируется строками вида `{% from "_tag_filter.html" import filter_panel with context %}` (`tools/server.py:839, 1063, ...`).
- `/history`: цикл `for p in range(1, history_pages + 1)` в `HISTORY_TEMPLATE` (`tools/server.py:1108-1115`), размер страницы 20 (`tools/server.py:1937`), фильтры собираются в `history_params` (`tools/server.py:1878-1885`), номер страницы нормализуется в диапазон (`tools/server.py:1941-1946`).
- Очередь `/settings`: `queue_pages` и `queue_page` (`tools/server.py:2517-2519`), билдер `_queue_page_url(p)`, сохраняющий остальные query-параметры (`tools/server.py:2542-2548`), шаблон выводит «← Назад / Вперёд →» и подпись «страница X из Y» (`tools/server.py:1734-1740`); строки строятся только для текущей страницы (комментарий на `tools/server.py:2521`).
- CSS: `.pagination`, `.pagination a, .pagination span`, `.pagination span.current`, `.pagination .disabled` (`tools/static/css/console.css:952-983`); класс `.disabled` уже определён и пока нигде не используется.
- Тесты: `test_settings_queue_pagination` (`tools/test_data_cache.py:375-436`) проверяет текст «страница 1 из 2» и ссылки `queue_page`; `test_perf.py:292-295` — наличие ссылки `queue_page=2`; тестов пагинации `/history` нет. Генератор журнала на 10 000 событий с согласованными ELO-снэпшотами есть в `test_perf.py:90-119`.
- Публичная витрина `web/` пагинации не имеет и не затрагивается.

## Goals / Non-Goals

**Goals:**
- Один алгоритм окна страниц и один Jinja-макрос для обеих точек листания (`/history` и очередь `/settings`).
- Сохранить контракт URL (`page`, `queue_page`, все фильтры и настройки отображения) и серверный рендер без JS.
- Зафиксировать поведение тестами: таблица истинности алгоритма + route-тест `/history` + обновление теста очереди.

**Non-Goals:**
- Не менять размеры страниц (20 и 100), маршруты, параметры, структуру данных.
- Не трогать страницы без листания (`/`, `/stats`, `/model/<id>`, `/add`) и публичную витрину `web/`.
- Без JS-пагинации, автоскролла, поля «перейти к странице» и мобильной адаптации сверх существующего `flex-wrap`.

## Decisions

### D1. Алгоритм окна — Python-хелпер `pagination_items` в `tools/render_helpers.py`

```python
def pagination_items(page: int, pages: int) -> list[int | None]:
    """Пункты виджета пагинации; None — троеточие. page в диапазоне 1..pages."""
```

Правила:
1. `pages <= 10` → `list(range(1, pages + 1))` (все номера, без троеточий).
2. Иначе базис — отсортированное множество `{1, pages} ∪ {p | page-2 <= p <= page+2, 1 <= p <= pages}`.
3. Проход по базису: расстояние между соседними номерами 2 (пропущена ровно одна страница) → печатается её номер; больше 2 → вставляется `None` (троеточие).

Таблица значений (становится тестом):

| pages, page | результат |
|---|---|
| 8, 5 | `1 2 3 4 5 6 7 8` |
| 27, 1 | `1 2 3 ... 27` |
| 27, 14 | `1 ... 12 13 14 15 16 ... 27` |
| 27, 27 | `1 ... 25 26 27` |
| 12, 5 | `1 2 3 4 5 6 7 ... 12` |

Обоснование: алгоритм тестируется без HTTP, макрос остаётся «глупым» (только рендер). Альтернативы: логика внутри Jinja-макроса (трудно юнит-тестировать, будет дублироваться) и вычисление в каждом роуте (дублирование между `/history` и очередью) — отклонены.

Валидность `page`/`pages` — ответственность вызывающих: оба роута уже нормализуют номер (`tools/server.py:1946`, `valid_queue_page`).

### D2. Общий макрос `pagination` в новом `tools/templates/_pagination.html`

```jinja
{% macro pagination(page, pages, items, page_url) %}
{% if pages > 1 %}
<nav class="pagination" aria-label="Пагинация">
  {% if page > 1 %}<a class="page-arrow" href="{{ page_url(page - 1) }}" rel="prev" aria-label="Назад">←</a>
  {% else %}<span class="page-arrow disabled" aria-disabled="true">←</span>{% endif %}
  {% for item in items %}
    {% if item is none %}<span class="ellipsis" aria-hidden="true">...</span>
    {% elif item == page %}<span class="current" aria-current="page">{{ item }}</span>
    {% else %}<a href="{{ page_url(item) }}">{{ item }}</a>{% endif %}
  {% endfor %}
  {% if page < pages %}<a class="page-arrow" href="{{ page_url(page + 1) }}" rel="next" aria-label="Вперёд">→</a>
  {% else %}<span class="page-arrow disabled" aria-disabled="true">→</span>{% endif %}
</nav>
{% endif %}
{% endmacro %}
```

- `page_url` — любой callable `page -> str`: Jinja вызывает переданную функцию как обычную. Для истории — замыкание `lambda p: url_for("history_page", page=p, **history_params)` (та же сборка ссылки, что сейчас живёт в шаблоне, переезжает в роут), для очереди — существующий `_queue_page_url`. Альтернатива «endpoint + params» заставила бы макрос знать семантику `url_for` и `request.args` — отклонена.
- Вызывающие сохраняют собственные guard-условия `{% if history_pages > 1 %}` / `{% if queue_pages > 1 %}`; проверка `pages > 1` внутри макроса — защитная.
- Текущая страница — `span.current` (стиль уже есть), не ссылка; троеточие — `span[aria-hidden]`; неактивная стрелка — `span.disabled` (CSS-класс из `console.css:983`).
- Контейнер меняется с `<div>` на `<nav aria-label="Пагинация">` — улучшение семантики, CSS привязан к классу `.pagination`, разметка не ломается.

### D3. Интеграция `/history`

- В роуте `history_page()` (`tools/server.py:1856-1970`) после нормализации номера строятся `history_items = pagination_items(history_page_num, history_pages)` и callable `history_page_url(page)` на базе существующего `history_params`; оба передаются в `HISTORY_TEMPLATE.render(...)`.
- Блок `{% for p in range(1, history_pages + 1) %}` (`tools/server.py:1108-1115`) заменяется вызовом `{{ pagination(history_page, history_pages, history_items, history_page_url) }}` под прежним условием `{% if history_pages > 1 %}`.
- `history_params` не меняется, поэтому фильтры (`model`, `include_inactive`, `agents`, `providers`, `view`, `chips`) сохраняются в ссылках, как и требует спека.

### D4. Интеграция очереди `/settings`

- Из шаблона (`tools/server.py:1734-1740`) убираются текстовые кнопки «← Назад / Вперёд →» и подпись «страница {{ queue_page }} из {{ queue_pages }}»; вместо них — тот же макрос с `items = pagination_items(queue_page, queue_pages)` и `page_url = _queue_page_url`.
- Переменные `queue_prev_url` / `queue_next_url` (`tools/server.py:2548-2550`) и их передача в render (`tools/server.py:2626-2628`) удаляются — макрос сам решает, когда стрелка активна.
- Производительность не меняется: виджету нужен только `queue_pages` (уже вычисляется на `tools/server.py:2517`); построение строк по-прежнему ограничено текущей страницей (`tools/server.py:2521-2525`).

### D5. CSS

План — без изменений: селекторы `.pagination a, .pagination span` уже задают размер 32×32, скругление, рамку и ховер; `.disabled`, `.current` и `ellipsis` попадают под них. Троеточие визуально станет «неактивной ячейкой» — допустимый вид в стилистике консоли. Если на ревью обнаружится визуальный дефект, допустимы точечные правки (приглушение троеточия), но базовый план их не предполагает.

### D6. Тесты (`tools/test_data_cache.py`, по образцу существующих)

- `test_pagination_items_window` — таблица истинности D1, включая границы: `pages=1`, `pages=2`, `pages=10` и `pages=11`, случаи «начало/середина/конец» при `pages=27`, склейку одиночного разрыва при `pages=12, page=5`.
- `test_history_pagination_widget` — реальный журнал на ~540 событий (27 страниц по 20), сгенерированный по образцу `test_perf._journal_text` (две модели, ELO-снэпшоты считаются тем же реплеем): проверяются ссылки `page=2`, `page=3`, `page=27`, отсутствие ссылок `page=4` и `page=26` на первой странице, ровно одно троеточие, активный `span.current`, неактивная стрелка «←», страница `page=14` — окно `12–16` с двумя троеточиями.
- Обновление `test_settings_queue_pagination`: вместо проверки «страница 1 из 2» — проверки виджета (ссылки `queue_page` и активный номер); на последней странице — неактивная стрелка «→»; остальные проверки (номера строк 1–100/101–105, клампинг `queue_page=99` и `queue_page=abc`) сохраняются.
- `test_perf.py` не меняется: проверка «`queue_page=2` есть в HTML» остаётся валидной при виджете.

## Risks / Trade-offs

- [При 1000 моделях очередь достигает ~5000 страниц] → виджет константной ширины (максимум 11 элементов), строка не растёт; четырёхзначные номера вписываются в `min-width: 32px` с паддингом.
- [Удаление подписи «страница X из Y» убирает текстовый ориентир] → позицию показывают активный номер и стрелки; закрепляется тестом.
- [Длинные MODIFIED-требования дают warning `>500 символов` в `openspec validate`] → предупреждение информационное, существующий текст требований намеренно не переписываем.
- [На узком экране виджет переносится (`flex-wrap`)] → максимум 5 номеров + 2 троеточия + 2 стрелки, перенос приемлем и уже заложен в CSS.
- [Изменение текста очереди ломает `test_settings_queue_pagination`] → тест обновляется в этом же change (пункт tasks).
- [Тест истории с ~540 событиями удлиняет прогон] → генератор на две модели, стоимость прогона ничтожна на фоне `test_perf.py` с 10 000 событий.

## Migration Plan

- Миграции данных нет: меняется только серверный рендер. Применение — перезапуск локальной консоли (`stop.bat` / `start.bat`).
- Откат — revert коммита; URL-контракт не менялся, откат безопасен для данных.
- Перед завершением: `openspec validate --all`, прогон `uv run python tools/test_data_cache.py`, `uv run python tools/test_perf.py`, smoke остальных `tools/test_*.py`; пункт в `CHANGELOG.md` `## [Unreleased]` (пользовательский блок + инженерные детали под `###`).
