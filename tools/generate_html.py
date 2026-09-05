#!/usr/bin/env python3
"""
generate_html.py — генерирует статичный leaderboard.html из index.json.

Использование:
    python tools/generate_html.py

Создаёт leaderboard.html в корне репозитория — можно открыть в браузере
напрямую (file://) без запуска сервера. Только чтение (без формы записи).

Зависимости: только stdlib.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = REPO_ROOT / "index.json"
OUTPUT_PATH = REPO_ROOT / "leaderboard.html"

DEFAULT_ELO = 1200

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ELO Benchmark — Leaderboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 20px; max-width: 1000px; margin: 0 auto; }
  h1 { margin-bottom: 10px; color: #1a1a2e; }
  .stats { color: #666; font-size: 0.9em; margin-bottom: 20px; }
  .controls { margin-bottom: 20px; }
  .controls label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #1a1a2e; color: white; font-weight: 600; }
  tr:hover { background: #f0f4ff; }
  .archived { color: #999; font-style: italic; }
  .rank { font-weight: bold; color: #666; }
  .elo { font-weight: bold; font-size: 1.1em; }
  .elo-high { color: #2e7d32; }
  .elo-mid { color: #f57f17; }
  .elo-low { color: #c62828; }
  .note { margin-top: 20px; color: #999; font-size: 0.85em; }
  .history-item { border-bottom: 1px solid #eee; padding: 8px 0; display: flex; gap: 12px; font-size: 0.95em; }
  .history-item:last-child { border-bottom: none; }
  .history-model { font-weight: 600; min-width: 160px; }
  .history-elo { font-weight: 600; color: #333; }
  .history-delta-up { color: #2e7d32; font-weight: 600; }
  .history-delta-down { color: #c62828; font-weight: 600; }
  .history-delta-neutral { color: #999; }
  .history-date { color: #999; font-size: 0.85em; margin-left: auto; }
</style>
</head>
<body>
<h1>ELO Benchmark — Leaderboard</h1>
<div class="stats">
  Всего моделей: {models_count} · Вердиктов: {matchups_count} · Обновлено: {updated}
</div>
<div class="controls">
  <label>
    <input type="checkbox" id="showArchived" onchange="toggleArchived()">
    Показывать архивные
  </label>
</div>
<table id="leaderboard">
  <thead>
    <tr>
      <th>#</th>
      <th>Модель</th>
      <th>Провайдер</th>
      <th>ELO</th>
      <th>W</th>
      <th>L</th>
      <th>D</th>
      <th>Игры</th>
    </tr>
  </thead>
  <tbody>
{rows}
  </tbody>
</table>

<h2 style="margin-top: 28px;">История</h2>
<div id="history" style="background: white; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px;">
{history}
</div>

<div class="note">Статичный экспорт. Для записи вердиктов запустите <code>python tools/server.py</code>.</div>
<script>
function toggleArchived() {{
  const show = document.getElementById('showArchived').checked;
  document.querySelectorAll('#leaderboard tbody tr').forEach(row => {
    if (row.dataset.archived === 'true') {
      row.style.display = show ? '' : 'none';
    }
  });
}
document.addEventListener('DOMContentLoaded', toggleArchived);
</script>
</body>
</html>
"""

ROW_TEMPLATE = '    <tr class="{archived_class}" data-archived="{is_archived}">\n      <td class="rank">{rank}</td>\n      <td>{name}</td>\n      <td>{provider}</td>\n      <td class="elo {elo_class}">{elo}</td>\n      <td>{wins}</td>\n      <td>{losses}</td>\n      <td>{draws}</td>\n      <td>{games}</td>\n    </tr>'

HISTORY_ITEM_TEMPLATE = '    <div class="history-item">\n      <span class="history-model">{model_name} vs {opponent_name}</span>\n      <span class="history-elo">{elo_before} → {elo}</span>\n      <span class="{delta_class}">{delta}</span>\n      <span class="history-date">{date}</span>\n    </div>'


def main() -> int:
    if not INDEX_PATH.exists():
        print(f"index.json не найден. Запустите `python tools/elo.py` сначала.", file=sys.stderr)
        return 1

    data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    models = data.get("models", {})

    # Сортировка по ELO (убывание)
    models_sorted = sorted(
        models.values(),
        key=lambda m: m.get("elo", DEFAULT_ELO),
        reverse=True,
    )

    rows = []
    for i, m in enumerate(models_sorted, 1):
        elo = m.get("elo", DEFAULT_ELO)
        is_archived = m.get("status", "active") == "archived"
        elo_class = "elo-high" if elo >= 1300 else ("elo-mid" if elo >= 1150 else "elo-low")
        rows.append(ROW_TEMPLATE
            .replace("{rank}", str(i))
            .replace("{name}", m.get("name", ""))
            .replace("{provider}", m.get("provider", ""))
            .replace("{elo}", str(elo))
            .replace("{wins}", str(m.get("wins", 0)))
            .replace("{losses}", str(m.get("losses", 0)))
            .replace("{draws}", str(m.get("draws", 0)))
            .replace("{games}", str(m.get("games", 0)))
            .replace("{is_archived}", "true" if is_archived else "false")
            .replace("{archived_class}", "archived" if is_archived else "")
            .replace("{elo_class}", elo_class)
        )

    # История ELO
    name_map = {mid: m.get("name", mid) for mid, m in models.items()}
    raw_history = data.get("elo_history", [])
    history_items = []
    for item in reversed(raw_history[-20:]):
        mid = item.get("model", "")
        opponent = item.get("opponent", "")
        elo = item.get("elo", DEFAULT_ELO)
        elo_before = item.get("elo_before", DEFAULT_ELO)
        delta = item.get("delta", 0)
        if delta > 0:
            delta_str = f"+{delta}"
            delta_class = "history-delta-up"
        elif delta < 0:
            delta_str = str(delta)
            delta_class = "history-delta-down"
        else:
            delta_str = "±0"
            delta_class = "history-delta-neutral"
        date = (item.get("recorded_at") or item.get("date", ""))[:19].replace("T", " ")
        history_items.append(
            HISTORY_ITEM_TEMPLATE
            .replace("{model_name}", name_map.get(mid, mid))
            .replace("{opponent_name}", name_map.get(opponent, opponent))
            .replace("{elo}", str(elo))
            .replace("{elo_before}", str(elo_before))
            .replace("{delta}", delta_str)
            .replace("{delta_class}", delta_class)
            .replace("{date}", date)
        )

    html = (
        HTML
        .replace("{models_count}", str(len(models)))
        .replace("{matchups_count}", str(len(data.get("matchups_index", []))))
        .replace("{updated}", data.get("updated", ""))
        .replace("{rows}", "\n".join(rows))
        .replace("{history}", "\n".join(history_items) if history_items else '<p style="color:#999;padding:8px 0;">Нет истории</p>')
    )

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"leaderboard.html создан ({OUTPUT_PATH}).")
    print(f"Моделей: {len(models)}, вердиктов: {len(data.get('matchups_index', []))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
