#!/usr/bin/env python3
"""render_helpers.py — общие helpers для рендеринга leaderboard и истории.

Используются tools/server.py.
"""

from __future__ import annotations

import html
import math
from datetime import date, timedelta

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


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Русская форма слова по числу: 1 запись, 2 записи, 5 записей.

    Числа 11–14 — всегда форма «many» (11 записей), независимо от
    последней цифры; отрицательные приводятся к модулю.
    """
    n = abs(int(n))
    if 11 <= n % 100 <= 14:
        return many
    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


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


def get_model_detail(index_data: dict, model_id: str,
                     registry: dict | None = None) -> dict | None:
    """Агрегирует данные страницы модели из кэша index.json.

    `registry` — сырые записи models.yaml ({id: запись}): из них берутся
    поля метаданных (версия, релиз, заметки), которых нет в index.
    Возвращает None для неизвестного id. Иначе словарь:
      id, name, agent, provider, status, elo, games, wins, losses, draws,
      winrate, last_match (последний по seq матч: {opp_id, opp_name,
      date_str, outcome, delta_str, delta_class, seq, url} или None),
      meta (непустые поля реестра: [{label, value}] — версия, релиз,
      добавлена, статус, заметки),
      points (1200 + after своих матчей по seq),
      h2h (список {id, name, games, w, l, d, winrate}, сортировка:
        встреч по убыванию, затем имя),
      history (список {opp_id, opp_name, date_str, outcome
        (Победа/Поражение/Ничья), before, delta, delta_str,
        delta_class, after, seq, matchup, url} в ОБРАТНОМ порядке seq —
        новые матчи сверху; url — постоянная ссылка вердикта),
      points (список after-значений в ХРОНОЛОГИЧЕСКОМ порядке seq, включая
        стартовое DEFAULT_ELO — для графика),
      point_links (ссылки точек графика, параллельно points: [None] +
        {url, title} на каждый матч — переход к записи вердикта).
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
    point_links: list[dict | None] = [None]
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
        seq = e.get("seq", 0)
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
            "seq": seq,
            "matchup": str(e.get("matchup") or ""),
            "url": f"/history?v={seq}#v-{seq}",
        })
        point_links.append({
            "url": f"/history?v={seq}#v-{seq}",
            "title": f"запись v={seq}",
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

    # Последний матч (хронологически) — до разворота таблицы.
    last_match = None
    if history:
        last = history[-1]
        last_match = {
            "opp_id": last["opp_id"],
            "opp_name": last["opp_name"],
            "date_str": last["date_str"],
            "outcome": last["outcome"],
            "delta_str": last["delta_str"],
            "delta_class": last["delta_class"],
            "seq": last["seq"],
            "url": last["url"],
        }

    # Метаданные реестра: только непустые поля, в порядке показа. Сырые
    # записи models.yaml содержат version/released/notes, которых нет в index.
    registry_entry = (registry or {}).get(model_id) or info
    status_labels = {"active": "активна", "archived": "неактивна"}
    meta: list[dict] = []
    for label, key in (("Версия", "version"), ("Релиз", "released"),
                       ("Добавлена", "added")):
        value = str(registry_entry.get(key) or "").strip()
        if value:
            meta.append({"label": label, "value": value})
    status = str(registry_entry.get("status") or "").strip()
    if status:
        meta.append({"label": "Статус", "value": status_labels.get(status, status)})
    notes = str(registry_entry.get("notes") or "").strip()
    if notes:
        meta.append({"label": "Заметки", "value": notes})

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
        "point_links": point_links,
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
        "last_match": last_match,
        "meta": meta,
    }


def history_task_id(item: dict) -> str:
    """Таск записи истории: префикс matchup (`T-NNN`), fallback — поле task.

    У применённых записей отдельного поля task нет — таск всегда закодирован
    в matchup (`T-NNN/NNN`); у аннулированных записей поле task есть.
    """
    matchup = str(item.get("matchup") or "")
    if "/" in matchup:
        return matchup.split("/", 1)[0]
    return str(item.get("task") or "")


WINNER_LABELS = {"a": "победила A", "b": "победила B", "draw": "ничья"}


def format_elo_history(history: list[dict], name_map: dict,
                       caption_map: dict | None = None,
                       highlight: bool = False) -> list[dict]:
    """Преобразует match-centric elo_history в форму для рендеринга.

    caption_map: id → подпись «Компания · Агент» (опционально).
    highlight: режим «Подсвечивать» — отдаёт item["hit"] (признак отобранной
    записи, проставленный роутом в исходных словарях); иначе hit=False.
    Возвращает список словарей с полями:
      model_a_id, model_b_id, model_a_name, model_b_name,
      model_a_caption, model_b_caption,
      elo_a_before, elo_a_after, elo_a_delta, elo_a_delta_str, elo_a_delta_class,
      elo_b_before, elo_b_after, elo_b_delta, elo_b_delta_str, elo_b_delta_class,
      date_str, hit, matchup, task, seq, winner, winner_label, winner_aria,
      voided, void_str.
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

        voided = bool(item.get("voided"))
        void_str = ""
        if voided:
            void = item.get("void") or {}
            void_date = format_recorded_at(
                void.get("recorded_at", ""), void.get("date", "")
            )
            void_str = "аннулировано"
            if void_date:
                void_str += f" {void_date}"
            reason = str(void.get("reason", "")).strip()
            if reason:
                void_str += f" · {reason}"

        captions = caption_map or {}
        winner = str(item.get("winner") or "")
        winner_label = WINNER_LABELS.get(winner, "")
        if winner == "a":
            winner_aria = f"Победила A — {a_name}"
        elif winner == "b":
            winner_aria = f"Победила B — {b_name}"
        elif winner == "draw":
            winner_aria = f"Ничья: {a_name} vs {b_name}"
        else:
            winner_aria = ""
        items.append({
            "model_a_id": a_id,
            "model_b_id": b_id,
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
            "matchup": item.get("matchup", ""),
            "task": history_task_id(item),
            "seq": item.get("seq"),
            "winner": winner,
            "winner_label": winner_label,
            "winner_aria": winner_aria,
            "voided": voided,
            "void_str": void_str,
        })
    return items


def merge_history_feed(elo_history: list[dict],
                       voided_history: list[dict] | None = None) -> list[dict]:
    """Единая лента истории: применённые + аннулированные записи.

    Копии записей `elo_history` (без пометок) и `voided_history`
    (с `voided=True` и словарём `void` из индекса) в общем обратном
    хронологическом порядке — по убыванию `seq` исходного вердикта:
    аннулированная запись стоит на месте своего исходного seq.
    """
    items = [dict(h) for h in elo_history]
    for v in voided_history or []:
        entry = dict(v)
        entry["voided"] = True
        items.append(entry)
    items.sort(key=lambda h: h.get("seq") or 0, reverse=True)
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
    links: list[dict | None] | None = None,
) -> str:
    """Строит SVG-график динамики ELO из точек (старт + after каждого матча).

    Пустой список или одна точка без истории ([1200]) → заглушка «Нет матчей».
    Ось X подписана датами первой и последней точки (dates); пунктирная линия
    на уровне 1200 — старт. min/max — цветные метки на линии, текущее значение
    и период — в HTML-легенде под графиком (без вложенных SVG-подписей).
    links — параллельный points список {url, title} | None: точка со ссылкой
    получает прозрачный хит-круг r=9 и ведёт, например, к записи вердикта.
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
    dots = ""
    for i, v in enumerate(points):
        dot = f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3.5" class="chart-dot"/>'
        link = links[i] if links and i < len(links) else None
        if link:
            href = html.escape(str(link.get("url", "")), quote=True)
            title = html.escape(str(link.get("title", "")))
            dots += (
                f'<a href="{href}" class="chart-dot-link">{dot}'
                f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="9" '
                f'class="chart-dot-hit"><title>{title}</title></circle></a>'
            )
        else:
            dots += dot
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

    entries: список {elo: int, id: str = "", name: str = "", games: int = 0,
    caption: str = "", hit: bool = True}; сортировка
    по убыванию Elo — внутри. У каждого бара имя модели и значение.
    Бар и имя модели с непустым id — ссылки на профиль `/model/<id>`.
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
        mid = str(p.get("id", ""))
        row_svg = (
            f'<rect x="{x(lo):.1f}" y="{cy - bar_h / 2:.1f}" '
            f'width="{max(1.0, x(v) - x(lo)):.1f}" height="{bar_h}" rx="4" '
            f'class="{cls}" style="{style}">'
            f"<title>{tip}</title></rect>"
            f'<text x="{left - 8}" y="{cy + 4:.1f}" text-anchor="end" '
            f'class="dist-name">{label}<title>{tip}</title></text>'
        )
        if caption:
            row_svg += (
                f'<text x="{left - 8}" y="{cy + 15:.1f}" text-anchor="end" '
                f'class="dist-caption">{html.escape(caption)}<title>{tip}</title></text>'
            )
        if mid:
            row_svg = (
                f'<a href="/model/{html.escape(mid)}" class="dist-link">{row_svg}</a>'
            )
        bars += (
            row_svg
            + f'<text x="{x(v) + 6:.1f}" y="{cy + 4:.1f}" '
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


# ─── Аналитика: интервалы рейтинга (A1) ─────────────────────────────


def interval_groups(rows: list[dict]) -> dict:
    """Группы неразличимых мест: цепочки перекрывающихся интервалов (A1).

    rows — записи пула [{id, elo, games, name, caption, ...}]; порядок
    результата — ELO по убыванию, затем id. Половина интервала —
    confidence_half_width(games); у модели без игр интервала нет.
    Соседние строки перекрываются, если нижняя граница верхней ≤ верхней
    границе нижней; группа — максимальная цепочка (транзитивно по
    соседям). Возвращает {"rows", "groups"}: строки дополнены
    half/has_interval/lo/hi и group (номер группы с 1; 0 — место
    различимо), groups — [{"start", "end"}] индексы строк.
    """
    ordered = [dict(r) for r in rows]
    ordered.sort(
        key=lambda r: (-int(r.get("elo", DEFAULT_ELO)), str(r.get("id", "")))
    )
    for r in ordered:
        elo = int(r.get("elo", DEFAULT_ELO))
        half = confidence_half_width(int(r.get("games", 0)))
        r["half"] = half
        r["has_interval"] = half is not None
        r["lo"] = elo - half if half is not None else elo
        r["hi"] = elo + half if half is not None else elo
        r["group"] = 0

    groups: list[dict] = []
    i = 0
    n = len(ordered)
    while i < n:
        j = i
        while (
            j + 1 < n
            and ordered[j]["has_interval"]
            and ordered[j + 1]["has_interval"]
            and ordered[j]["lo"] <= ordered[j + 1]["hi"]
        ):
            j += 1
        if j > i:
            groups.append({"start": i, "end": j})
        i = j + 1
    for number, group in enumerate(groups, start=1):
        for k in range(group["start"], group["end"] + 1):
            ordered[k]["group"] = number
    return {"rows": ordered, "groups": groups}


def build_rating_intervals_svg(rows: list[dict], width: int = 860) -> str:
    """SVG блока A1: место, имя (ссылка), ELO и интервал ±400/√игр.

    rows — строки interval_groups()["rows"]. Полоса — интервал модели
    (у модели без игр только точка и прочерк), группы «место не
    определено» выделены фоном и правой меткой. Пустой список → "".
    """
    if not rows:
        return ""

    row_h, top, bottom = 26, 44, 14
    elo_x = 296
    plot_x0, plot_x1 = 310, width - 132
    label_x = width - 10
    height = top + row_h * len(rows) + bottom

    values: list[int] = []
    for r in rows:
        values.append(int(r.get("elo", DEFAULT_ELO)))
        if r.get("has_interval"):
            values += [int(r["lo"]), int(r["hi"])]
    lo, hi = min(values), max(values)
    if lo == hi:
        lo, hi = lo - 10, hi + 10
    pad = (hi - lo) * 0.08 or 10
    lo, hi = lo - pad, hi + pad

    def x(value: float) -> float:
        return plot_x0 + (plot_x1 - plot_x0) * (value - lo) / (hi - lo)

    groups: list[list[int]] = []
    for i, r in enumerate(rows):
        number = int(r.get("group") or 0)
        if not number:
            continue
        if groups and groups[-1][0] == number:
            groups[-1][2] = i
        else:
            groups.append([number, i, i])

    parts: list[str] = []
    for _, start, end in groups:
        band_y = top + start * row_h + 2
        band_h = row_h * (end - start + 1) - 4
        parts.append(
            f'<rect x="4" y="{band_y}" width="{width - 8}" height="{band_h}" '
            f'rx="6" class="interval-group-band"/>'
        )
        center_y = top + (start + end) / 2 * row_h + 13 + 4
        parts.append(
            f'<text x="{label_x}" y="{center_y:.1f}" text-anchor="end" '
            f'class="interval-group-label">место не определено</text>'
        )

    step = 50 if hi - lo <= 400 else 100
    tick = math.ceil(lo / step) * step
    while tick <= hi:
        gx = x(tick)
        parts.append(
            f'<line x1="{gx:.1f}" y1="{top - 14}" x2="{gx:.1f}" '
            f'y2="{height - bottom}" class="chart-grid"/>'
        )
        parts.append(
            f'<text x="{gx:.1f}" y="20" text-anchor="middle" '
            f'class="chart-tick">{tick}</text>'
        )
        tick += step

    for i, r in enumerate(rows):
        cy = top + i * row_h + 13
        elo = int(r.get("elo", DEFAULT_ELO))
        mid = str(r.get("id", ""))
        name = html.escape(str(r.get("name", mid)))
        caption = str(r.get("caption", ""))
        grouped = bool(r.get("group"))
        if r.get("has_interval"):
            bx1, bx2 = x(int(r["lo"])), x(int(r["hi"]))
            interval_note = f"{int(r['lo'])}–{int(r['hi'])}"
            parts.append(
                f'<line x1="{bx1:.1f}" y1="{cy:.1f}" x2="{bx2:.1f}" '
                f'y2="{cy:.1f}" class="interval-bar'
                f'{" interval-bar-grouped" if grouped else ""}">'
                f"<title>{html.escape(name)}: интервал {interval_note}</title>"
                f"</line>"
            )
        tooltip = f"{name} — Elo {elo}"
        if caption:
            tooltip += f" ({html.escape(caption)})"
        if not r.get("has_interval"):
            tooltip += " · игр нет, интервал не определён"
        parts.append(
            f'<text x="8" y="{cy + 4}" class="interval-rank'
            f'{" interval-rank-grouped" if grouped else ""}">'
            f'{"≈" if grouped else ""}{i + 1}</text>'
        )
        parts.append(
            f'<a href="/model/{html.escape(mid)}" class="interval-name">'
            f"{name}<title>{tooltip}</title></a>"
        )
        parts.append(
            f'<text x="{elo_x}" y="{cy + 4}" text-anchor="end" '
            f'class="interval-elo">{elo}</text>'
        )
        parts.append(
            f'<a href="/model/{html.escape(mid)}">'
            f'<circle cx="{x(elo):.1f}" cy="{cy:.1f}" r="4" class="chart-dot'
            f'{" interval-dot-grouped" if grouped else ""}">'
            f"<title>{tooltip}</title></circle></a>"
        )
        if not r.get("has_interval"):
            parts.append(
                f'<text x="{elo_x + 8}" y="{cy + 4}" class="interval-gap">—</text>'
            )

    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart chart-intervals" '
        f'role="img" aria-label="Интервалы рейтинга: {len(rows)} моделей, '
        f'групп «место не определено»: {len(groups)}">'
        + "".join(parts)
        + "</svg>"
    )


# ─── Аналитика: динамика ELO (A2) ───────────────────────────────────

ELO_LINES_LIMIT = 10
ELO_LINES_DEFAULT = 5
ELO_PERIOD_DEFAULT = 90
ELO_LINE_COLORS = (
    "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#a855f7",
    "#ec4899", "#14b8a6", "#f97316", "#8b949e", "#84cc16",
)


def parse_lines_param(raw: str | None, models: dict) -> list[str]:
    """Разбор `lines` блока A2: CSV id моделей реестра.

    Пустые токены, дубликаты и неизвестные id отбрасываются; при более
    чем ELO_LINES_LIMIT моделях остаются наибольшие по текущему ELO.
    Пустой результат — вызывающий подставляет топ по умолчанию.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for token in str(raw or "").split(","):
        mid = token.strip()
        if not mid or mid in seen or mid not in models:
            continue
        seen.add(mid)
        ids.append(mid)
    if len(ids) > ELO_LINES_LIMIT:
        ids.sort(key=lambda mid: (
            -int(models[mid].get("elo", DEFAULT_ELO)), mid,
        ))
        ids = ids[:ELO_LINES_LIMIT]
    return ids


def parse_period_param(raw: str | None) -> int | None:
    """Разбор `period` блока A2: 30/90/all (по умолчанию 90).

    None — «всё» (без фильтра дат).
    """
    value = str(raw or "").strip().lower()
    if value == "all":
        return None
    if value in ("30", "90"):
        return int(value)
    return ELO_PERIOD_DEFAULT


def default_line_ids(models: dict, limit: int = ELO_LINES_DEFAULT) -> list[str]:
    """Топ активных моделей по ELO — выбор A2 по умолчанию."""
    active = [
        (mid, info) for mid, info in models.items()
        if info.get("status", "active") != "archived"
    ]
    active.sort(key=lambda pair: (
        -int(pair[1].get("elo", DEFAULT_ELO)), pair[0],
    ))
    return [mid for mid, _ in active[:limit]]


def day_of(item: dict) -> str:
    """Календарный день записи: `date`, при отсутствии — `recorded_at`."""
    value = str(item.get("date") or "").strip()
    if value:
        return value[:10]
    return str(item.get("recorded_at") or "").strip()[:10]


def build_elo_series(elo_history: list[dict], selected: list[str],
                     days: int | None) -> dict:
    """Линии A2: точки (позиция матча, ELO после) по выбранным моделям.

    Шкала X — общий упорядоченный список матчей выбранных моделей
    (по `seq`). Окно периода `days` отсчитывается от последней даты
    истории (включительно); `days=None` — вся история. Возвращает
    {"x_count", "dates", "series": {mid: [(x, elo)]}}, "dates" — дни
    первого и последнего матча выборки.
    """
    ordered = sorted(elo_history or [], key=lambda e: e.get("seq", 0))
    cutoff = ""
    if days is not None and ordered:
        last_day = next(
            (day_of(e) for e in reversed(ordered) if day_of(e)), "",
        )
        if last_day:
            try:
                cutoff = (
                    date.fromisoformat(last_day) - timedelta(days=days - 1)
                ).isoformat()
            except ValueError:
                cutoff = ""

    series: dict[str, list[tuple[int, int]]] = {mid: [] for mid in selected}
    dates: list[str] = []
    x_count = 0
    for e in ordered:
        a_id = str(e.get("model_a_id") or "")
        b_id = str(e.get("model_b_id") or "")
        if a_id not in series and b_id not in series:
            continue
        day = day_of(e)
        if days is not None:
            if not cutoff or not day or day < cutoff:
                continue
        for side, elo_key in (("model_a_id", "elo_a"), ("model_b_id", "elo_b")):
            mid = str(e.get(side) or "")
            if mid not in series:
                continue
            after = (e.get(elo_key) or {}).get("after")
            if after is None:
                continue
            series[mid].append((x_count, int(after)))
        dates.append(day)
        x_count += 1

    visible_days = [d for d in dates if d]
    span = (visible_days[0], visible_days[-1]) if visible_days else ()
    return {"x_count": x_count, "dates": span, "series": series}


def build_elo_multiline_svg(series: list[dict], x_count: int,
                            dates: tuple[str, str] | None = None,
                            colors: tuple[str, ...] = ELO_LINE_COLORS,
                            width: int = 860, height: int = 260) -> str:
    """SVG блока A2: ломаные выбранных моделей на общей шкале матчей.

    series — [{"id", "name", "points": [(x, elo)]}] в порядке легенды;
    цвета берутся по индексу серии (палитра ELO_LINE_COLORS). Ось Y
    включает опорную линию 1200; подписи дат — первая и последняя.
    Серия с непустым id кликабельна: линия оборачивается ссылкой
    на `/model/<id>` (невидимый хит-слой stroke-width 12).
    Нет матчей у всех серий → "" (шаблон показывает пустое состояние).
    """
    drawn = [s for s in series if s.get("points")]
    if x_count <= 0 or not drawn:
        return ""

    left, right, top, bottom = 52, 16, 18, 30
    plot_w = width - left - right
    plot_h = height - top - bottom

    values = [v for s in drawn for _, v in s["points"]]
    lo, hi = min(values), max(values)
    lo, hi = min(lo, DEFAULT_ELO), max(hi, DEFAULT_ELO)
    if lo == hi:
        lo, hi = lo - 10, hi + 10
    pad = (hi - lo) * 0.1 or 10
    lo, hi = lo - pad, hi + pad

    def x(i: int) -> float:
        if x_count <= 1:
            return left + plot_w / 2
        return left + plot_w * i / (x_count - 1)

    def y(value: float) -> float:
        return top + plot_h * (1 - (value - lo) / (hi - lo))

    grid = ""
    for frac, label in ((0.0, hi), (0.5, (hi + lo) / 2), (1.0, lo)):
        gy = top + plot_h * frac
        grid += (
            f'<line x1="{left}" y1="{gy:.1f}" x2="{width - right}" '
            f'y2="{gy:.1f}" class="chart-grid"/>'
            f'<text x="{left - 8}" y="{gy + 4:.1f}" text-anchor="end" '
            f'class="chart-tick">{label:.0f}</text>'
        )

    baseline_y = y(DEFAULT_ELO)
    baseline = (
        f'<line x1="{left}" y1="{baseline_y:.1f}" x2="{width - right}" '
        f'y2="{baseline_y:.1f}" class="chart-baseline">'
        f"<title>старт: {DEFAULT_ELO}</title></line>"
    )

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

    lines = ""
    for index, item in enumerate(drawn):
        color = colors[index % len(colors)]
        points = item["points"]
        mid = str(item.get("id", ""))
        name = html.escape(str(item.get("name", item.get("id", ""))))
        poly = " ".join(f"{x(px):.1f},{y(pv):.1f}" for px, pv in points)
        end_x, end_y = x(points[-1][0]), y(points[-1][1])
        visible = (
            f'<polyline points="{poly}" class="chart-line-multi" fill="none" '
            f'stroke="{color}">'
            f"<title>{name}: {len(points)} матчей, Elo {points[-1][1]}</title>"
            f"</polyline>"
        )
        end_dot = (
            f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="3.5" '
            f'fill="{color}"><title>{name}: текущий Elo {points[-1][1]}</title>'
            f"</circle>"
        )
        if mid:
            hit = (
                f'<polyline points="{poly}" class="chart-line-hit" fill="none" '
                f'stroke-linecap="round">'
                f"<title>{name}: {len(points)} матчей, Elo {points[-1][1]}"
                f" — открыть профиль</title></polyline>"
            )
            lines += (
                f'<a href="/model/{html.escape(mid)}">{visible}{hit}{end_dot}</a>'
            )
        else:
            lines += visible + end_dot

    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="Динамика ELO: линий {len(drawn)}, матчей {x_count}">'
        f"{grid}{baseline}{lines}{axis}</svg>"
    )


# ─── Аналитика: активность по дням (A3) ─────────────────────────────


def activity_by_day(elo_history: list[dict]) -> list[dict]:
    """Число применённых вердиктов по календарным дням (A3).

    День — `date[:10]`, fallback `recorded_at[:10]`; дни без вердиктов
    между первым и последним заполняются нулями. Возвращает
    [{"day": "YYYY-MM-DD", "count": N}]; пустая история → [].
    """
    counts: dict[str, int] = {}
    for item in elo_history or []:
        day = day_of(item)
        if not day:
            continue
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        counts[day] = counts.get(day, 0) + 1
    if not counts:
        return []
    cursor = date.fromisoformat(min(counts))
    last = date.fromisoformat(max(counts))
    days: list[dict] = []
    while cursor <= last:
        key = cursor.isoformat()
        days.append({"day": key, "count": counts.get(key, 0)})
        cursor += timedelta(days=1)
    return days


def build_activity_bars_svg(days: list[dict], links: bool = True,
                            width: int = 860, height: int = 170) -> str:
    """SVG столбиков A3: число вердиктов на день, подсказка — дата и N.

    links=True — столбики дней с вердиктами ведут на историю этого дня
    (`/history?from=D&to=D`); links=False — без ссылок (слепок: фильтр
    дат живёт только в консоли, зеркало его не применяет).
    """
    if not days:
        return ""
    left, right, top, bottom = 44, 12, 16, 26
    plot_w = width - left - right
    plot_h = height - top - bottom
    n = len(days)
    peak = max(d["count"] for d in days)
    top_value = max(peak, 1)
    bar_span = plot_w / n
    bar_w = max(bar_span * 0.7, 1.6)

    bars = ""
    for index, item in enumerate(days):
        count = item["count"]
        bar_h = plot_h * count / top_value
        bx = left + index * bar_span + (bar_span - bar_w) / 2
        by = top + plot_h - bar_h
        cls = "activity-bar" + ("" if count else " activity-bar-zero")
        rect = (
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" '
            f'height="{bar_h:.1f}" class="{cls}">'
            f'<title>{_fmt_axis_date(item["day"])}: {count}</title></rect>'
        )
        if links and count:
            day = item["day"]
            rect = f'<a href="/history?from={day}&amp;to={day}">{rect}</a>'
        bars += rect

    grid = (
        f'<line x1="{left}" y1="{top}" x2="{width - right}" y2="{top}" '
        f'class="chart-grid"/>'
        f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" '
        f'y2="{top + plot_h}" class="chart-grid"/>'
        f'<text x="{left - 8}" y="{top + 4}" text-anchor="end" '
        f'class="chart-tick">{top_value}</text>'
        f'<text x="{left - 8}" y="{top + plot_h + 4}" text-anchor="end" '
        f'class="chart-tick">0</text>'
    )
    axis = (
        f'<text x="{left}" y="{height - 6}" text-anchor="start" '
        f'class="chart-tick">{_fmt_axis_date(days[0]["day"])}</text>'
        f'<text x="{width - right}" y="{height - 6}" text-anchor="end" '
        f'class="chart-tick">{_fmt_axis_date(days[-1]["day"])}</text>'
    )
    total = sum(d["count"] for d in days)
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart chart-activity" '
        f'role="img" aria-label="Активность по дням: дней {n}, вердиктов '
        f'{total}, максимум {peak}">{grid}{bars}{axis}</svg>'
    )


# ─── Аналитика: матрица пар (A4) ────────────────────────────────────


def _short_name(text: str, limit: int = 16) -> str:
    """Обрезка подписи матрицы: длинное имя укорачивается многоточием."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def pair_matrix(ids: list[str], pair_stats: dict) -> dict:
    """Матрица применённых встреч активного пула (A4).

    ids — порядок строк/столбцов (ELO по убыванию); pair_stats —
    {frozenset({a, b}): число игр}; принимается и словарь get_pair_stats
    с ключом "games". Возвращает {"ids", "rows", "meets"}: rows[i][j] —
    None на диагонали и в ячейках без встреч, иначе {"count": N,
    "rematch": N > 1}. Заполняются только ячейки со встречами: пул в
    сотни моделей остаётся разреженным (без миллионов объектов).
    """
    ordered = list(ids)
    n = len(ordered)
    rows: list[list[dict | None]] = [[None] * n for _ in range(n)]

    def _games(value) -> int:
        if isinstance(value, dict):
            return int(value.get("games", 0))
        return int(value or 0)

    pos = {mid: i for i, mid in enumerate(ordered)}
    meets = 0
    for key, value in (pair_stats or {}).items():
        pair = tuple(key)
        if len(pair) != 2:
            continue
        i = pos.get(pair[0])
        j = pos.get(pair[1])
        if i is None or j is None or i == j:
            continue
        count = _games(value)
        if count <= 0:
            continue
        info = {"count": count, "rematch": count > 1}
        rows[i][j] = info
        rows[j][i] = info
        meets += count
    return {"ids": ordered, "rows": rows, "meets": meets}


def build_pair_matrix_svg(matrix: dict, names: dict | None = None,
                          links: bool = True, width: int = 860) -> str:
    """SVG тепловой матрицы A4: заливка по числу игр, метка рематча.

    names — {id: имя} для подписей; links=True — ячейки встреч ведут на
    историю пары (`/history?pair=a:b`), links=False — без ссылок
    (слепок). Нет моделей или нет ни одной встречи → "" (пустое
    состояние рендерит шаблон). Отрисовка разреженная: фон и сетка —
    O(n) элементов, прямоугольники и подписи — только у ячеек встреч
    (плотная n²-сетка на пуле в сотни моделей давала бы сотни мегабайт).
    """
    ids = list(matrix.get("ids") or [])
    n = len(ids)
    if n == 0 or not matrix.get("meets"):
        return ""
    names = names or {}

    label_len = max(len(str(names.get(mid, mid))) for mid in ids)
    label_w = int(min(max(label_len * 6.6 + 14, 90), 200))
    cell = max(12.0, min((width - label_w - 12) / n, 28.0))
    header_h = 78
    left = label_w
    top = header_h
    area = cell * n
    height = header_h + area + 10

    counters: list[tuple[int, int, dict]] = []
    max_count = 0
    for i, row in enumerate(matrix["rows"]):
        for j, info in enumerate(row):
            if info is None:
                continue
            counters.append((i, j, info))
            if info["count"] > max_count:
                max_count = info["count"]

    labels_parts: list[str] = []
    for j, mid in enumerate(ids):
        cx = left + (j + 0.5) * cell
        full = str(names.get(mid, mid))
        labels_parts.append(
            f'<text x="{cx:.1f}" y="{top - 10}" text-anchor="start" '
            f'transform="rotate(-45 {cx:.1f} {top - 10})" '
            f'class="pair-col-label">{html.escape(_short_name(full, 14))}'
            f"<title>{html.escape(full)}</title></text>"
        )
    labels = "".join(labels_parts)

    row_parts: list[str] = []
    for i, mid in enumerate(ids):
        cy = top + i * cell
        full = str(names.get(mid, mid))
        row_parts.append(
            f'<text x="{left - 8}" y="{cy + cell / 2 + 4:.1f}" '
            f'text-anchor="end" class="pair-row-label">'
            f"{html.escape(_short_name(full, 22))}"
            f"<title>{html.escape(full)}</title></text>"
        )
    row_labels = "".join(row_parts)

    grid_d = []
    for k in range(n + 1):
        x = left + k * cell
        grid_d.append(f"M{x:.1f} {top:.1f}V{top + area:.1f}")
        y = top + k * cell
        grid_d.append(f"M{left:.1f} {y:.1f}H{left + area:.1f}")
    background = (
        f'<rect x="{left:.1f}" y="{top:.1f}" width="{area:.1f}" '
        f'height="{area:.1f}" class="pair-cells-bg"/>'
        f'<path d="{" ".join(grid_d)}" class="pair-grid-lines"/>'
    )

    diag_parts: list[str] = []
    for k in range(n):
        x = left + k * cell
        y = top + k * cell
        diag_parts.append(
            f'<rect x="{x + 0.5:.1f}" y="{y + 0.5:.1f}" '
            f'width="{cell - 1:.1f}" height="{cell - 1:.1f}" '
            f'class="pair-cell pair-cell-diagonal"/>'
        )
    diagonal = "".join(diag_parts)

    body_parts: list[str] = []
    for i, j, info in counters:
        a, b = ids[i], ids[j]
        cx = left + j * cell
        cy = top + i * cell
        count = info["count"]
        full_a = str(names.get(a, a))
        full_b = str(names.get(b, b))
        cls = "pair-cell pair-cell-set"
        style = f' style="fill-opacity: {0.18 + 0.62 * count / max_count:.2f}"'
        title = f"{full_a} vs {full_b}: {count}"
        if info["rematch"]:
            cls += " pair-cell-rematch"
            title += " · рематч"
        cell_svg = (
            f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cell:.1f}" '
            f'height="{cell:.1f}" class="{cls}"{style}>'
            f"<title>{html.escape(title)}</title></rect>"
        )
        if cell >= 19:
            cell_svg += (
                f'<text x="{cx + cell / 2:.1f}" y="{cy + cell / 2 + 3.5:.1f}" '
                f'text-anchor="middle" class="pair-cell-count">{count}</text>'
            )
        if info["rematch"]:
            cell_svg += (
                f'<circle cx="{cx + cell - 4:.1f}" cy="{cy + 4:.1f}" '
                f'r="2.2" class="pair-rematch-dot"/>'
            )
        if links:
            pair = html.escape(":".join(sorted((a, b))))
            body_parts.append(f'<a href="/history?pair={pair}">{cell_svg}</a>')
        else:
            body_parts.append(cell_svg)
    body = "".join(body_parts)

    return (
        f'<svg viewBox="0 0 {label_w + area + 12:.0f} {height:.0f}" '
        f'class="chart chart-matrix" role="img" aria-label="Матрица пар: '
        f'{n} моделей, встреч {matrix.get("meets", 0)}">'
        f"{labels}{row_labels}{background}{diagonal}{body}</svg>"
    )


