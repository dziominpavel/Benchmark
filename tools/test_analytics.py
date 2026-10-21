#!/usr/bin/env python3
"""test_analytics.py — чистые хелперы аналитики (волна 6).

Проверяет (без Flask):
  * «Рейтинг» — interval_groups: перекрытие соседей, цепочка (транзитивно),
    разрыв, модель без игр; rating_page (страница, место во всём пуле,
    разрез группы); рендер build_rating_svg (место, интервал, градиент в
    одной строке; шкала — по всему пулу);
  * «Динамика ELO» — разбор списка моделей (`id`, имя, подстрока имени;
    неоднозначность и промах видны, порядок ввода сохраняется, кап 10) и
    `period` (30/90/all, дефолт 90), выбор по умолчанию, build_elo_series
    (период от последней даты истории) и build_elo_multiline_svg.

Запуск: python tools/test_analytics.py
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_helpers as rh


def _row(mid: str, elo: int, games: int = 0, **extra) -> dict:
    row = {"id": mid, "name": mid, "elo": elo, "games": games, "caption": ""}
    row.update(extra)
    return row


def _line_x(svg: str, cls: str) -> str | None:
    """X-координата вертикальной линии SVG по её CSS-классу."""
    m = re.search(r'<line x1="([\d.]+)"[^>]*class="' + cls + r'"', svg)
    return m.group(1) if m else None


def _elo_x(svg: str) -> str | None:
    """X-координата колонки ELO (правая граница колонки имён)."""
    m = re.search(
        r'<text x="([\d.]+)"[^>]*text-anchor="end" class="interval-elo"', svg
    )
    return m.group(1) if m else None


def test_interval_groups_overlap():
    """Перекрытие соседей — одна группа; различимые места — без групп."""
    result = rh.interval_groups([
        _row("x", 1200, 100),   # [1160, 1240]
        _row("y", 1250, 100),   # [1210, 1290]
        _row("z", 1400, 100),   # [1360, 1440] — разрыв с y
    ])
    rows = result["rows"]
    assert [r["id"] for r in rows] == ["z", "y", "x"], "порядок: ELO по убыванию"
    assert rows[0]["group"] == 0, "z различима"
    assert rows[1]["group"] == 1 and rows[2]["group"] == 1, "x и y — одна группа"
    assert result["groups"] == [{"start": 1, "end": 2}]
    assert rows[1]["half"] == 40 and rows[1]["lo"] == 1210 and rows[1]["hi"] == 1290
    assert all(r["has_interval"] for r in rows)
    print("«Рейтинг» interval groups: overlap: OK")


def test_interval_groups_chain():
    """Цепочка A–B–C: A с C не пересекается, но группа одна."""
    result = rh.interval_groups([
        _row("a", 1300, 400),   # ±20 → [1280, 1320]
        _row("b", 1250, 44),    # ±60 → [1190, 1310]
        _row("c", 1200, 400),   # ±20 → [1180, 1220]
    ])
    rows = result["rows"]
    assert [r["group"] for r in rows] == [1, 1, 1], "цепочка — одна группа"
    assert result["groups"] == [{"start": 0, "end": 2}]
    assert rows[0]["lo"] > rows[2]["hi"], "A и C не перекрываются напрямую"
    print("«Рейтинг» interval groups: chain: OK")


def test_interval_groups_gap_and_empty():
    """Разрыв между соседями группы не создаёт; пустой пул — без групп."""
    result = rh.interval_groups([
        _row("a", 1300, 100),   # ±40 → [1260, 1340]
        _row("b", 1200, 100),   # ±40 → [1160, 1240]
    ])
    assert result["groups"] == []
    assert [r["group"] for r in result["rows"]] == [0, 0]
    assert rh.interval_groups([])["groups"] == []
    assert rh.interval_groups([])["rows"] == []
    print("«Рейтинг» interval groups: gap and empty: OK")


def test_interval_groups_no_games():
    """Модель без игр — без интервала и без участия в группах."""
    result = rh.interval_groups([
        _row("a", 1200, 0),
        _row("b", 1190, 100),   # ±40 → [1150, 1230]
    ])
    rows = result["rows"]
    assert rows[0]["id"] == "a" and rows[0]["half"] is None
    assert rows[0]["has_interval"] is False and rows[0]["group"] == 0
    assert result["groups"] == [], "без интервала перекрытий нет"
    print("«Рейтинг» interval groups: no games: OK")


def test_rating_svg_row_fields():
    """Карточка «Рейтинг»: место, имя, ELO, интервал и бар в одной строке."""
    rows = rh.interval_groups([
        _row("a", 1300, 400), _row("b", 1250, 44), _row("c", 1000, 0),
    ])["rows"]
    svg = rh.build_rating_svg(rows, rows)
    assert 'class="chart chart-rating"' in svg
    assert 'aria-label="Рейтинг: 3 моделей' in svg
    assert 'href="/model/a"' in svg and 'href="/model/b"' in svg
    assert "dist-pt" in svg, "нет градиентного бара"
    assert "±20" in svg, "интервал не показан"
    assert "—" in svg, "у модели без игр прочерк"
    assert "interval-group-band" in svg
    assert "interval-group-label" not in svg, "надпись группы над строками не убрана"
    assert "Группа неразличимых мест" in svg, "у полосы группы нет подсказки"
    assert "≈" in svg, "группы не помечены при числителе места"
    assert "интервалы соседей перекрываются" in svg, "у ≈ нет подсказки"
    assert "chart-tick" in svg and "dist-line-start" in svg
    assert rh.build_rating_svg([], []) == "", "пустой пул — пустое состояние"
    print("«Рейтинг» svg: row fields: OK")


def test_rating_svg_scale_from_pool():
    """Шкала и колонка имён считаются по всему пулу, а не по странице."""
    pool = rh.interval_groups([
        _row("a", 1500, 100), _row("b", 1400, 100), _row("c", 1300, 100),
    ])["rows"]
    page1 = rh.rating_page(pool, [], 1, page_size=2)["rows"]
    page2 = rh.rating_page(pool, [], 2, page_size=2)["rows"]
    svg1 = rh.build_rating_svg(page1, pool)
    svg2 = rh.build_rating_svg(page2, pool)
    assert _line_x(svg1, "dist-line-start") == _line_x(svg2, "dist-line-start"), (
        "шкала ELO разъехалась между страницами"
    )
    assert _elo_x(svg1) == _elo_x(svg2), "колонка имён разъехалась между страницами"
    print("«Рейтинг» svg: scale from pool: OK")


def test_rating_page_places_and_groups():
    """rating_page: место во всём пуле; разрез группы — маркер без подписи."""
    pool = rh.interval_groups([
        _row("a", 1400, 400),   # ±20 → [1380, 1420]
        _row("b", 1300, 400),   # ±20 → [1280, 1320]
        _row("c", 1250, 44),    # ±60 → [1190, 1310] — перекрывается с b
    ])
    rows = pool["rows"]
    assert [r["id"] for r in rows] == ["a", "b", "c"]
    assert pool["groups"] == [{"start": 1, "end": 2}], "b и c — одна группа"

    page1 = rh.rating_page(rows, pool["groups"], 1, page_size=2)
    assert page1["pages"] == 2 and page1["page"] == 1
    assert [r["rank"] for r in page1["rows"]] == [1, 2], "место — во всём пуле"
    page2 = rh.rating_page(rows, pool["groups"], 2, page_size=2)
    assert [r["rank"] for r in page2["rows"]] == [3], "место второй страницы"

    # Группа разрезана границей страницы: подсказка упоминает продолжение
    assert page1["rows"][1]["group_full"] is False
    assert page1["rows"][1]["group_size"] == 2, "размер группы — по всему пулу"
    svg = rh.build_rating_svg(page1["rows"], rows)
    assert "interval-group-label" not in svg, "надпись группы над строками не убрана"
    assert "продолжение — на соседней странице" in svg, "нет подсказки о продолжении"

    # Группа целиком на странице: подсказка без упоминания продолжения
    full = rh.rating_page(rows, pool["groups"], 1, page_size=3)
    assert full["rows"][1]["group_full"] is True
    assert full["rows"][1]["group_size"] == 2
    svg_full = rh.build_rating_svg(full["rows"], rows)
    assert "Группа неразличимых мест: 2 модели" in svg_full
    assert "продолжение — на соседней странице" not in svg_full

    # Номер страницы за пределами диапазона — последняя существующая
    assert rh.rating_page(rows, pool["groups"], 99, page_size=2)["page"] == 2
    assert rh.rating_page(rows, pool["groups"], 0, page_size=2)["page"] == 1
    assert rh.rating_page([], [], 1)["rows"] == []
    print("«Рейтинг» page: places and groups: OK")


def test_rating_page_size():
    """Размер страницы карточки «Рейтинг» — 50 строк."""
    assert rh.RATING_PAGE_SIZE == 50
    pool = rh.interval_groups(
        [_row(f"m{i:03d}", 1500 - i, 20) for i in range(120)]
    )["rows"]
    page = rh.rating_page(pool, [], 1)
    assert len(page["rows"]) == 50
    assert page["pages"] == 3
    assert page["rows"][0]["rank"] == 1
    assert page["rows"][-1]["rank"] == 50
    print("«Рейтинг» page size: OK")


def _models_fixture() -> dict:
    """Реестр для разбора списка: имена отличаются от id."""
    models = {
        "cursor-fable-5-1-1m-max": _row("cursor-fable-5-1-1m-max", 1441),
        "devin-gpt-6-astra-max": _row("devin-gpt-6-astra-max", 1500),
        "opencode-mimo-v2-5-free": _row("opencode-mimo-v2-5-free", 900),
        "devin-fable-5": _row("devin-fable-5", 1300),
    }
    models["cursor-fable-5-1-1m-max"]["name"] = "Cursor Fable 5.1 1M Max"
    models["devin-gpt-6-astra-max"]["name"] = "Devin GPT-6 Astra Max"
    models["opencode-mimo-v2-5-free"]["name"] = "OpenCode MiMo V2.5 Free"
    models["devin-fable-5"]["name"] = "Devin Fable 5"
    return models


def test_resolve_lines_tokens():
    """A2: разбор списка — id, имя, подстрока; неоднозначность и промах видны."""
    models = _models_fixture()

    # Точное имя
    by_name = rh.resolve_lines("Cursor Fable 5.1 1M Max", models)
    assert by_name["ids"] == ["cursor-fable-5-1-1m-max"]
    assert by_name["tokens"][0]["status"] == "ok"
    assert by_name["unresolved"] == []

    # Точный id
    by_id = rh.resolve_lines("opencode-mimo-v2-5-free", models)
    assert by_id["ids"] == ["opencode-mimo-v2-5-free"]

    # Однозначная подстрока имени
    part = rh.resolve_lines("mimo", models)
    assert part["ids"] == ["opencode-mimo-v2-5-free"]

    # Неоднозначная подстрока — статус и кандидаты, модель не выбрана
    amb = rh.resolve_lines("fable", models)
    assert amb["ids"] == []
    assert amb["tokens"][0]["status"] == "ambiguous"
    assert len(amb["tokens"][0]["candidates"]) == 2
    assert [c["id"] for c in amb["tokens"][0]["candidates"]] == [
        "cursor-fable-5-1-1m-max", "devin-fable-5",
    ]
    assert amb["unresolved"]

    # Не найдено — токен виден, выбор не подменяется
    miss = rh.resolve_lines("gpt-5", models)
    assert miss["ids"] == []
    assert miss["tokens"][0]["status"] == "not-found"
    assert rh.lines_warnings(miss) == ["не найдено: «gpt-5»"]

    # Повтор токена — модель одна, на позиции первого вхождения
    dup = rh.resolve_lines("mimo, MiMo , devin-gpt-6-astra-max", models)
    assert dup["ids"] == ["opencode-mimo-v2-5-free", "devin-gpt-6-astra-max"]

    # Порядок токенов сохраняется
    order = rh.resolve_lines(
        "devin-gpt-6-astra-max, cursor-fable-5-1-1m-max", models)
    assert order["ids"] == ["devin-gpt-6-astra-max", "cursor-fable-5-1-1m-max"]

    # Поле выбора — имена; при неразобранном токене — исходный текст
    assert order["field"] == "Devin GPT-6 Astra Max, Cursor Fable 5.1 1M Max"
    assert miss["field"] == "gpt-5"

    # Чипы: модельные и проблемный
    kinds = [c["kind"] for c in amb["chips"]]
    assert kinds == ["problem"]
    assert [c["kind"] for c in order["chips"]] == ["model", "model"]
    assert order["chips"][0]["raw"] == "Devin GPT-6 Astra Max"

    # Предел: первые 10 в порядке ввода, не вошедшие — отдельным списком
    many = rh.resolve_lines(",".join(f"m{i:02d}" for i in range(12)), {
        **models, **{f"m{i:02d}": _row(f"m{i:02d}", 1200 + i)
                     for i in range(12)},
    })
    assert many["ids"] == [f"m{i:02d}" for i in range(10)]
    assert [d["id"] for d in many["dropped"]] == ["m10", "m11"]
    assert any("не вошло" in w for w in rh.lines_warnings(many))

    # Состояние по умолчанию — тот же формат разбора
    default = rh.resolve_lines_default(models)
    assert default["ids"] == ["devin-gpt-6-astra-max", "cursor-fable-5-1-1m-max",
                               "devin-fable-5", "opencode-mimo-v2-5-free"]
    assert default["field"].startswith("Devin GPT-6 Astra Max, ")
    assert default["unresolved"] == []
    print("A2 resolve lines tokens: OK")


def test_lines_param_parse():
    """A2: `lines` — id и имена, дубликаты и лишние отброшены."""
    models = {f"m{i:02d}": _row(f"m{i:02d}", 1200 + i) for i in range(12)}
    models["arch"] = _row("arch", 1500)

    assert rh.parse_lines_param("", models) == []
    assert rh.parse_lines_param(None, models) == []
    assert rh.parse_lines_param(" m00 , ,m01,m00,unknown ", models) == [
        "m00", "m01",
    ]

    # 13 перечисленных → первые 10 в порядке ввода, не по ELO
    raw = ",".join(["arch"] + [f"m{i:02d}" for i in range(12)])
    picked = rh.parse_lines_param(raw, models)
    assert len(picked) == rh.ELO_LINES_LIMIT
    assert picked == ["arch"] + [f"m{i:02d}" for i in range(9)]
    assert picked[0] == "arch", "архивная модель реестра — допустимый выбор"
    print("A2 lines param parse: OK")


def test_period_param_parse():
    """A2: `period` — 30/90/all, прочее — 90 по умолчанию."""
    assert rh.parse_period_param(None) == 90
    assert rh.parse_period_param("") == 90
    assert rh.parse_period_param("90") == 90
    assert rh.parse_period_param("30") == 30
    assert rh.parse_period_param("all") is None
    assert rh.parse_period_param("ALL") is None
    assert rh.parse_period_param("42") == 90
    assert rh.parse_period_param("abc") == 90
    print("A2 period param parse: OK")


def test_default_line_ids():
    """A2: по умолчанию — топ активных по ELO, архивные не участвуют."""
    models = {
        "a": _row("a", 1500), "b": _row("b", 1300), "c": _row("c", 1400),
        "arch": {**_row("arch", 1700), "status": "archived"},
    }
    models["a"]["status"] = "active"
    models["b"]["status"] = "active"
    models["c"]["status"] = "active"
    assert rh.default_line_ids(models) == ["a", "c", "b"]
    assert rh.default_line_ids(models, 2) == ["a", "c"]
    print("A2 default line ids: OK")


def _series_event(seq: int, day: str, a: str, b: str,
                  elo_a: int, elo_b: int) -> dict:
    return {
        "seq": seq,
        "date": day,
        "model_a_id": a,
        "model_b_id": b,
        "elo_a": {"after": elo_a},
        "elo_b": {"after": elo_b},
    }


def test_build_elo_series():
    """A2: окно периода отсчитывается от последней даты истории."""
    base = date(2025, 10, 1)
    history = [
        _series_event(1, base.isoformat(), "a", "b", 1210, 1190),
        _series_event(2, (base + timedelta(days=93)).isoformat(), "a", "c", 1230, 1180),
        _series_event(3, (base + timedelta(days=153)).isoformat(), "a", "b", 1225, 1195),
        _series_event(4, (base + timedelta(days=163)).isoformat(), "b", "c", 1200, 1205),
    ]
    # Последняя дата — 2026-03-13; period=30 → 2026-02-12+
    result = rh.build_elo_series(history, ["a", "b"], 30)
    assert result["x_count"] == 2, f"в окне 30 дней не 2 матча: {result['x_count']}"
    assert result["series"]["a"] == [(0, 1225)], (
        "a играла только в матче 3 окна"
    )
    assert result["series"]["b"] == [(0, 1195), (1, 1200)]
    assert result["dates"] == ("2026-03-03", "2026-03-13")

    # period=90 → без матча 2025-10-01; шкала — только матчи выборки
    result90 = rh.build_elo_series(history, ["a"], 90)
    assert result90["x_count"] == 2
    assert result90["dates"] == ("2026-01-02", "2026-03-03")

    # all → вся история
    result_all = rh.build_elo_series(history, ["a"], None)
    assert result_all["x_count"] == 3
    assert result_all["dates"] == ("2025-10-01", "2026-03-03")

    # Модель без матчей в окне — пустая линия, но выбор сохраняется
    empty = rh.build_elo_series(history, ["d"], 30)
    assert empty["x_count"] == 0 and empty["series"]["d"] == []
    assert rh.build_elo_series([], ["a"], 90)["x_count"] == 0
    print("A2 elo series: OK")


def test_elo_multiline_svg():
    """A2: линии окрашены, 1200 — пунктиром, даты подписаны, пусто → ""."""
    series = [
        {"id": "a", "name": "A", "points": [(0, 1210), (1, 1230)]},
        {"id": "b", "name": "B", "points": [(1, 1180)]},
    ]
    svg = rh.build_elo_multiline_svg(
        series, 2, ("2026-01-02", "2026-02-01"),
    )
    assert 'class="chart-line-multi"' in svg and 'stroke="#3b82f6"' in svg
    assert 'stroke="#ef4444"' in svg, "вторая линия без своего цвета"
    assert "chart-baseline" in svg, "нет опорной линии 1200"
    assert "02.01.2026" in svg and "01.02.2026" in svg
    assert "Динамика ELO: линий 2, матчей 2" in svg
    assert 'href="/model/a"' in svg and 'href="/model/b"' in svg, "линия без ссылки"
    assert svg.count('class="chart-line-hit"') == 2, "нет хит-слоя на линии"
    no_link = rh.build_elo_multiline_svg(
        [{"name": "A", "points": [(0, 1210), (1, 1230)]}], 2, (),
    )
    assert "/model/" not in no_link, "серия без id не должна вести на профиль"
    assert rh.build_elo_multiline_svg([], 0, ()) == ""
    assert rh.build_elo_multiline_svg(
        [{"id": "a", "name": "A", "points": []}], 3, (),
    ) == "", "нет матчей — пустое состояние"
    print("A2 multiline svg: OK")


def test_plural_ru():
    """Счётчик title: формы слова по числу, включая 11–14 и сотые."""
    cases = {
        0: "записей", 1: "запись", 2: "записи", 4: "записи", 5: "записей",
        11: "записей", 12: "записей", 14: "записей", 21: "запись",
        22: "записи", 102: "записи", 111: "записей", 595: "записей", 602: "записи",
    }
    for n, expected in cases.items():
        assert rh.plural_ru(n, "запись", "записи", "записей") == expected, n
    print("plural ru: OK")


def test_elo_svg_point_links():
    """Профиль: точка с links ведёт к записи вердикта, без — некликабельна."""
    svg = rh.build_elo_svg(
        [1200, 1216, 1208],
        links=[None, {"url": "/history?v=1#v-1", "title": "запись v=1"}, None],
    )
    assert 'href="/history?v=1#v-1"' in svg and "запись v=1" in svg
    assert svg.count('class="chart-dot-hit"') == 1, "ссылка только у матчевой точки"
    plain = rh.build_elo_svg([1200, 1216])
    assert "/history?" not in plain and "chart-dot-hit" not in plain
    print("profile elo svg point links: OK")


def test_group_summary():
    """A5: медиана/среднее/винрейт, «без агента»/«без компании», порядок."""
    models = {
        "m1": {"elo": 1500, "games": 20, "wins": 12,
               "agent": "Cursor", "provider": "Anthropic"},
        "m2": {"elo": 1300, "games": 20, "wins": 10,
               "agent": "Cursor", "provider": "Anthropic"},
        "m3": {"elo": 1400, "games": 5, "wins": 3,
               "agent": "", "provider": "OpenAI"},
        "m4": {"elo": 1600, "games": 0, "wins": 0},
    }
    agents = rh.group_summary(models, "agent")
    assert [r["name"] for r in agents] == ["без агента", "Cursor"]
    cursor = agents[1]
    assert cursor["models"] == 2
    assert cursor["median"] == 1400 and cursor["mean"] == 1400
    assert cursor["games"] == 40 and cursor["wins"] == 22
    assert cursor["winrate"] == "55%"
    none_row = agents[0]
    assert none_row["models"] == 2 and none_row["median"] == 1500
    assert none_row["games"] == 5 and none_row["winrate"] == "60%"

    providers = rh.group_summary(models, "provider")
    assert [r["name"] for r in providers] == [
        "без компании", "Anthropic", "OpenAI",
    ], "медиана вниз, при равенстве — по названию"
    assert providers[0]["games"] == 0 and providers[0]["winrate"] == "—"
    assert rh.group_summary({}, "agent") == []
    print("A5 group summary: OK")


def _delta_event(seq, day, a, b, winner, before_a, after_a, before_b, after_b,
                 task="T-001"):
    """Событие elo_history: дельты сторон после − до."""
    return {
        "seq": seq, "date": day, "matchup": f"{task}/{seq:03d}",
        "model_a_id": a, "model_b_id": b, "winner": winner,
        "elo_a": {"before": before_a, "after": after_a},
        "elo_b": {"before": before_b, "after": after_b},
    }


def test_delta_leaders():
    """A6: окно от последней даты, топ роста/падения, нулевая сумма вне топов."""
    history = [
        _delta_event(1, "2026-01-02", "a", "b", "a", 1200, 1210, 1200, 1190),
        _delta_event(2, "2026-01-05", "a", "b", "a", 1210, 1215, 1190, 1185),
        _delta_event(3, "2026-01-10", "b", "c", "c", 1185, 1175, 1200, 1210),
        _delta_event(4, "2026-01-10", "a", "c", "a", 1215, 1220, 1210, 1205),
        _delta_event(5, "2026-01-10", "a", "d", "draw", 1220, 1220, 1200, 1200),
    ]
    models = {mid: {"name": mid.upper()} for mid in "abcd"}

    week = rh.delta_leaders(history, models, 7)
    assert week["date"] == "2026-01-10" and week["days"] == 7
    assert [(r["id"], r["sum"], r["games"]) for r in week["growth"]] == [
        ("a", 10, 3), ("c", 5, 2),
    ], "окно 7 дней: e2/e4/e5"
    assert [(r["id"], r["sum"]) for r in week["fall"]] == [("b", -15)]
    assert week["growth"][0]["name"] == "A", "имя из реестра"

    month = rh.delta_leaders(history, models, 30)
    assert [(r["id"], r["sum"], r["games"]) for r in month["growth"]] == [
        ("a", 20, 4), ("c", 5, 2),
    ]
    assert [(r["id"], r["sum"]) for r in month["fall"]] == [("b", -25)]
    assert all(r["id"] != "d" for r in month["growth"] + month["fall"]), "нулевая сумма"

    assert [r["id"] for r in rh.delta_leaders(history, models, 30, top=1)["growth"]] == ["a"]
    assert rh.delta_leaders(history, {"a": {"name": "A"}}, 30)["fall"] == [], "вне пула"
    assert rh.delta_leaders([], models, 7)["growth"] == []
    print("A6 delta leaders: OK")


def test_opposition_strength():
    """A7: средний ELO соперников «до», апсеты против топ-10, прочерки."""
    history = [
        _delta_event(1, "2026-01-01", "a", "b", "a", 1200, 1220, 1200, 1180),
        _delta_event(2, "2026-01-02", "b", "c", "b", 1180, 1160, 1220, 1240),
        _delta_event(3, "2026-01-03", "d", "a", "a", 1240, 1260, 1240, 1220),
    ]
    models = {
        "a": {"name": "Alpha", "elo": 1220},
        "b": {"name": "Beta", "elo": 1160},
        "c": {"name": "Gamma", "elo": 1240},
        "d": {"name": "Delta", "elo": 1260},
    }
    rows = rh.opposition_strength(history, ["a", "b", "c", "d"], models)
    assert [r["id"] for r in rows] == ["a", "b", "c", "d"], "порядок рейтинга"
    by_id = {r["id"]: r for r in rows}
    assert by_id["a"]["games"] == 2 and by_id["a"]["opp_avg"] == 1220
    assert by_id["a"]["upsets"] == 1, "победа над b из топ-10"
    assert by_id["b"]["opp_avg"] == 1210 and by_id["b"]["upsets"] == 0
    assert by_id["c"]["opp_avg"] == 1180 and by_id["c"]["upsets"] == 1
    assert by_id["d"]["opp_avg"] == 1240 and by_id["d"]["upsets"] == 1

    # Топ-10 из одной модели: апсет только у победителя над ней
    narrow = rh.opposition_strength(
        history, ["a", "b", "c", "d"], models, top_ids={"a"},
    )
    narrow_map = {r["id"]: r for r in narrow}
    assert narrow_map["a"]["upsets"] == 0
    assert narrow_map["d"]["upsets"] == 1, "d ниже топ-10 победила a из топ-10"

    no_games = rh.opposition_strength([], ["a", "e"], models)
    assert no_games[1]["games"] == 0
    assert no_games[1]["opp_avg"] is None and no_games[1]["upsets"] is None
    assert no_games[1]["name"] == "e", "нет в реестре — подпись id"
    print("A7 opposition strength: OK")


if __name__ == "__main__":
    test_interval_groups_overlap()
    test_interval_groups_chain()
    test_interval_groups_gap_and_empty()
    test_interval_groups_no_games()
    test_rating_svg_row_fields()
    test_rating_svg_scale_from_pool()
    test_rating_page_places_and_groups()
    test_rating_page_size()
    test_resolve_lines_tokens()
    test_lines_param_parse()
    test_period_param_parse()
    test_default_line_ids()
    test_build_elo_series()
    test_elo_multiline_svg()
    test_plural_ru()
    test_elo_svg_point_links()
    test_group_summary()
    test_delta_leaders()
    test_opposition_strength()
    print("\nALL ANALYTICS TESTS PASSED")
