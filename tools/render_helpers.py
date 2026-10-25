#!/usr/bin/env python3
"""render_helpers.py — общие helpers для рендеринга leaderboard и истории.

Используются tools/server.py.
"""

from __future__ import annotations

import html
import math
from datetime import date, timedelta

from elo import expected_score, k_factor

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
        void_date_raw = ""
        void_reason = ""
        if voided:
            void = item.get("void") or {}
            void_date_raw = str(void.get("date") or void.get("recorded_at") or "")
            void_date = format_recorded_at(
                void.get("recorded_at", ""), void.get("date", "")
            )
            void_str = "аннулировано"
            if void_date:
                void_str += f" {void_date}"
            void_reason = str(void.get("reason", "")).strip()
            if void_reason:
                void_str += f" · {void_reason}"

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
            "date_raw": str(item.get("date") or "")[:10],
            "recorded_at_raw": str(item.get("recorded_at") or ""),
            "hit": bool(item.get("hit")) if highlight else False,
            "matchup": item.get("matchup", ""),
            "task": history_task_id(item),
            "seq": item.get("seq"),
            "winner": winner,
            "winner_label": winner_label,
            "winner_aria": winner_aria,
            "voided": voided,
            "void_str": void_str,
            "void_date_raw": void_date_raw,
            "void_reason": void_reason,
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


def _wrap_chart(svg: str) -> str:
    """SVG в обёртке с горизонтальной прокруткой на узких экранах.

    Ширину графика задаёт viewBox; на телефоне он не сжимается ниже
    800 px (CSS), а излишек прокручивается внутри карточки.
    """
    return f'<div class="chart-scroll">{svg}</div>'


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
    return _wrap_chart(svg) + legend


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


MOMENTUM_WINDOW = 10
MOMENTUM_MIN_GAMES = 16
MOMENTUM_Z_THRESHOLD = 1.5
MOMENTUM_MAX_AGE_DAYS = 14


def _parse_iso_date(value: str) -> date | None:
    """Разбирает дату журнала (YYYY-MM-DD); None, если формат не тот."""
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _short_date(value: str) -> str:
    """Дата для тултипа: ДД.ММ или пустая строка."""
    parsed = _parse_iso_date(value)
    return parsed.strftime("%d.%m") if parsed else ""


def _momentum_title(
    delta: int,
    wins: int,
    draws: int,
    losses: int,
    last_date: str,
    window: int,
) -> str:
    """Тултип индикатора: ΔELO, счёт окна и дата последней игры."""
    games_word = plural_ru(window, "игра", "игры", "игр")
    text = (
        f"За {window} {games_word} рейтинг {delta:+d}: "
        f"{wins} {plural_ru(wins, 'победа', 'победы', 'побед')}, "
        f"{draws} {plural_ru(draws, 'ничья', 'ничьи', 'ничьих')}, "
        f"{losses} {plural_ru(losses, 'поражение', 'поражения', 'поражений')}."
    )
    short = _short_date(last_date)
    if short:
        text += f" Последняя игра {short}."
    return text


def _window_metrics(
    records: list[dict], window: int, delta: int | None = None,
) -> tuple[int, float]:
    """Δ и z по последним `window` записям.

    По умолчанию Δ — сумма дельт окна; `delta` позволяет подставить
    authoritative-значение (ELO_now − ELO до окна).
    """
    recent = records[-window:]
    if delta is None:
        delta = sum(r["delta"] for r in recent)
    variance = sum(r["var"] for r in recent)
    sd = math.sqrt(variance)
    return delta, (delta / sd if sd > 0 else 0.0)


def _state_metrics(
    records: list[dict],
    end: int,
    window: int,
    final_delta: int | None,
    last_index: int,
) -> tuple[int, float]:
    """Δ и z окна, заканчивающегося на индексе `end`."""
    start = max(0, end + 1 - window)
    delta = 0
    variance = 0.0
    for index in range(start, end + 1):
        delta += records[index]["delta"]
        variance += records[index]["var"]
    if final_delta is not None and end == last_index:
        delta = final_delta
    sd = math.sqrt(variance)
    return delta, (delta / sd if sd > 0 else 0.0)


