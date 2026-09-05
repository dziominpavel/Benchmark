#!/usr/bin/env python3
"""render_helpers.py — общие helpers для рендеринга leaderboard и истории.

Используются tools/server.py и tools/generate_html.py.
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


def render_history_html(items: list[dict]) -> str:
    """Рендерит историю в HTML-строку для generate_html.py."""
    if not items:
        return '<p style="color:#999;padding:8px 0;">Нет истории</p>'

    lines = []
    for item in items:
        lines.append(
            '    <div class="history-item">\n'
            f'      <span class="history-model">{item["model_a_name"]} vs {item["model_b_name"]}</span>\n'
            f'      <span class="history-elo">{item["elo_a_before"]} → {item["elo_a_after"]}</span>\n'
            f'      <span class="{item["elo_a_delta_class"]}">{item["elo_a_delta_str"]}</span>\n'
            f'      <span class="history-elo">{item["elo_b_before"]} → {item["elo_b_after"]}</span>\n'
            f'      <span class="{item["elo_b_delta_class"]}">{item["elo_b_delta_str"]}</span>\n'
            f'      <span class="history-date">{item["date_str"]}</span>\n'
            '    </div>'
        )
    return "\n".join(lines)
