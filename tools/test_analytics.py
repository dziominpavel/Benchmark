#!/usr/bin/env python3
"""test_analytics.py — чистые хелперы аналитики волны 4 (A1–A8).

Проверяет (без Flask):
  * A1 — interval_groups: перекрытие соседей, цепочка (транзитивно),
    разрыв, модель без игр; рендер build_rating_intervals_svg;
  * A2 — разбор `lines` (CSV, кап 10, неизвестные id) и `period`
    (30/90/all, дефолт 90), выбор по умолчанию, build_elo_series
    (период от последней даты истории) и build_elo_multiline_svg.

Запуск: python tools/test_analytics.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_helpers as rh


def _row(mid: str, elo: int, games: int = 0, **extra) -> dict:
    row = {"id": mid, "name": mid, "elo": elo, "games": games, "caption": ""}
    row.update(extra)
    return row


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
    print("A1 interval groups: overlap: OK")


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
    print("A1 interval groups: chain: OK")


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
    print("A1 interval groups: gap and empty: OK")


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
    print("A1 interval groups: no games: OK")


def test_rating_intervals_svg():
    """Рендер A1: ссылки, группы «место не определено», прочерк без игр."""
    rows = rh.interval_groups([
        _row("a", 1300, 400), _row("b", 1250, 44), _row("c", 1000, 0),
    ])["rows"]
    svg = rh.build_rating_intervals_svg(rows)
    assert 'class="chart chart-intervals"' in svg
    assert 'href="/model/a"' in svg and 'href="/model/b"' in svg
    assert "место не определено" in svg and "interval-group-band" in svg
    assert "интервалов" not in svg  # подпись блока — в шаблоне, не в SVG
    assert "interval-gap" in svg, "у модели без игр нет прочерка"
    assert "≈" in svg, "группы не помечены при числителе места"
    assert rh.build_rating_intervals_svg([]) == ""
    print("A1 rating intervals svg: OK")


def test_lines_param_parse():
    """A2: `lines` — только id реестра, дубликаты и лишние отброшены."""
    models = {f"m{i:02d}": _row(f"m{i:02d}", 1200 + i) for i in range(12)}
    models["arch"] = _row("arch", 1500)

    assert rh.parse_lines_param("", models) == []
    assert rh.parse_lines_param(None, models) == []
    assert rh.parse_lines_param(" m00 , ,m01,m00,unknown ", models) == ["m00", "m01"]

    # 13 перечисленных → 10 наибольших по ELO из перечисленных
    raw = ",".join(["arch"] + [f"m{i:02d}" for i in range(12)])
    picked = rh.parse_lines_param(raw, models)
    assert len(picked) == rh.ELO_LINES_LIMIT
    assert picked[0] == "arch", "архивная модель реестра — допустимый выбор"
    assert "m00" not in picked and "m02" not in picked
    assert set(picked[1:]) == {f"m{i:02d}" for i in range(3, 12)}
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


def test_activity_by_day():
    """A3: дни от первого до последнего, нулевые дни не пропускаются."""
    days = rh.activity_by_day([
        {"date": "2026-01-02"},
        {"date": "2026-01-02"},
        {"date": "2026-01-05"},
        {"recorded_at": "2026-01-05T10:00:00+03:00"},
    ])
    assert [d["day"] for d in days] == [
        "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05",
    ]
    assert [d["count"] for d in days] == [2, 0, 0, 2]
    assert rh.activity_by_day([]) == []
    assert rh.activity_by_day([{"date": "bad"}, {}]) == [], "невалидные дни пропущены"
    print("A3 activity by day: OK")


def test_activity_bars_svg():
    """A3: столбики с подсказкой, нулевой день помечен, пустая история → \"\"."""
    days = rh.activity_by_day(
        [{"date": "2026-01-01"}] * 3 + [{"date": "2026-01-03"}]
    )
    svg = rh.build_activity_bars_svg(days)
    assert 'class="activity-bar"' in svg
    assert "01.01.2026: 3" in svg and "03.01.2026: 1" in svg
    assert "activity-bar-zero" in svg, "день без вердиктов не помечен нулевым"
    assert "дней 3, вердиктов 4, максимум 3" in svg
    assert 'href="/history?from=2026-01-01&amp;to=2026-01-01"' in svg, "столбик без ссылки"
    assert "from=2026-01-02" not in svg, "нулевой день не ведёт в историю"
    unlinked = rh.build_activity_bars_svg(days, links=False)
    assert "/history?from=" not in unlinked, "links=False должен отключать ссылки"
    assert rh.build_activity_bars_svg([]) == ""
    print("A3 activity bars svg: OK")


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


def test_elo_distribution_links():
    """«Распределение Elo»: бар и имя с id — ссылка на профиль, без id — нет."""
    svg = rh.build_elo_distribution_svg([
        {"id": "a", "elo": 1250, "name": "Alpha", "games": 3},
        {"elo": 1150, "name": "Beta", "games": 1},
    ])
    assert 'href="/model/a"' in svg and 'class="dist-link"' in svg
    assert svg.count('href="/model/') == 1, "строка без id не ведёт на профиль"
    print("distribution links: OK")


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