def _momentum_state(
    records: list[dict],
    window: int,
    min_games: int,
    z_threshold: float,
    max_age_days: int,
    final_delta: int | None = None,
) -> str:
    """Состояние стрелки: вход по двум срезам, удержание пока |z| >= порога.

    Считается от конца: находится непрерывный ряд последних игр, где
    |z| >= порога в одну сторону (с учётом пауз не больше
    `max_age_days`); если в ряду есть игра после самой старой, на которой
    направление подтверждено дельтой, стрелка горит. Ряд короче двух игр
    стрелку не даёт — так вход требует двух подряд заметных срезов.
    `final_delta` — authoritative-дельта последнего окна.
    """
    total = len(records)
    if total < min_games:
        return ""
    last_index = total - 1
    _, z = _state_metrics(records, last_index, window, final_delta, last_index)
    if z >= z_threshold - 1e-9:
        sign = 1
    elif z <= -z_threshold + 1e-9:
        sign = -1
    else:
        return ""

    run: list[int] = [last_index]
    index = last_index
    while index > 0:
        prev = index - 1
        current_day = records[index].get("day")
        prev_day = records[prev].get("day")
        if (
            current_day is not None
            and prev_day is not None
            and (current_day - prev_day).days > max_age_days
        ):
            break
        _, z_prev = _state_metrics(records, prev, window, final_delta, last_index)
        if sign > 0 and z_prev < z_threshold - 1e-9:
            break
        if sign < 0 and z_prev > -z_threshold + 1e-9:
            break
        run.append(prev)
        index = prev

    if len(run) < 2:
        return ""
    for position in run[:-1]:
        if position + 1 < min_games:
            continue
        delta = records[position]["delta"]
        if (sign > 0 and delta > 0) or (sign < 0 and delta < 0):
            return "↑" if sign > 0 else "↓"
    return ""


def compute_rating_momentum(
    elo_history: list[dict],
    pool_ids: list[str],
    current_elo: dict[str, int],
    window: int = MOMENTUM_WINDOW,
    min_games: int = MOMENTUM_MIN_GAMES,
    z_threshold: float = MOMENTUM_Z_THRESHOLD,
    max_age_days: int = MOMENTUM_MAX_AGE_DAYS,
) -> dict[str, dict]:
    """Считает движение рейтинга за последние `window` личных игр.

    Δ = ELO_now − ELO до окна; место в расчёте не участвует. Заметность
    проверяется по z = Δ / sd, где sd — разброс от удачи:
    sqrt(Σ K_i² · E_i · (1 − E_i)) по играм окна. K_i — K-фактор перед
    игрой (по числу личных игр модели), E_i — ожидаемый счёт против
    соперника на момент игры.

    Стрелка не пересчитывается с нуля на каждой игре: `↑` загорается,
    когда |z| >= z_threshold на текущем и предыдущем срезе и последняя
    личная игра повысила рейтинг; горит, пока |z| не опустится ниже
    порога; после паузы больше `max_age_days` между личными играми
    состояние сбрасывается. `↓` — зеркально. Модель с `games < min_games`
    значения не получает; стрелка скрывается, если последняя игра старше
    `max_age_days` от последней даты журнала.

    Возвращает {id: {arrow, css, delta, z, games_in_window, wins, draws,
    losses, last_date, has_value, title}}. `has_value` — есть ли числовое
    значение для сортировки (достаточно игр и свежая форма); `title` —
    тултип стрелки или пояснение, почему её нет.
    """
    window = max(1, int(window))
    min_games = max(1, int(min_games))
    max_age_days = max(0, int(max_age_days))

    pool = list(pool_ids)
    pool_set = set(pool)
    history = sorted(elo_history or [], key=lambda e: e.get("seq", 0))

    personal: dict[str, list[dict]] = {mid: [] for mid in pool}
    games_before: dict[str, int] = {mid: 0 for mid in pool}
    fresh_dates: list[date] = []

    for event in history:
        event_date = _parse_iso_date(event.get("date", ""))
        if event_date is not None:
            fresh_dates.append(event_date)
        for side, own_key, opp_key in (
            ("model_a_id", "elo_a", "elo_b"),
            ("model_b_id", "elo_b", "elo_a"),
        ):
            mid = event.get(side, "")
            if mid not in pool_set:
                continue
            own = event.get(own_key) or {}
            opp = event.get(opp_key) or {}
            before = own.get("before")
            after = own.get("after")
            if before is None or after is None:
                continue
            winner = event.get("winner")
            if winner == "draw":
                result = 0.5
            elif (winner == "a" and side == "model_a_id") or (
                winner == "b" and side == "model_b_id"
            ):
                result = 1.0
            elif winner in ("a", "b"):
                result = 0.0
            else:
                continue
            delta = own.get("delta")
            if delta is None:
                delta = int(after) - int(before)
            k = k_factor(games_before[mid])
            expected = expected_score(
                int(before), int(opp.get("before", DEFAULT_ELO)),
            )
            personal[mid].append({
                "seq": event.get("seq", 0),
                "date": str(event.get("date", "") or ""),
                "day": event_date,
                "delta": int(delta),
                "elo_before": int(before),
                "elo_after": int(after),
                "opp_before": int(opp.get("before", DEFAULT_ELO)),
                "result": result,
                "k": k,
                "var": (k ** 2) * expected * (1.0 - expected),
            })
            games_before[mid] += 1

    fresh_date = max(fresh_dates) if fresh_dates else None

    momentum: dict[str, dict] = {}
    for mid in pool:
        records = personal[mid]
        last_date = records[-1]["date"] if records else ""
        item = {
            "arrow": "",
            "css": "history-delta-neutral",
            "delta": None,
            "z": None,
            "games_in_window": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "last_date": last_date,
            "has_value": False,
            "title": "",
        }
        if len(records) < min_games:
            item["title"] = (
                f"мало игр для тренда: нужно {min_games}+ личных игр"
            )
            momentum[mid] = item
            continue

        recent = records[-window:]
        wins = sum(1 for r in recent if r["result"] == 1.0)
        draws = sum(1 for r in recent if r["result"] == 0.5)
        losses = sum(1 for r in recent if r["result"] == 0.0)
        delta = int(current_elo.get(mid, recent[-1]["elo_after"])) - int(
            recent[0]["elo_before"]
        )
        _, z = _window_metrics(records, window, delta)
        state = _momentum_state(
            records, window, min_games, z_threshold, max_age_days,
            final_delta=delta,
        )

        last_parsed = _parse_iso_date(last_date)
        fresh = (
            fresh_date is not None
            and last_parsed is not None
            and (fresh_date - last_parsed).days <= max_age_days
        )
        item.update({
            "delta": delta,
            "z": z,
            "games_in_window": len(recent),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "has_value": fresh,
        })
        if not fresh:
            item["title"] = (
                f"нет личных игр в последних {max_age_days} днях"
            )
        elif state:
            item["arrow"] = state
            item["css"] = (
                "history-delta-up" if state == "↑" else "history-delta-down"
            )
            item["title"] = _momentum_title(
                delta, wins, draws, losses, last_date, window,
            )
        momentum[mid] = item
    return momentum


