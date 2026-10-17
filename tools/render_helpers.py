#!/usr/bin/env python3
"""render_helpers.py — общие helpers для рендеринга leaderboard и истории.

Используются tools/server.py.
"""

from __future__ import annotations

import html
import math

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


def pagination_items(page: int, pages: int) -> list[int | None]:
    """Пункты виджета пагинации: номера страниц, None — троеточие.

    Первая, последняя и текущая ±2 страницы; при 10 страницах и меньше —
    все номера подряд. Разрыв ровно в одну страницу закрывается её номером,
    больший — троеточием. Номер страницы уже приведён к диапазону 1..pages.
    """
    if pages <= 10:
        return list(range(1, pages + 1))

    visible = {1, pages}
    for p in range(page - 2, page + 3):
        if 1 <= p <= pages:
            visible.add(p)

    items: list[int | None] = []
    ordered = sorted(visible)
    for index, p in enumerate(ordered):
        if index:
            gap = p - ordered[index - 1]
            if gap == 2:
                items.append(p - 1)
            elif gap > 2:
                items.append(None)
        items.append(p)
    return items


def get_model_detail(index_data: dict, model_id: str) -> dict | None:
    """Агрегирует данные страницы модели из кэша index.json.

    Возвращает None для неизвестного id. Иначе словарь:
      id, name, agent, provider, elo, games, wins, losses, draws, winrate,
      points (1200 + after своих матчей по seq),
      h2h (список {id, name, games, w, l, d, winrate}, сортировка:
        встреч по убыванию, затем имя),
      history (список {opp_id, opp_name, date_str, outcome
        (Победа/Поражение/Ничья), before, delta, delta_str,
        delta_class, after} в ОБРАТНОМ порядке seq — новые матчи сверху),
      points (список after-значений в ХРОНОЛОГИЧЕСКОМ порядке seq, включая
        стартовое DEFAULT_ELO — для графика).
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

    # Инвертируем ТОЛЬКО список таблицы «История матчей»: новые матчи сверху.
    # `mine` и `points` должны остаться в хронологическом порядке seq —
    # из них строится SVG-график (старые слева → новые справа). Разворот
    # `mine` перед циклом молча отразил бы график.
    history.reverse()

    games = info.get("games", 0)
    return {
        "id": model_id,
        "name": info.get("name", model_id),
        "agent": info.get("agent", ""),
        "provider": info.get("provider", ""),
        "status": info.get("status", "active"),
        "elo": info.get("elo", DEFAULT_ELO),
        "games": games,
        "wins": info.get("wins", 0),
        "losses": info.get("losses", 0),
        "draws": info.get("draws", 0),
        "winrate": format_winrate(info.get("wins", 0), games),
        "points": points,
        "date_first": (
            (mine[0].get("date") or mine[0].get("recorded_at", ""))[:10]
            if mine else ""
        ),
        "date_last": (
            (mine[-1].get("date") or mine[-1].get("recorded_at", ""))[:10]
            if mine else ""
        ),
        "h2h": h2h_list,
        "history": history,
    }


def format_elo_history(history: list[dict], name_map: dict,
                       caption_map: dict | None = None,
                       highlight: bool = False) -> list[dict]:
    """Преобразует match-centric elo_history в форму для рендеринга.

    caption_map: id → подпись «Компания · Агент» (опционально).
    highlight: режим «Подсвечивать» — отдаёт item["hit"] (признак отобранной
    записи, проставленный роутом в исходных словарях); иначе hit=False.
    Возвращает список словарей с полями:
      model_a_name, model_b_name, model_a_caption, model_b_caption,
      elo_a_before, elo_a_after, elo_a_delta, elo_a_delta_str, elo_a_delta_class,
      elo_b_before, elo_b_after, elo_b_delta, elo_b_delta_str, elo_b_delta_class,
      date_str, hit.
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

        captions = caption_map or {}
        items.append({
            "model_a_name": a_name,
            "model_b_name": b_name,
            "model_a_caption": captions.get(a_id, ""),
            "model_b_caption": captions.get(b_id, ""),
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
            "hit": bool(item.get("hit")) if highlight else False,
        })
    return items


def _fmt_axis_date(ts: str) -> str:
    """'YYYY-MM-DD...' → 'DD.MM.YYYY'; иначе — исходная строка."""
    ts = (ts or "").strip()
    if len(ts) >= 10 and ts[4] == "-" and ts[7] == "-":
        return f"{ts[8:10]}.{ts[5:7]}.{ts[0:4]}"
    return ts


