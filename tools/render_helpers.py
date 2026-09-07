#!/usr/bin/env python3
"""render_helpers.py — общие helpers для рендеринга leaderboard и истории.

Используются tools/server.py.
"""

from __future__ import annotations

DEFAULT_ELO = 1200


def format_delta(delta: int) -> tuple[str, str]:
    """Возвращает (строка дельты, CSS-класс)."""
    if delta > 0:
        return f"+{delta}", "history-delta-up"
    if delta < 0:
        return str(delta), "history-delta-down"
    return "±0", "history-delta-neutral"


def format_recorded_at(recorded_at: str, fallback_date: str = "") -> str:
    """Форматирует recorded_at как 'YYYY-MM-DD HH:MM:SS' или fallback_date."""
    ts = recorded_at or fallback_date
    if not ts:
        return ""
    return ts[:19].replace("T", " ")


def format_winrate(wins: int, games: int) -> str:
    """Возвращает winrate в процентах с одним знаком после запятой.

    При games == 0 возвращает '—'.
    """
    if games == 0:
        return "—"
    return f"{(wins / games) * 100:.1f}%"


def get_model_detail(index_data: dict, model_id: str) -> dict | None:
    """Агрегирует данные страницы модели из кэша index.json.

    Возвращает None для неизвестного id. Иначе словарь:
      id, name, elo, games, wins, losses, draws, winrate,
      points (1200 + after своих матчей по seq),
      h2h (список {id, name, games, w, l, d, winrate}, сортировка:
        встреч по убыванию, затем имя),
      history (список {opp_id, opp_name, date_str, outcome
        (Победа/Поражение/Ничья), before, delta, delta_str,
        delta_class, after} в порядке seq).
    """
    models = index_data.get("models", {})
    info = models.get(model_id)
    if info is None:
        return None

    name_map = {
        mid: minfo.get("name", mid) for mid, minfo in models.items()
    }
    mine = [
        e for e in index_data.get("elo_history", [])
        if e.get("model_a_id") == model_id or e.get("model_b_id") == model_id
    ]
    mine.sort(key=lambda e: e.get("seq", 0))

    points = [DEFAULT_ELO]
    h2h: dict[str, dict] = {}
    history = []
    for e in mine:
        a_id = e.get("model_a_id", "")
        b_id = e.get("model_b_id", "")
        mine_is_a = (a_id == model_id)
        side = e.get("elo_a", {}) if mine_is_a else e.get("elo_b", {})
        before = side.get("before", DEFAULT_ELO)
        after = side.get("after", DEFAULT_ELO)
        delta = side.get("delta", 0)
        points.append(after)

        opp_id = b_id if mine_is_a else a_id
        st = h2h.setdefault(opp_id, {"w": 0, "l": 0, "d": 0})
        winner = e.get("winner", "")
        if winner == "draw":
            st["d"] += 1
            outcome = "Ничья"
        elif (winner == "a" and mine_is_a) or (winner == "b" and not mine_is_a):
            st["w"] += 1
            outcome = "Победа"
        else:
            st["l"] += 1
            outcome = "Поражение"

        delta_str, delta_class = format_delta(delta)
        history.append({
            "opp_id": opp_id,
            "opp_name": name_map.get(opp_id, opp_id),
            "date_str": format_recorded_at(
                e.get("recorded_at", ""), e.get("date", "")
            ),
            "outcome": outcome,
            "before": before,
            "delta": delta,
            "delta_str": delta_str,
            "delta_class": delta_class,
            "after": after,
        })

    h2h_list = [
        {
            "id": oid,
            "name": name_map.get(oid, oid),
            "games": st["w"] + st["l"] + st["d"],
            "w": st["w"],
            "l": st["l"],
            "d": st["d"],
            "winrate": format_winrate(st["w"], st["w"] + st["l"] + st["d"]),
        }
        for oid, st in h2h.items()
    ]
    h2h_list.sort(key=lambda r: (-r["games"], r["name"].lower()))

    games = info.get("games", 0)
    return {
        "id": model_id,
        "name": info.get("name", model_id),
        "status": info.get("status", "active"),
        "elo": info.get("elo", DEFAULT_ELO),
        "games": games,
        "wins": info.get("wins", 0),
        "losses": info.get("losses", 0),
        "draws": info.get("draws", 0),
        "winrate": format_winrate(info.get("wins", 0), games),
        "points": points,
        "h2h": h2h_list,
        "history": history,
    }