# ─── Аналитика: карточка «Рейтинг» (интервалы + распределение) ──────────


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


RATING_PAGE_SIZE = 50


def rating_page(
    rows: list[dict],
    groups: list[dict],
    page: int,
    page_size: int = RATING_PAGE_SIZE,
) -> dict:
    """Страница строк карточки «Рейтинг» вместе с фрагментами групп.

    rows — строки interval_groups()["rows"] (весь пул, ELO по убыванию);
    groups — groups того же результата: [{"start", "end"}] индексы строк.
    Место строки — её индекс в полном пуле, поэтому постраничная навигация
    не сдвигает места. Группа неразличимых мест может быть разрезана границей
    страницы: group_full=True — группа помещается на странице целиком,
    group_size — размер группы по всему пулу (у разрезанной больше, чем
    видно на странице).

    Возвращает {"rows", "page", "pages", "page_size", "total", "start"}.
    """
    total = len(rows)
    pages = max(1, math.ceil(total / page_size)) if page_size else 1
    page = max(1, min(int(page or 1), pages))
    start = (page - 1) * page_size
    stop = min(start + page_size, total)

    bounds = {
        number: (int(g["start"]), int(g["end"]))
        for number, g in enumerate(groups or [], start=1)
    }
    page_rows: list[dict] = []
    for index in range(start, stop):
        row = dict(rows[index])
        number = int(row.get("group") or 0)
        group_start, group_end = bounds.get(number, (0, -1))
        row["rank"] = index + 1
        row["group_full"] = bool(
            number and group_start >= start and group_end < stop
        )
        # Размер группы — по всему пулу: на разрезанной страницей группе
        # показывается её фрагмент, а считать надо целую.
        row["group_size"] = (group_end - group_start + 1) if number else 0
        page_rows.append(row)
    return {
        "rows": page_rows,
        "page": page,
        "pages": pages,
        "page_size": page_size,
        "total": total,
        "start": start,
    }