def build_elo_svg(
    points: list[int],
    dates: tuple[str, str] | None = None,
    width: int = 860,
    height: int = 220,
) -> str:
    """Строит SVG-график динамики ELO из точек (старт + after каждого матча).

    Пустой список или одна точка без истории ([1200]) → заглушка «Нет матчей».
    Ось X подписана датами первой и последней точки (dates); пунктирная линия
    на уровне 1200 — старт. min/max — цветные метки на линии, текущее значение
    и период — в HTML-легенде под графиком (без вложенных SVG-подписей).
    """
    if len(points) < 2:
        return '<div class="chart-empty">Нет матчей</div>'

    lo, hi = min(points), max(points)
    lo, hi = min(lo, DEFAULT_ELO), max(hi, DEFAULT_ELO)
    if lo == hi:
        lo, hi = lo - 10, hi + 10
    pad = (hi - lo) * 0.1 or 10
    lo, hi = lo - pad, hi + pad

    left, right, top, bottom = 56, 16, 18, 34
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

    # старт 1200 — пунктиром (диапазон оси всегда включает 1200)
    baseline_y = y(DEFAULT_ELO)
    baseline = (
        f'<line x1="{left}" y1="{baseline_y:.1f}" x2="{width - right}" '
        f'y2="{baseline_y:.1f}" class="chart-baseline">'
        f"<title>старт: {DEFAULT_ELO}</title></line>"
    )

    # подписи дат на оси X (первая и последняя)
    axis = ""
    if dates:
        d_first = _fmt_axis_date(dates[0])
        d_last = _fmt_axis_date(dates[1])
        if d_first:
            axis += (
                f'<text x="{left}" y="{height - 8}" text-anchor="start" '
                f'class="chart-tick">{html.escape(d_first)}</text>'
            )
        if d_last:
            axis += (
                f'<text x="{width - right}" y="{height - 8}" text-anchor="end" '
                f'class="chart-tick">{html.escape(d_last)}</text>'
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

    svg = (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="Динамика ELO: {n} точек">'
        f"{grid}{baseline}"
        f'<polyline points="{poly}" class="chart-line" fill="none"/>'
        f"{dots}{marks}{axis}</svg>"
    )

    legend_parts = []
    if dates:
        d_first = _fmt_axis_date(dates[0])
        d_last = _fmt_axis_date(dates[1])
        if d_first and d_last:
            legend_parts.append(f"период <b>{d_first} — {d_last}</b>")
    legend_parts.append(f"старт <b>{DEFAULT_ELO}</b>")
    legend_parts.append(f"мин <b>{min(points)}</b>")
    legend_parts.append(f"макс <b>{max(points)}</b>")
    legend_parts.append(f"текущий <b>{points[-1]}</b>")
    legend = (
        '<div class="chart-legend">'
        + "".join(f"<span>{p}</span>" for p in legend_parts)
        + "</div>"
    )
    return svg + legend


def build_elo_scale(elos: list[int]) -> list[tuple[float, int]]:
    """Анкеры цветовой шкалы распределения: пары (значение Elo, опора палитры).

    Половины растягиваются по пулу вокруг пивота DEFAULT_ELO: минимум — s0
    (тёмно-красный), 1200 — s2 (жёлтый), максимум — s4 (тёмно-зелёный).
    Пул целиком выше/равно 1200 использует только холодную половину,
    целиком ниже — только тёплую. Вырожденный пул (min == max) расширяется
    на ±10, как ось графика.
    """
    lo, hi = min(elos), max(elos)
    if lo == hi:
        lo, hi = lo - 10, hi + 10
    anchors: list[tuple[float, int]] = []
    if lo < DEFAULT_ELO:
        anchors += [
            (float(lo), 0),
            ((lo + DEFAULT_ELO) / 2.0, 1),
        ]
    anchors.append((float(DEFAULT_ELO), 2))
    if hi > DEFAULT_ELO:
        anchors += [
            ((DEFAULT_ELO + hi) / 2.0, 3),
            (float(hi), 4),
        ]
    return anchors


def scale_segment(elo: float, anchors: list[tuple[float, int]]) -> tuple[int, float]:
    """(номер сегмента, доля 0..1) значения Elo на шкале анкеров.

    На стыке сегментов выбирается правый сегмент с долей 0: цвет на стыке
    непрерывен (конец левого = начало правого). Ниже первого и выше
    последнего анкера доля зажата в 0/1.
    """
    if elo <= anchors[0][0]:
        return 0, 0.0
    for i in range(len(anchors) - 1):
        seg_lo, seg_hi = anchors[i][0], anchors[i + 1][0]
        if elo < seg_hi:
            return i, (elo - seg_lo) / (seg_hi - seg_lo)
    return len(anchors) - 2, 1.0


def build_elo_distribution_svg(entries: list[dict], width: int = 860,
                               highlight: bool = False) -> str:
    """Строит SVG bar-chart распределения ELO пула моделей.

    entries: список {elo: int, name: str = "", games: int = 0,
    caption: str = "", hit: bool = True}; сортировка
    по убыванию Elo — внутри. У каждого бара имя модели и значение.
    Бары окрашены непрерывным градиентом по Elo (см. build_elo_scale):
    минимум пула — тёмно-красный, 1200 — жёлтый, максимум — тёмно-зелёный;
    пара опор и доля смешивания передаются в inline --a/--b/--p.
    Вертикальные линии: старт 1200
    и среднее. Ось начинается около минимума (не от нуля).
    Пустой список → заглушка «Нет данных».
    highlight: режим «Подсвечивать» — барам с hit=True добавляется класс
    filter-hit (акцентный контур), остальным — filter-miss (приглушение);
    если отобранных нет, классы не навешиваются (без приглушения).
    """
    if not entries:
        return '<div class="chart-empty">Нет данных</div>'

    pts = sorted(entries, key=lambda e: e.get("elo", DEFAULT_ELO), reverse=True)
    any_hits = highlight and any(p.get("hit") for p in pts)
    elos = [p.get("elo", DEFAULT_ELO) for p in pts]
    n = len(elos)
    mean = sum(elos) / n
    scale = build_elo_scale(elos)

    lo, hi = min(elos), max(elos)
    if lo == hi:
        lo, hi = lo - 10, hi + 10
    pad = max(15.0, (hi - lo) * 0.08)
    lo, hi = lo - pad, hi + pad

    row_h, bar_h = 30, 18
    # поле слева — под самое длинное имя (без обрезки на 30 символах)
    max_name = max(
        (max(len(str(p.get("name", ""))), len(str(p.get("caption", "")))) for p in pts),
        default=0,
    )
    left = max(220, min(420, int(max_name * 7.2) + 24))
    right, top, bottom = 56, 44, 34
    height = top + n * row_h + bottom
    plot_w = width - left - right
    rows_bottom = top + n * row_h

    def x(v: float) -> float:
        return left + plot_w * (v - lo) / (hi - lo)

    bars = ""
    for i, p in enumerate(pts):
        v = p.get("elo", DEFAULT_ELO)
        seg, frac = scale_segment(v, scale)
        cls = "dist-pt"
        if any_hits:
            cls += " filter-hit" if p.get("hit") else " filter-miss"
        style = (
            f"--a:var(--dist-s{scale[seg][1]});"
            f"--b:var(--dist-s{scale[seg + 1][1]});"
            f"--p:{frac * 100:.1f}%"
        )
        cy = top + i * row_h + row_h / 2
        caption = str(p.get("caption", ""))
        tip_name = (
            f'{p.get("name", "")} ({caption})' if caption else f'{p.get("name", "")}'
        )
        tip = html.escape(f'{tip_name} · {v} · игр: {p.get("games", 0)}')
        label = html.escape(str(p.get("name", "")))
        bars += (
            f'<rect x="{x(lo):.1f}" y="{cy - bar_h / 2:.1f}" '
            f'width="{max(1.0, x(v) - x(lo)):.1f}" height="{bar_h}" rx="4" '
            f'class="{cls}" style="{style}">'
            f"<title>{tip}</title></rect>"
            f'<text x="{left - 8}" y="{cy + 4:.1f}" text-anchor="end" '
            f'class="dist-name">{label}<title>{tip}</title></text>'
        )
        if caption:
            bars += (
                f'<text x="{left - 8}" y="{cy + 15:.1f}" text-anchor="end" '
                f'class="dist-caption">{html.escape(caption)}<title>{tip}</title></text>'
            )
        bars += (
            f'<text x="{x(v) + 6:.1f}" y="{cy + 4:.1f}" '
            f'class="dist-value">{v}</text>'
        )

    def vline(v: float, cls: str, tip: str) -> str:
        return (
            f'<line x1="{x(v):.1f}" y1="{top}" x2="{x(v):.1f}" '
            f'y2="{rows_bottom}" class="{cls}">'
            f"<title>{html.escape(tip)}</title></line>"
        )

    lines = (
        vline(DEFAULT_ELO, "dist-line-start", "старт: 1200")
        + vline(mean, "dist-line-mean", f"среднее: {mean:.1f}")
    )

    legend = (
        f'<line x1="{left}" y1="14" x2="{left + 28}" y2="14" class="dist-line-start"/>'
        f'<text x="{left + 34}" y="18" class="chart-tick">старт 1200</text>'
        f'<line x1="{left + 130}" y1="14" x2="{left + 158}" y2="14" class="dist-line-mean"/>'
        f'<text x="{left + 164}" y="18" class="chart-tick">среднее {mean:.0f}</text>'
    )

    grid = ""
    for v in (min(elos), (min(elos) + max(elos)) / 2, max(elos)):
        gx = x(v)
        grid += (
            f'<line x1="{gx:.1f}" y1="{top}" x2="{gx:.1f}" '
            f'y2="{rows_bottom}" class="chart-grid"/>'
            f'<text x="{gx:.1f}" y="{rows_bottom + 22:.1f}" '
            f'text-anchor="middle" class="chart-tick">{v:.0f}</text>'
        )

    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="Распределение Elo: {n} моделей">'
        f"{legend}{grid}{lines}{bars}</svg>"
    )