def format_elo_history(history: list[dict], name_map: dict) -> list[dict]:
    """Преобразует match-centric elo_history в форму для рендеринга.

    Возвращает список словарей с полями:
      model_a_name, model_b_name,
      elo_a_before, elo_a_after, elo_a_delta, elo_a_delta_str, elo_a_delta_class,
      elo_b_before, elo_b_after, elo_b_delta, elo_b_delta_str, elo_b_delta_class,
      date_str.
    """
    items = []
    for item in history:
        a_id = item.get("model_a_id", "")
        b_id = item.get("model_b_id", "")
        a_name = name_map.get(a_id, a_id)
        b_name = name_map.get(b_id, b_id)

        elo_a = item.get("elo_a", {})
        elo_b = item.get("elo_b", {})

        a_before = elo_a.get("before", DEFAULT_ELO)
        a_after = elo_a.get("after", DEFAULT_ELO)
        a_delta = elo_a.get("delta", 0)

        b_before = elo_b.get("before", DEFAULT_ELO)
        b_after = elo_b.get("after", DEFAULT_ELO)
        b_delta = elo_b.get("delta", 0)

        a_delta_str, a_delta_class = format_delta(a_delta)
        b_delta_str, b_delta_class = format_delta(b_delta)

        date_str = format_recorded_at(
            item.get("recorded_at", ""), item.get("date", "")
        )

        items.append({
            "model_a_name": a_name,
            "model_b_name": b_name,
            "elo_a_before": a_before,
            "elo_a_after": a_after,
            "elo_a_delta": a_delta,
            "elo_a_delta_str": a_delta_str,
            "elo_a_delta_class": a_delta_class,
            "elo_b_before": b_before,
            "elo_b_after": b_after,
            "elo_b_delta": b_delta,
            "elo_b_delta_str": b_delta_str,
            "elo_b_delta_class": b_delta_class,
            "date_str": date_str,
        })
    return items


def build_elo_svg(points: list[int], width: int = 860, height: int = 220) -> str:
    """Строит SVG-график динамики ELO из точек (старт + after каждого матча).

    Пустой список или одна точка без истории ([1200]) → заглушка
    «Нет матчей». Подписывает минимум, максимум и текущее значение.
    """
    if len(points) < 2:
        return '<div class="chart-empty">Нет матчей</div>'

    lo, hi = min(points), max(points)
    if lo == hi:
        lo, hi = lo - 10, hi + 10
    pad = (hi - lo) * 0.1 or 10
    lo, hi = lo - pad, hi + pad

    left, right, top, bottom = 56, 16, 18, 28
    plot_w = width - left - right
    plot_h = height - top - bottom
    n = len(points)

    def x(i: int) -> float:
        return left + (plot_w * i / (n - 1) if n > 1 else plot_w / 2)

    def y(v: float) -> float:
        return top + plot_h * (1 - (v - lo) / (hi - lo))

    poly = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(points))
    dots = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3.5" class="chart-dot"/>'
        for i, v in enumerate(points)
    )
    grid = ""
    for frac, label in ((0.0, hi), (0.5, (hi + lo) / 2), (1.0, lo)):
        gy = top + plot_h * frac
        grid += (
            f'<line x1="{left}" y1="{gy:.1f}" x2="{width - right}" '
            f'y2="{gy:.1f}" class="chart-grid"/>'
            f'<text x="{left - 8}" y="{gy + 4:.1f}" text-anchor="end" '
            f'class="chart-tick">{label:.0f}</text>'
        )

    extremes = [
        (points.index(min(points)), min(points), "min"),
        (points.index(max(points)), max(points), "max"),
    ]
    marks = "".join(
        f'<text x="{x(i):.1f}" y="{y(v) - 10:.1f}" text-anchor="middle" '
        f'class="chart-mark chart-{kind}">{v}</text>'
        for i, v, kind in extremes
    )
    current = (
        f'<text x="{x(n - 1):.1f}" y="{y(points[-1]) + 18:.1f}" '
        f'text-anchor="middle" class="chart-mark chart-current">'
        f'текущий: {points[-1]}</text>'
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">'
        f"{grid}"
        f'<polyline points="{poly}" class="chart-line" fill="none"/>'
        f"{dots}{marks}{current}</svg>"
    )