def build_rating_svg(
    rows: list[dict],
    pool: list[dict],
    highlight: bool = False,
    width: int = 860,
) -> str:
    """SVG карточки «Рейтинг»: место, имя, ELO, интервал, градиентный бар.

    rows — страница строк rating_page(): ключи id, name, elo, games, caption,
    half, lo, hi, group, rank, group_full, group_size (и hit в режиме
    «Подсвечивать»).
    pool — весь пул карточки (записи с ключом elo): шкала ELO и градиент
    считаются по нему, а не по странице, иначе страницы несопоставимы.
    Ширина колонки имён — тоже по пулу, иначе колонки «прыгают» между
    страницами. highlight — режим «Подсвечивать»: строки с hit=True
    получают класс filter-hit, остальные — filter-miss.
    Пустой пул → "".
    """
    if not pool:
        return ""

    elos = [int(r.get("elo", DEFAULT_ELO)) for r in pool]
    lo, hi = min(elos), max(elos)
    if lo == hi:
        lo, hi = lo - 10, hi + 10
    pad = max(15.0, (hi - lo) * 0.08)
    lo, hi = lo - pad, hi + pad
    scale = build_elo_scale(elos)
    mean = sum(elos) / len(elos)

    row_h, bar_h = 30, 18
    top, bottom = 44, 30
    rank_x, name_x = 8, 52
    max_name = max(
        (max(len(str(r.get("name", ""))), len(str(r.get("caption", ""))))
         for r in pool),
        default=0,
    )
    name_w = max(150, min(360, int(max_name * 7.0)))
    elo_x = name_x + name_w + 14
    half_x = elo_x + 54
    plot_x0, plot_x1 = half_x + 16, width - 16
    height = top + row_h * len(rows) + bottom
    rows_bottom = top + row_h * len(rows)

    def x(value: float) -> float:
        return plot_x0 + (plot_x1 - plot_x0) * (value - lo) / (hi - lo)

    def clamp_x(value: float) -> float:
        return max(plot_x0, min(plot_x1, x(value)))

    parts: list[str] = []

    # Группы неразличимых мест — полосой по видимому фрагменту. Надписи над
    # строками нет: смысл признака объясняет легенда карточки, детали — тултип.
    groups: list[list[int]] = []
    for i, r in enumerate(rows):
        number = int(r.get("group") or 0)
        if not number:
            continue
        if groups and groups[-1][0] == number:
            groups[-1][2] = i
        else:
            groups.append([number, i, i])
    for _, start, end in groups:
        band_y = top + start * row_h + 2
        band_h = row_h * (end - start + 1) - 4
        full = bool(rows[start].get("group_full", True))
        size = int(rows[start].get("group_size") or (end - start + 1))
        visible = end - start + 1
        tip = (
            f"Группа неразличимых мест: {size} "
            f"{plural_ru(size, 'модель', 'модели', 'моделей')} — интервалы "
            f"соседей перекрываются, точный порядок статистически не различим"
        )
        if not full:
            tip += (
                f"; на этой странице видно {visible}, продолжение — "
                f"на соседней странице"
            )
        parts.append(
            f'<rect x="4" y="{band_y}" width="{width - 8}" height="{band_h}" '
            f'rx="6" class="interval-group-band">'
            f"<title>{html.escape(tip)}</title></rect>"
        )

    step = 50 if hi - lo <= 400 else 100
    tick = math.ceil(lo / step) * step
    while tick <= hi:
        gx = x(tick)
        parts.append(
            f'<line x1="{gx:.1f}" y1="{top - 14}" x2="{gx:.1f}" '
            f'y2="{rows_bottom}" class="chart-grid"/>'
        )
        parts.append(
            f'<text x="{gx:.1f}" y="20" text-anchor="middle" '
            f'class="chart-tick">{tick}</text>'
        )
        tick += step

    for value, cls, tip in (
        (DEFAULT_ELO, "dist-line-start", "старт: 1200"),
        (mean, "dist-line-mean", f"среднее: {mean:.1f}"),
    ):
        gx = x(value)
        parts.append(
            f'<line x1="{gx:.1f}" y1="{top}" x2="{gx:.1f}" y2="{rows_bottom}" '
            f'class="{cls}"><title>{html.escape(tip)}</title></line>'
        )

    for i, r in enumerate(rows):
        cy = top + i * row_h + row_h / 2
        elo = int(r.get("elo", DEFAULT_ELO))
        mid = str(r.get("id", ""))
        name = html.escape(str(r.get("name", mid)))
        caption = str(r.get("caption", ""))
        grouped = bool(r.get("group"))
        rank = int(r.get("rank") or (i + 1))
        seg, frac = scale_segment(elo, scale)
        style = (
            f"--a:var(--dist-s{scale[seg][1]});"
            f"--b:var(--dist-s{scale[seg + 1][1]});"
            f"--p:{frac * 100:.1f}%"
        )
        cls = "dist-pt"
        if highlight:
            cls += " filter-hit" if r.get("hit") else " filter-miss"
        raw_name = str(r.get("name", mid))
        tip_name = f"{raw_name} ({caption})" if caption else raw_name
        tip = html.escape(
            f"{tip_name} · {elo} · игр: {r.get('games', 0)}"
        )
        if r.get("has_interval"):
            tip += f" · интервал {int(r['lo'])}–{int(r['hi'])}"
        else:
            tip += " · игр нет, интервал не определён"

        # градиентный бар: от минимума пула до ELO модели
        bar = (
            f'<rect x="{x(lo):.1f}" y="{cy - bar_h / 2:.1f}" '
            f'width="{max(1.0, x(elo) - x(lo)):.1f}" height="{bar_h}" rx="4" '
            f'class="{cls}" style="{style}">'
            f"<title>{tip}</title></rect>"
        )
        if mid:
            bar = (
                f'<a href="/model/{html.escape(mid)}" class="dist-link">{bar}</a>'
            )
        parts.append(bar)

        # интервал ±400/√игр — отрезком поверх бара
        if r.get("has_interval"):
            bx1, bx2 = clamp_x(int(r["lo"])), clamp_x(int(r["hi"]))
            parts.append(
                f'<line x1="{bx1:.1f}" y1="{cy:.1f}" x2="{bx2:.1f}" '
                f'y2="{cy:.1f}" class="interval-bar'
                f'{" interval-bar-grouped" if grouped else ""}">'
                f"<title>{html.escape(name)}: интервал "
                f"{int(r['lo'])}–{int(r['hi'])}</title>"
                f"</line>"
            )

        # У места в группе — подсказка: почему оно помечено «≈».
        rank_tip = (
            "<title>место не определено: интервалы соседей перекрываются, "
            "точный порядок статистически не различим</title>"
            if grouped else ""
        )
        parts.append(
            f'<text x="{rank_x}" y="{cy + 4}" class="interval-rank'
            f'{" interval-rank-grouped" if grouped else ""}">'
            f'{"≈" if grouped else ""}{rank}{rank_tip}</text>'
        )
        parts.append(
            f'<text x="{name_x}" y="{cy + 4}">'
            f'<a href="/model/{html.escape(mid)}" class="dist-name">'
            f"{name}<title>{tip}</title></a></text>"
        )
        if caption:
            parts.append(
                f'<text x="{name_x}" y="{cy + 15}" class="dist-caption">'
                f"{html.escape(caption)}</text>"
            )
        parts.append(
            f'<text x="{elo_x}" y="{cy + 4}" text-anchor="end" '
            f'class="interval-elo">{elo}</text>'
        )
        half = "—" if not r.get("has_interval") else f"±{int(r['half'])}"
        parts.append(
            f'<text x="{half_x}" y="{cy + 4}" text-anchor="end" '
            f'class="interval-gap">{half}</text>'
        )
        parts.append(
            f'<circle cx="{x(elo):.1f}" cy="{cy:.1f}" r="4" class="chart-dot'
            f'{" interval-dot-grouped" if grouped else ""}">'
            f"<title>{tip}</title></circle>"
        )

    visible_groups = len({int(r.get("group") or 0) for r in rows if r.get("group")})
    return _wrap_chart(
        f'<svg viewBox="0 0 {width} {height}" class="chart chart-rating" '
        f'role="img" aria-label="Рейтинг: {len(rows)} моделей, '
        f'групп неразличимых мест: {visible_groups}">'
        + "".join(parts)
        + "</svg>"
    )