def confidence_half_width(games: int) -> int | None:
    """Половина интервала доверия рейтинга по числу игр.

    Эвристика объёма данных: round(400 / sqrt(games)).
    При games <= 0 возвращает None (показывать «—»).
    """

    try:
        n = int(games)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return int(round(400 / math.sqrt(n)))


def format_confidence(games: int) -> str:
    """Форматирует доверие как '±N' или '—' при отсутствии игр."""

    w = confidence_half_width(games)
    return f"±{w}" if w is not None else "—"


TREND_WINDOW = 5
TREND_MIN_GAMES = TREND_WINDOW + 1
STALE_GLOBAL_GAP = 30


def _rank_positions(pool_ids: list[str], elo: dict[str, int]) -> dict[str, int]:
    """Ранжирует пул: ELO по убыванию, затем id по возрастанию. Места с 1."""
    ordered = sorted(pool_ids, key=lambda mid: (-elo.get(mid, DEFAULT_ELO), mid))
    return {mid: i + 1 for i, mid in enumerate(ordered)}


class _Fenwick:
    """Дерево Фенвика для порядковых статистик пула (занятые пары ELO×id)."""

    def __init__(self, size: int) -> None:
        self._n = size
        self._tree = [0] * (size + 1)

    def add(self, pos: int, delta: int) -> None:
        """Прибавляет delta на позиции pos (0-based)."""
        i = pos + 1
        n = self._n
        tree = self._tree
        while i <= n:
            tree[i] += delta
            i += i & (-i)

    def prefix(self, pos: int) -> int:
        """Сумма на позициях [0, pos)."""
        total = 0
        i = pos
        tree = self._tree
        while i > 0:
            total += tree[i]
            i -= i & (-i)
        return total


