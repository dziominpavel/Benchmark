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

sys.path.insert(0, str(REPO_ROOT / "tools"))
from render_helpers import format_elo_history, render_history_html

HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ELO Benchmark — Leaderboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
  .page { width: 100%; max-width: 1400px; margin: 0 auto; padding: 24px; }
  h1 { margin-bottom: 24px; color: #1a1a2e; }
  .stats { color: #666; font-size: 0.9em; margin-bottom: 12px; }
  .controls { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
  .controls label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #1a1a2e; color: white; font-weight: 600; }
  tr:hover { background: #f0f4ff; }
  .archived { color: #999; font-style: italic; }
  .rank { font-weight: bold; color: #666; }
  .elo { font-weight: bold; font-size: 1.1em; }

  .content-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    grid-template-areas: "rating sidebar" "history .";
    row-gap: 16px;
    column-gap: 24px;
    align-items: stretch;
  }
  .main-column { display: contents; }
  .rating-card { grid-area: rating; }
  .history-details { grid-area: history; }
  .sidebar {
    grid-area: sidebar;
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 100%;
    min-width: 0;
  }
  .card { background: white; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .rating-card { background: white; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .note-card { background: white; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .note-card h2 { font-size: 1.1rem; margin-bottom: 10px; color: #1a1a2e; }

  .table-wrap { overflow-x: auto; }
  .table-wrap table { width: 100%; min-width: 0; }
  th, td { white-space: nowrap; }
  .model-cell, .model-cell .edit-link { white-space: normal; }
  .model-cell .status-pill { white-space: nowrap; }
  td:first-child, th:first-child { padding-left: 16px; }
  td:last-child, th:last-child { padding-right: 16px; }
  .note-card p { margin-bottom: 8px; font-size: 0.9rem; color: #555; }
  .note-card code { background: #f0f0f0; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; }
  .note-card a { color: #1a1a2e; text-decoration: none; font-weight: 600; }
  .note-card a:hover { text-decoration: underline; }

  .history-details summary {
    list-style: none;
    cursor: pointer;
    font-size: 1.15rem;
    font-weight: 600;
    color: #1a1a2e;
    padding: 16px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 20px;
  }
  .history-details summary::-webkit-details-marker { display: none; }
  .history-details summary::after { content: '▼'; font-size: 0.8rem; color: #666; }
  .history-details[open] summary::after { transform: rotate(180deg); }
  .history-count { color: #999; font-size: 0.85rem; font-weight: 400; margin-left: 8px; }
  .history-box { background: white; padding: 12px 16px; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-top: -8px; padding-top: 20px; }
  .history-page { display: none; }
  .history-page.active { display: block; }
  .history-item { border-bottom: 1px solid #eee; padding: 8px 0; display: flex; gap: 12px; font-size: 0.95em; }
  .history-item:last-child { border-bottom: none; }
  .history-model { font-weight: 600; min-width: 160px; }
  .history-elo { font-weight: 600; color: #333; }
  .history-delta-up { color: #2e7d32; font-weight: 600; }
  .history-delta-down { color: #c62828; font-weight: 600; }
  .history-delta-neutral { color: #999; }
  .history-date { color: #999; font-size: 0.85em; margin-left: auto; }
  .pagination { display: flex; justify-content: center; gap: 6px; margin-top: 12px; flex-wrap: wrap; }
  .pagination a {
    display: inline-flex; justify-content: center; align-items: center;
    min-width: 28px; height: 28px; padding: 0 6px;
    border-radius: 4px; background: #f0f0f0; color: #333;
    text-decoration: none; font-size: 0.85rem; font-weight: 600;
  }
  .pagination a:hover { background: #e0e0e0; }
  .pagination a.current { background: #1a1a2e; color: white; }

  @media (max-width: 900px) {
    .content-grid {
      grid-template-columns: 1fr;
      grid-template-areas: "rating" "history" "sidebar";
    }
    .page { padding: 16px; }
  }
</style>
</head>
<body>
<div class="page">
  <h1>ELO Benchmark — Leaderboard</h1>

  <div class="controls">
    <div class="stats">
      Всего моделей: {models_count} · Вердиктов: {matchups_count} · Обновлено: {updated}
    </div>
    <label>
      <input type="checkbox" id="showArchived" onchange="toggleArchived()">
      Показывать архивные
    </label>
  </div>

  <div class="content-grid">
    <div class="main-column">
      <div class="rating-card">
        <div class="table-wrap">
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
        </div>
      </div>

      <details class="history-details">
        <summary>История <span class="history-count">({history_total})</span></summary>
        <div class="history-box">
          <div id="historyPagesContainer">
            {history_pages_html}
          </div>
          {history_pagination_html}
        </div>
      </details>
    </div>

    <div class="sidebar">
      <div class="note-card">
        <h2>Запись вердиктов</h2>
        <p>Статичный экспорт. Для записи вердиктов и просмотра рекомендаций запустите сервер:</p>
        <code>python tools/server.py</code>
        <p style="margin-top:10px;"><a href="http://localhost:5000" target="_blank">Открыть сервер</a></p>
      </div>
    </div>
  </div>
</div>

<script>
function toggleArchived() {
  const show = document.getElementById('showArchived').checked;
  document.querySelectorAll('#leaderboard tbody tr').forEach(row => {
    if (row.dataset.archived === 'true') {
      row.style.display = show ? '' : 'none';
    }
  });
}

function showHistoryPage(page) {
  document.querySelectorAll('.history-page').forEach(el => {
    el.classList.toggle('active', parseInt(el.dataset.page) === page);
  });
  document.querySelectorAll('.history-page-btn').forEach(btn => {
    btn.classList.toggle('current', parseInt(btn.dataset.page) === page);
  });
  return false;
}

document.addEventListener('DOMContentLoaded', () => {
  toggleArchived();
  showHistoryPage(1);
});
</script>
</body>
</html>
"""

ROW_TEMPLATE = '    <tr class="{archived_class}" data-archived="{is_archived}">\n      <td class="rank">{rank}</td>\n      <td class="model-cell">{name}</td>\n      <td>{provider}</td>\n      <td class="elo">{elo}</td>\n      <td>{wins}</td>\n      <td>{losses}</td>\n      <td>{draws}</td>\n      <td>{games}</td>\n    </tr>'


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
        )

    # История ELO: пагинация по 20 записей
    name_map = {mid: m.get("name", mid) for mid, m in models.items()}
    raw_history = list(reversed(data.get("elo_history", [])))
    page_size = 20
    total_history = len(raw_history)
    history_pages = (total_history + page_size - 1) // page_size if total_history else 1
    history_pages_html = ""
    if total_history:
        for p in range(1, history_pages + 1):
            start = (p - 1) * page_size
            end = start + page_size
            page_items = render_history_html(
                format_elo_history(raw_history[start:end], name_map)
            )
            active = ' active' if p == 1 else ''
            history_pages_html += f'    <div class="history-page{active}" data-page="{p}">\n{page_items}\n    </div>\n'
    else:
        history_pages_html = '    <p style="color:#999;padding:8px 0;">Нет истории</p>\n'

    if history_pages > 1:
        pagination = ['    <div class="pagination">']
        for p in range(1, history_pages + 1):
            current = ' current' if p == 1 else ''
            pagination.append(
                f'      <a href="#" class="history-page-btn{current}" data-page="{p}" onclick="return showHistoryPage({p});">{p}</a>'
            )
        pagination.append('    </div>')
        history_pagination_html = "\n".join(pagination)
    else:
        history_pagination_html = ""

    html = (
        HTML
        .replace("{models_count}", str(len(models)))
        .replace("{matchups_count}", str(len(data.get("matchups_index", []))))
        .replace("{updated}", data.get("updated", ""))
        .replace("{rows}", "\n".join(rows))
        .replace("{history_total}", str(total_history))
        .replace("{history_pages_html}", history_pages_html)
        .replace("{history_pagination_html}", history_pagination_html)
    )

    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"leaderboard.html создан ({OUTPUT_PATH}).")
    print(f"Моделей: {len(models)}, вердиктов: {len(data.get('matchups_index', []))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