# ─── Аналитика: динамика ELO (A2) ───────────────────────────────────

ELO_LINES_LIMIT = 10
ELO_LINES_DEFAULT = 5
ELO_PERIOD_DEFAULT = 90
ELO_LINE_CANDIDATES = 20
ELO_LINE_COLORS = (
    "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#a855f7",
    "#ec4899", "#14b8a6", "#f97316", "#8b949e", "#84cc16",
)


def _model_card(mid: str, info: dict) -> dict:
    """Карточка модели для списка выбора: id, имя, ELO, текст для поля."""
    name = str((info or {}).get("name") or mid)
    return {
        "id": mid,
        "name": name,
        "elo": int((info or {}).get("elo") or DEFAULT_ELO),
        # Список разделён запятыми — имя с запятой в список не годится.
        "token": name if "," not in name else mid,
    }


def _token_ok(token: str, mid: str, info: dict) -> dict:
    card = _model_card(mid, info)
    return {
        "raw": token,
        "status": "ok",
        "id": mid,
        "name": card["name"],
        "elo": card["elo"],
        "candidates": [card],
    }


def resolve_lines_token(token: str, models: dict) -> dict:
    """Разбор одного токена списка моделей.

    Правила в порядке строгости: `id` реестра → точное имя → однозначная
    подстрока имени → однозначная подстрока `id`. Совпадений несколько —
    статус `ambiguous` и список кандидатов; совпадений нет — `not-found`.
    Молчаливых отбрасываний нет: статус несёт вызывающий.
    """
    needle = token.casefold()
    for mid, info in models.items():
        if mid.casefold() == needle:
            return _token_ok(token, mid, info)
    for mid, info in models.items():
        if str(info.get("name") or "").casefold() == needle:
            return _token_ok(token, mid, info)
    pools = (
        [mid for mid, info in models.items()
         if needle in str(info.get("name") or "").casefold()],
        [mid for mid in models if needle in mid.casefold()],
    )
    for pool in pools:
        if not pool:
            continue
        if len(pool) == 1:
            return _token_ok(token, pool[0], models[pool[0]])
        ordered = sorted(pool, key=lambda m: (
            -int(models[m].get("elo") or DEFAULT_ELO), m,
        ))[:ELO_LINE_CANDIDATES]
        return {
            "raw": token,
            "status": "ambiguous",
            "id": "",
            "name": "",
            "elo": None,
            "candidates": [_model_card(mid, models[mid]) for mid in ordered],
        }
    return {
        "raw": token,
        "status": "not-found",
        "id": "",
        "name": "",
        "elo": None,
        "candidates": [],
    }