# ─── Аналитика: агенты и компании (A5) ──────────────────────────────


def group_summary(models: dict, key: str) -> list[dict]:
    """Сводка активного пула по агентам или компаниям (A5).

    key — "agent"/"provider"; пустые значения собираются в «без
    агента»/«без компании». Строка: моделей, медиана и среднее ELO,
    суммарные игры и победы, винрейт (доля побед от игр). Порядок —
    медиана по убыванию, при равенстве — по названию.
    """
    empty_labels = {"agent": "без агента", "provider": "без компании"}
    groups: dict[str, dict] = {}
    for mid, info in models.items():
        name = str(info.get(key) or "").strip()
        row = groups.setdefault(name, {
            "name": name, "models": 0, "elos": [], "games": 0, "wins": 0,
        })
        row["models"] += 1
        row["elos"].append(int(info.get("elo", DEFAULT_ELO)))
        row["games"] += int(info.get("games", 0))
        row["wins"] += int(info.get("wins", 0))

    rows: list[dict] = []
    for row in groups.values():
        elos = sorted(row["elos"])
        n = len(elos)
        median = elos[n // 2] if n % 2 else (elos[n // 2 - 1] + elos[n // 2]) / 2
        rows.append({
            "name": row["name"] or empty_labels.get(key, "—"),
            "models": row["models"],
            "median": int(round(median)),
            "mean": int(round(sum(elos) / n)),
            "games": row["games"],
            "wins": row["wins"],
            "winrate": (
                f"{round(row['wins'] / row['games'] * 100)}%"
                if row["games"] else "—"
            ),
        })
    rows.sort(key=lambda r: (-r["median"], r["name"]))
    return rows


# ─── Аналитика: взлёты и падения (A6) ───────────────────────────────

DELTA_WINDOWS = (7, 30)
DELTA_TOP = 5


def delta_leaders(elo_history: list[dict], models: dict, days: int,
                  top: int = DELTA_TOP) -> dict:
    """Топ роста и падения по сумме ΔELO личных матчей за окно `days` (A6).

    Окно — последние `days` календарных дней от последней даты истории
    включительно (опорная дата — для детерминизма слепка и тестов).
    Учитываются модели из `models` (активный пул). Модель попадает в
    топ роста/падения только при ненулевой сумме; модели без матчей в
    окне не показываются. Возвращает {"days", "date", "growth", "fall"};
    строки — {id, name, sum, games}.
    """
    events = sorted(elo_history or [], key=lambda e: e.get("seq", 0))
    last_day = ""
    for item in events:
        day = day_of(item)
        if day and day > last_day:
            last_day = day

    window_start = ""
    if last_day:
        try:
            start = date.fromisoformat(last_day) - timedelta(days=days - 1)
            window_start = start.isoformat()
        except ValueError:
            window_start = ""

    totals: dict[str, dict] = {}
    for item in events:
        day = day_of(item)
        if not day or not window_start or day < window_start or day > last_day:
            continue
        for side, elo_key in (("model_a_id", "elo_a"), ("model_b_id", "elo_b")):
            mid = str(item.get(side) or "")
            if not mid or mid not in models:
                continue
            info = item.get(elo_key) or {}
            before, after = info.get("before"), info.get("after")
            if before is None or after is None:
                continue
            row = totals.setdefault(mid, {"sum": 0, "games": 0})
            row["sum"] += int(after) - int(before)
            row["games"] += 1

    rows: list[dict] = []
    for mid, row in totals.items():
        if row["sum"] == 0:
            continue
        rows.append({
            "id": mid,
            "name": models.get(mid, {}).get("name", mid),
            "sum": row["sum"],
            "games": row["games"],
        })
    growth = sorted(
        (r for r in rows if r["sum"] > 0), key=lambda r: (-r["sum"], r["id"]),
    )[:top]
    fall = sorted(
        (r for r in rows if r["sum"] < 0), key=lambda r: (r["sum"], r["id"]),
    )[:top]
    return {"days": days, "date": last_day, "growth": growth, "fall": fall}


def stale_models(elo_history: list[dict], models: dict,
                 gap: int = STALE_GLOBAL_GAP) -> list[dict]:
    """Активные модели без личных матчей в последних `gap` вердиктах (A6).

    Возвращает строки {id, name, games} (игры — по реестру); порядок —
    игры по убыванию, при равенстве — по id.
    """
    ordered = sorted(elo_history or [], key=lambda e: e.get("seq", 0))
    played: set[str] = set()
    for item in ordered[-gap:]:
        played.add(str(item.get("model_a_id") or ""))
        played.add(str(item.get("model_b_id") or ""))
    rows = [
        {"id": mid, "name": info.get("name", mid),
         "games": int(info.get("games", 0) or 0)}
        for mid, info in (models or {}).items() if mid not in played
    ]
    rows.sort(key=lambda r: (-r["games"], r["id"]))
    return rows


# ─── Аналитика: сила оппозиции (A7) ─────────────────────────────────


def opposition_strength(elo_history: list[dict], pool_ids: list[str],
                        models: dict, top_ids: set[str] | None = None,
                        top: int = 10) -> list[dict]:
    """Сила оппозиции активного пула (A7).

    Строки — в порядке pool_ids (рейтинг, ELO вниз). Средний ELO
    соперников — по ELO соперника ДО каждого матча модели; «апсеты» —
    победы над моделями текущего топ-`top` (top_ids по умолчанию —
    первые `top` из pool_ids); игры — применённые матчи. Модели без игр
    получают None в opp_avg/upsets (в шаблоне — прочерк).
    """
    ids = list(pool_ids)
    if top_ids is None:
        top_ids = set(ids[:top])
    stats = {mid: {"opp_sum": 0, "games": 0, "upsets": 0} for mid in ids}
    for item in elo_history or []:
        a_id = str(item.get("model_a_id") or "")
        b_id = str(item.get("model_b_id") or "")
        winner = str(item.get("winner") or "")
        pre = {
            "a": (item.get("elo_a") or {}).get("before"),
            "b": (item.get("elo_b") or {}).get("before"),
        }
        for side, mid, opp, opp_side in (
            ("a", a_id, b_id, "b"), ("b", b_id, a_id, "a"),
        ):
            row = stats.get(mid)
            if row is None:
                continue
            opp_elo = pre[opp_side]
            row["games"] += 1
            row["opp_sum"] += int(opp_elo) if opp_elo is not None else DEFAULT_ELO
            if winner == side and opp in top_ids:
                row["upsets"] += 1
    rows: list[dict] = []
    for mid in ids:
        row = stats[mid]
        info = models.get(mid, {})
        rows.append({
            "id": mid,
            "name": info.get("name", mid),
            "elo": int(info.get("elo", DEFAULT_ELO)),
            "opp_avg": (
                int(round(row["opp_sum"] / row["games"])) if row["games"] else None
            ),
            "upsets": row["upsets"] if row["games"] else None,
            "games": row["games"],
        })
    return rows


# ─── Аналитика: исходы (A8) ─────────────────────────────────────────


def _winner_rows(events: list[dict]) -> dict:
    """Числа и проценты исходов набора событий (a/b/draw)."""
    counts = {"a": 0, "b": 0, "draw": 0}
    total = 0
    for item in events or []:
        winner = str(item.get("winner") or "")
        if winner not in counts:
            continue
        counts[winner] += 1
        total += 1
    rows = [
        {
            "key": key,
            "label": WINNER_LABELS[key],
            "n": counts[key],
            "pct": round(counts[key] * 100 / total) if total else 0,
        }
        for key in ("a", "b", "draw")
    ]
    return {"total": total, "rows": rows}


def winner_shares(elo_history: list[dict],
                  task_ids: list[str] | None = None) -> dict:
    """Доли исходов применённых вердиктов (A8).

    Без `task_ids` — только общие числа и проценты; с непустым списком
    добавляет разбивку `by_task` в порядке task_ids (таск записи —
    префикс matchup). Проценты округляются до целого.
    """
    result = _winner_rows(elo_history)
    if task_ids:
        by_task = []
        for tid in task_ids:
            events = [
                item for item in (elo_history or [])
                if history_task_id(item) == tid
            ]
            row = _winner_rows(events)
            if row["total"]:
                by_task.append({"task": tid, **row})
        result["by_task"] = by_task
    return result