def test_pair_matrix():
    """A4: ячейки симметричны, диагональ пуста, рематч при > 1."""
    stats = {
        frozenset({"a", "b"}): {"games": 3, "wins": {"a": 2, "b": 1}},
        frozenset({"b", "c"}): 1,
    }
    matrix = rh.pair_matrix(["a", "b", "c"], stats)
    assert matrix["ids"] == ["a", "b", "c"]
    assert matrix["rows"][0][0] is None, "диагональ пуста"
    assert matrix["rows"][0][1] == {"count": 3, "rematch": True}
    assert matrix["rows"][1][0] == {"count": 3, "rematch": True}
    assert matrix["rows"][1][2] == {"count": 1, "rematch": False}
    assert matrix["rows"][0][2] is None, "ячейка без встреч данных не несёт"
    assert matrix["meets"] == 4, "встречи считаются по парам один раз"
    empty = rh.pair_matrix([], {})
    assert empty["rows"] == [] and empty["meets"] == 0
    sparse = rh.pair_matrix([f"m{i}" for i in range(120)], {})
    assert len(sparse["rows"]) == 120 and sparse["rows"][0][119] is None
    print("A4 pair matrix: OK")


def test_pair_matrix_svg():
    """A4: ссылки ячеек в live, без ссылок в read-only, пустое состояние."""
    names = {"a": "Alpha", "b": "Beta", "c": "Gamma"}
    matrix = rh.pair_matrix(["a", "b", "c"], {frozenset({"a", "b"}): 3})
    svg = rh.build_pair_matrix_svg(matrix, names)
    assert 'href="/history?pair=a:b"' in svg
    assert "pair-cell-diagonal" in svg
    assert "pair-cell-rematch" in svg and "pair-rematch-dot" in svg
    assert "Alpha vs Beta: 3 · рематч" in svg
    assert "Матрица пар: 3 моделей, встреч 3" in svg
    assert "pair-cells-bg" in svg and "pair-grid-lines" in svg, "фон и сетка одним слоем"

    mirror = rh.build_pair_matrix_svg(matrix, names, links=False)
    assert "href=" not in mirror, "ячейки слепка не должны быть ссылками"
    assert "Alpha" in mirror

    none = rh.pair_matrix(["a", "b"], {})
    assert rh.build_pair_matrix_svg(none, names) == "", "нет встреч — пусто"
    assert rh.build_pair_matrix_svg(rh.pair_matrix([], {}), {}) == ""

    # Пул в сотни моделей: отрисовка разреженная (без n² прямоугольников)
    big_ids = [f"m{i}" for i in range(300)]
    big = rh.pair_matrix(big_ids, {frozenset(big_ids[:2]): 2})
    big_svg = rh.build_pair_matrix_svg(big, {mid: mid for mid in big_ids})
    assert len(big_svg) < 600_000, "матрица разрослась: вернулась плотная сетка"
    print("A4 pair matrix svg: OK")


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


def test_stale_models():
    """A6: остывшие — активные без игр в последних gap вердиктах."""
    history = [
        _delta_event(1, "2026-01-01", "a", "b", "a", 1200, 1220, 1200, 1180),
        _delta_event(2, "2026-01-02", "b", "c", "b", 1180, 1200, 1200, 1180),
        _delta_event(3, "2026-01-03", "b", "c", "c", 1200, 1180, 1180, 1200),
    ]
    models = {
        "a": {"name": "A", "games": 1},
        "b": {"name": "B", "games": 3},
        "c": {"name": "C", "games": 2},
        "d": {"name": "D", "games": 3},
    }
    assert [r["id"] for r in rh.stale_models(history, models, gap=2)] == ["d", "a"]
    assert [r["id"] for r in rh.stale_models(history, models)] == ["d"]
    assert len(rh.stale_models([], models)) == 4, "без истории остыли все"
    assert rh.stale_models([], {}) == []
    print("A6 stale models: OK")


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


def test_winner_shares():
    """A8: числа/проценты, округление, разбивка по таскам, пусто."""
    history = [
        _delta_event(1, "2026-01-01", "a", "b", "a", 1200, 1220, 1200, 1180,
                     task="T-001"),
        _delta_event(2, "2026-01-02", "a", "b", "b", 1220, 1200, 1180, 1200,
                     task="T-002"),
        _delta_event(3, "2026-01-03", "a", "b", "draw", 1200, 1200, 1200, 1200,
                     task="T-002"),
        _delta_event(4, "2026-01-04", "a", "b", "x", 1200, 1200, 1200, 1200),
    ]
    shares = rh.winner_shares(history)
    assert shares["total"] == 3, "неизвестный исход пропущен"
    rows = {r["key"]: r for r in shares["rows"]}
    assert (rows["a"]["n"], rows["a"]["pct"]) == (1, 33)
    assert (rows["b"]["n"], rows["b"]["pct"]) == (1, 33)
    assert (rows["draw"]["n"], rows["draw"]["pct"]) == (1, 33)
    assert "by_task" not in shares

    shares2 = rh.winner_shares(history, ["T-001", "T-002", "T-003"])
    by_task = {g["task"]: g for g in shares2["by_task"]}
    assert set(by_task) == {"T-001", "T-002"}, "пустой таск не показывается"
    assert [r["n"] for r in by_task["T-001"]["rows"]] == [1, 0, 0]
    assert [r["n"] for r in by_task["T-002"]["rows"]] == [0, 1, 1]
    assert rh.winner_shares([])["total"] == 0
    print("A8 winner shares: OK")


if __name__ == "__main__":
    test_interval_groups_overlap()
    test_interval_groups_chain()
    test_interval_groups_gap_and_empty()
    test_interval_groups_no_games()
    test_rating_intervals_svg()
    test_lines_param_parse()
    test_period_param_parse()
    test_default_line_ids()
    test_build_elo_series()
    test_elo_multiline_svg()
    test_activity_by_day()
    test_activity_bars_svg()
    test_plural_ru()
    test_elo_distribution_links()
    test_elo_svg_point_links()
    test_pair_matrix()
    test_pair_matrix_svg()
    test_group_summary()
    test_delta_leaders()
    test_stale_models()
    test_opposition_strength()
    test_winner_shares()
    print("\nALL ANALYTICS TESTS PASSED")