def resolve_lines(raw: str | None, models: dict) -> dict:
    """Разбор списка моделей карточки «Динамика ELO».

    Список — токены через запятую. Каждый токен получает статус (`ok`,
    `ambiguous`, `not-found`). Выбранные модели идут в порядке токенов,
    повторы схлопываются, лишние сверх ELO_LINES_LIMIT возвращаются
    отдельным списком `dropped`.

    Возвращает:
      raw        — исходный текст списка;
      ids        — выбранные id (не более ELO_LINES_LIMIT);
      tokens     — по записи на токен: {raw, status, id, name, elo,
                   candidates};
      chips      — ряд для карточки: model (выбранные модели) и problem
                   (неразобранные токены);
      dropped    — модели, не вошедшие в предел: [{id, name}];
      unresolved — неразобранные токены;
      field      — текст поля выбора.
    """
    text = str(raw or "")
    tokens = [
        resolve_lines_token(part.strip(), models)
        for part in text.split(",") if part.strip()
    ]

    ordered: list[str] = []
    seen: set[str] = set()
    for tok in tokens:
        if tok["status"] == "ok" and tok["id"] not in seen:
            seen.add(tok["id"])
            ordered.append(tok["id"])

    ids = ordered[:ELO_LINES_LIMIT]
    dropped = [
        {"id": mid, "name": str(models.get(mid, {}).get("name") or mid)}
        for mid in ordered[ELO_LINES_LIMIT:]
    ]
    unresolved = [tok for tok in tokens if tok["status"] != "ok"]
    selected = set(ids)

    # Поле выбора показывает имена выбранных моделей; если часть токенов не
    # разобралась — исходный текст: пользователь должен его поправить.
    names_mode = not unresolved
    chips: list[dict] = []
    used: set[str] = set()
    for tok in tokens:
        if tok["status"] == "ok":
            if tok["id"] in used or tok["id"] not in selected:
                continue
            used.add(tok["id"])
            chips.append({
                "kind": "model",
                "id": tok["id"],
                "name": tok["name"],
                "elo": tok["elo"],
                "raw": tok["name"] if names_mode else tok["raw"],
            })
        else:
            chips.append({
                "kind": "problem",
                "raw": tok["raw"],
                "status": tok["status"],
                "candidates": tok["candidates"],
            })

    if names_mode:
        field = ", ".join(
            _model_card(mid, models.get(mid, {}))["token"] for mid in ids
        )
    else:
        field = text

    return {
        "raw": text,
        "ids": ids,
        "tokens": tokens,
        "chips": chips,
        "dropped": dropped,
        "unresolved": unresolved,
        "field": field,
    }