def compute_rank_trends(
    elo_history: list[dict],
    pool_ids: list[str],
    current_elo: dict[str, int],
    window: int = TREND_WINDOW,
    stale_gap: int = STALE_GLOBAL_GAP,
) -> dict[str, dict]:
    """Считает динамику позиции d5 для видимого пула (один проход по истории).

    Для модели с k играми (k >= window + 1) база — ELO-срез сразу после
    ее (k - window)-й личной игры; rank_then — ранг в том же пуле по срезу
    (без игр на тот момент = 1200), rank_now — текущий ранг в пуле.
    Дельта = rank_then - rank_now. При k < window + 1 базы нет.
    Модель без личных игр в последних stale_gap глобальных вердиктах
    считается застоявшейся: вместо стрелки нейтраль с пояснением.

    Ранги на моменты срезов считаются одним проходом: занятость пар
    «(ELO-после, id)» поддерживается деревом Фенвика, запрос ранга —
    O(log N) без перескана истории на каждую модель. Порядок рангов —
    как в _rank_positions (ELO по убыванию, затем id по возрастанию).
    """
    pool = list(pool_ids)
    pool_set = set(pool)
    history = sorted(elo_history or [], key=lambda e: e.get("seq", 0))

    rank_now_map = _rank_positions(pool, current_elo)

    personal: dict[str, list[int]] = {mid: [] for mid in pool}
    pairs: set[tuple[int, str]] = {(-DEFAULT_ELO, mid) for mid in pool}
    for e in history:
        seq = e.get("seq", 0)
        a_id = e.get("model_a_id", "")
        if a_id in pool_set:
            personal[a_id].append(seq)
            val = e.get("elo_a", {}).get("after")
            if val is not None:
                pairs.add((-int(val), a_id))
        b_id = e.get("model_b_id", "")
        if b_id in pool_set:
            personal[b_id].append(seq)
            val = e.get("elo_b", {}).get("after")
            if val is not None:
                pairs.add((-int(val), b_id))

    baseline: dict[str, int] = {}
    stale: set[str] = set()
    max_seq = max((e.get("seq", 0) for e in history), default=0)
    for mid in pool:
        seqs = personal[mid]
        if len(seqs) >= window + 1:
            if history and max_seq - seqs[-1] >= stale_gap:
                stale.add(mid)
            else:
                baseline[mid] = seqs[len(seqs) - window - 1]

    # Ранги на срезы: один проход по истории. Каждая модель в каждый
    # момент занимает ровно одну пару «(ELO-после, id)»; занятость пар
    # и число строго более высоких пар поддерживает дерево Фенвика.
    queries: dict[int, list[str]] = {}
    for mid, cut in baseline.items():
        queries.setdefault(cut, []).append(mid)
    pending = sorted(queries)

    # Ключи пар — (-ELO, id): порядок сортировки совпадает с
    # (ELO по убыванию, id по возрастанию) без key-функции.
    ordered_pairs = sorted(pairs)
    pos = {pair: i for i, pair in enumerate(ordered_pairs)}
    fenwick = _Fenwick(len(ordered_pairs))
    current: dict[str, int] = {mid: DEFAULT_ELO for mid in pool}
    for mid in pool:
        fenwick.add(pos[(-DEFAULT_ELO, mid)], 1)

    rank_then_map: dict[str, int] = {}
    snap_value: dict[str, int] = {}

    def _answer(cut: int) -> None:
        for mid_q in queries[cut]:
            snap_value[mid_q] = current[mid_q]
            rank_then_map[mid_q] = (
                fenwick.prefix(pos[(-current[mid_q], mid_q)]) + 1
            )

    def _apply_event(e: dict) -> None:
        for side, elo_key in (("model_a_id", "elo_a"), ("model_b_id", "elo_b")):
            mid = e.get(side, "")
            if mid not in pool_set:
                continue
            val = e.get(elo_key, {}).get("after")
            if val is None:
                continue
            new = int(val)
            old = current[mid]
            if new == old:
                continue
            fenwick.add(pos[(-old, mid)], -1)
            current[mid] = new
            fenwick.add(pos[(-new, mid)], 1)

    qi = 0
    for e in history:
        seq = e.get("seq", 0)
        # Срез cut полон, когда встретилось событие с seq > cut:
        # все события с seq <= cut уже применены.
        while qi < len(pending) and pending[qi] < seq:
            _answer(pending[qi])
            qi += 1
        _apply_event(e)
    while qi < len(pending):
        _answer(pending[qi])
        qi += 1

    trends: dict[str, dict] = {}
    for mid in pool:
        rank_now = rank_now_map[mid]
        if mid in stale:
            gap = max_seq - personal[mid][-1]
            trends[mid] = {
                "delta": None,
                "label": "–",
                "arrow": "",
                "num": "–",
                "css": "history-delta-neutral",
                "title": (
                    f"без личных игр в последних {stale_gap} прогонах "
                    f"(последняя: {gap} назад)"
                ),
                "rank_then": None,
                "rank_now": rank_now,
                "elo_delta": None,
                "has_baseline": False,
                "stale": True,
            }
            continue
        if mid not in baseline:
            trends[mid] = {
                "delta": None,
                "label": "–",
                "arrow": "",
                "num": "–",
                "css": "history-delta-neutral",
                "title": "мало игр для тренда: нужно 6+ личных игр",
                "rank_then": None,
                "rank_now": rank_now,
                "elo_delta": None,
                "has_baseline": False,
            }
            continue
        rank_then = rank_then_map[mid]
        delta = rank_then - rank_now
        elo_delta = current_elo.get(mid, DEFAULT_ELO) - snap_value.get(mid, DEFAULT_ELO)
        if delta > 0:
            label, css = f"↑{delta}", "history-delta-up"
            arrow, num = "↑", str(delta)
        elif delta < 0:
            label, css = f"↓{-delta}", "history-delta-down"
            arrow, num = "↓", str(-delta)
        else:
            label, css = "=", "history-delta-neutral"
            arrow, num = "", "="
        trends[mid] = {
            "delta": delta,
            "label": label,
            "arrow": arrow,
            "num": num,
            "css": css,
            "title": (
                f"5 личных игр · ΔELO {elo_delta:+d} · "
                f"место {rank_then}→{rank_now}"
            ),
            "rank_then": rank_then,
            "rank_now": rank_now,
            "elo_delta": elo_delta,
            "has_baseline": True,
        }
    return trends