def resolve_lines_default(models: dict,
                          limit: int = ELO_LINES_DEFAULT) -> dict:
    """Разбор для состояния по умолчанию: топ активных по ELO.

    Формат тот же, что у `resolve_lines`, — чтобы карточка рендерилась
    одним кодом в обоих режимах.
    """
    ids = default_line_ids(models, limit)
    chips = [
        {
            "kind": "model",
            "id": mid,
            "name": str(models.get(mid, {}).get("name") or mid),
            "elo": int(models.get(mid, {}).get("elo") or DEFAULT_ELO),
            "raw": _model_card(mid, models.get(mid, {}))["token"],
        }
        for mid in ids
    ]
    return {
        "raw": "",
        "ids": ids,
        "tokens": [],
        "chips": chips,
        "dropped": [],
        "unresolved": [],
        "field": ", ".join(chip["raw"] for chip in chips),
    }


def lines_warnings(result: dict) -> list[str]:
    """Предупреждения разбора списка моделей — для вывода под полем."""
    warnings: list[str] = []
    for tok in result.get("unresolved", []):
        if tok["status"] == "not-found":
            warnings.append(f"не найдено: «{tok['raw']}»")
            continue
        candidates = tok.get("candidates") or []
        names = ", ".join(c["name"] for c in candidates[:5])
        tail = "…" if len(candidates) > 5 else ""
        warnings.append(
            f"неоднозначно: «{tok['raw']}» — подходит {len(candidates)} "
            f"{plural_ru(len(candidates), 'модель', 'модели', 'моделей')}: "
            f"{names}{tail}"
        )
    dropped = result.get("dropped") or []
    if dropped:
        names = ", ".join(m["name"] for m in dropped)
        warnings.append(
            f"не вошло (предел {ELO_LINES_LIMIT} моделей): {names}"
        )
    return warnings


def parse_lines_param(raw: str | None, models: dict) -> list[str]:
    """Разбор `lines` блока A2: выбранные id в порядке токенов.

    Порядок ввода сохраняется; лишние сверх ELO_LINES_LIMIT отбрасываются
    (их перечень — в `resolve_lines(...)["dropped"]`).
    """
    return resolve_lines(raw, models)["ids"]


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
    """Линии A2: дневные точки (индекс дня, ELO после) по выбранным моделям.

    Ось X — календарные дни окна периода. Окно отсчитывается от максимальной
    валидной даты истории (включительно) и не зависит от `selected`:
    `days=30/90` — последние N дней, но не раньше первой даты истории;
    `days=None` — вся история. На модель и день — одна точка: ELO после
    последнего матча дня по `seq` (с непустым `after`). Матчи без валидной
    даты пропускаются. Возвращает {"window", "day_count", "series",
    "match_counts", "match_count"}.
    """
    series: dict[str, list[tuple[int, int]]] = {mid: [] for mid in selected}
    match_counts = {mid: 0 for mid in selected}
    ordered = sorted(elo_history or [], key=lambda e: e.get("seq", 0))

    dated: list[tuple[dict, date]] = []
    for e in ordered:
        raw_day = day_of(e)
        try:
            day = date.fromisoformat(raw_day[:10])
        except (TypeError, ValueError):
            continue
        dated.append((e, day))
    if not dated:
        return {
            "window": (),
            "day_count": 0,
            "series": series,
            "match_counts": match_counts,
            "match_count": 0,
        }

    min_day = min(day for _, day in dated)
    max_day = max(day for _, day in dated)
    start = min_day
    if days is not None:
        start = max(min_day, max_day - timedelta(days=days - 1))
    day_count = (max_day - start).days + 1

    daily: dict[str, dict[date, int]] = {mid: {} for mid in selected}
    match_count = 0
    for e, day in dated:
        if day < start or day > max_day:
            continue
        a_id = str(e.get("model_a_id") or "")
        b_id = str(e.get("model_b_id") or "")
        if a_id not in series and b_id not in series:
            continue
        match_count += 1
        for side, elo_key in (
            ("model_a_id", "elo_a"), ("model_b_id", "elo_b"),
        ):
            mid = str(e.get(side) or "")
            if mid not in series:
                continue
            match_counts[mid] += 1
            after = (e.get(elo_key) or {}).get("after")
            if after is not None:
                daily[mid][day] = int(after)

    for mid, points_by_day in daily.items():
        series[mid] = sorted(
            ((day - start).days, after)
            for day, after in points_by_day.items()
        )
    return {
        "window": (start.isoformat(), max_day.isoformat()),
        "day_count": day_count,
        "series": series,
        "match_counts": match_counts,
        "match_count": match_count,
    }


def build_elo_multiline_svg(
    series: list[dict],
    window: tuple[str, str] | None,
    match_count: int = 0,
    colors: tuple[str, ...] = ELO_LINE_COLORS,
    width: int = 860,
    height: int = 260,
) -> str:
    """SVG блока A2: дневные ломаные выбранных моделей.

    series — [{"id", "name", "points": [(day_index, elo)], "matches": n}]
    в порядке легенды; `window` — (первый день, последний день) окна.
    Ось X календарная: `day_index` — номер дня от начала окна. Ось Y
    включает опорную линию 1200; на оси до пяти равномерных дат.
    Серия с непустым id кликабельна: линия оборачивается ссылкой
    на `/model/<id>` (невидимый хит-слой stroke-width 12).
    Нет точек у всех серий или пустое окно → "" (шаблон показывает
    пустое состояние).
    """
    if not window or len(window) != 2:
        return ""
    try:
        start = date.fromisoformat(str(window[0])[:10])
        end = date.fromisoformat(str(window[1])[:10])
    except (TypeError, ValueError):
        return ""
    if end < start:
        return ""
    day_count = (end - start).days + 1

    drawn: list[dict] = []
    for item in series:
        points = sorted(
            (int(px), int(pv))
            for px, pv in (item.get("points") or [])
            if 0 <= int(px) < day_count
        )
        if points:
            drawn.append({**item, "points": points})
    if not drawn:
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
        if day_count <= 1:
            return left + plot_w / 2
        return left + plot_w * i / (day_count - 1)

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

    # До пяти равномерных дат: начало, четверти, конец. Для короткого
    # окна дубликаты индексов отбрасываются.
    if day_count <= 1:
        tick_indexes = [0]
    else:
        tick_indexes = sorted({
            round((day_count - 1) * step / 4) for step in range(5)
        })
    axis = ""
    for idx in tick_indexes:
        tick_day = start + timedelta(days=idx)
        label = _fmt_axis_date(tick_day.isoformat())
        if day_count == 1:
            anchor = "middle"
        elif idx == 0:
            anchor = "start"
        elif idx == day_count - 1:
            anchor = "end"
        else:
            anchor = "middle"
        axis += (
            f'<text x="{x(idx):.1f}" y="{height - 8}" '
            f'text-anchor="{anchor}" class="chart-tick">'
            f"{html.escape(label)}</text>"
        )

    total_matches = int(match_count or 0)
    if not total_matches:
        total_matches = sum(
            int(s.get("matches", len(s["points"]))) for s in drawn
        )

    lines = ""
    for index, item in enumerate(drawn):
        color = colors[index % len(colors)]
        points = item["points"]
        mid = str(item.get("id", ""))
        name = html.escape(str(item.get("name", item.get("id", ""))))
        matches = int(item.get("matches", len(points)))
        last_day = start + timedelta(days=points[-1][0])
        last_date = _fmt_axis_date(last_day.isoformat())
        title = (
            f"{name}: {matches} "
            f"{plural_ru(matches, 'матч', 'матча', 'матчей')}, "
            f"{len(points)} {plural_ru(len(points), 'день', 'дня', 'дней')}, "
            f"последний матч {last_date}, Elo {points[-1][1]}"
        )
        poly = " ".join(f"{x(px):.1f},{y(pv):.1f}" for px, pv in points)
        end_x, end_y = x(points[-1][0]), y(points[-1][1])
        visible = (
            f'<polyline points="{poly}" class="chart-line-multi" fill="none" '
            f'stroke="{color}"><title>{title}</title></polyline>'
        )
        end_dot = (
            f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="3.5" '
            f'fill="{color}"><title>{title}</title></circle>'
        )
        if mid:
            hit = (
                f'<polyline points="{poly}" class="chart-line-hit" fill="none" '
                f'stroke-linecap="round">'
                f"<title>{title} — открыть профиль</title></polyline>"
            )
            lines += (
                f'<a href="/model/{html.escape(mid)}">{visible}{hit}{end_dot}</a>'
            )
        else:
            lines += visible + end_dot

    return _wrap_chart(
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="Динамика ELO: линий {len(drawn)}, '
        f'матчей {total_matches}, дней {day_count}">'
        f"{grid}{baseline}{lines}{axis}</svg>"
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

