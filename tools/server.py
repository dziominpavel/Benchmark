#!/usr/bin/env python3
"""
server.py — локальный веб-сервер для бенчмарка LLM-моделей.

Предоставляет:
  - Leaderboard (таблица ELO-рейтинга)
  - Форму записи вердикта (попарное сравнение: A vs B → победитель)
  - Отдельную страницу добавления модели (одно поле — название)
  - Историю изменений рейтинга

Запуск:
    python tools/server.py
    → http://localhost:5000

Зависимости: Flask, PyYAML (опц., для models.yaml).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Добавляем tools/ в path для импорта elo.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import (
    generate_index, save_index, load_models_yaml, load_matchups,
    is_index_stale, record_verdict, resolve_matchup_models,
    DEFAULT_ELO, REPO_ROOT,
)

from render_helpers import format_elo_history

from register_model import parse_existing, format_model

from flask import Flask, request, redirect, url_for, render_template_string

app = Flask(__name__)

ANSWERS_DIR = REPO_ROOT / "answers"
MATCHUPS_DIR = REPO_ROOT / "matchups"
TASKS_DIR = REPO_ROOT / "tasks"

DEFAULT_TASK = "general"


# ─── Helpers ────────────────────────────────────────────────────────


def ensure_index() -> dict:
    """Загружает index.json, пересчитывает если устарел."""
    if is_index_stale():
        data = generate_index()
        save_index(data)
        return data
    return json.loads((REPO_ROOT / "index.json").read_text(encoding="utf-8"))


def slugify(name: str, existing_ids: list[str]) -> str:
    """Превращает имя модели в slug. Если пусто — model-N. Если занят — суффикс."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        slug = f"model-{len(existing_ids) + 1}"
    base = slug
    suffix = 2
    while slug in existing_ids:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def get_model_name_map() -> dict[str, str]:
    """Возвращает {id: name} из models.yaml."""
    models = load_models_yaml()
    return {m["id"]: m.get("name", m["id"]) for m in models}


def get_all_matchup_pairs() -> set[frozenset[str]]:
    """Возвращает множество всех уже сравнённых пар (frozenset{id_a, id_b}).

    Использует resolved ids (model_a_id/model_b_id) и пропускает
    tombstone- и аннулированные вердикты.
    """
    model_ids = {m["id"] for m in load_models_yaml()}
    pairs = set()
    if not MATCHUPS_DIR.exists():
        return pairs
    matchups = load_matchups()
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
    for mu in matchups:
        if mu.get("void_of"):
            continue
        if mu.get("_matchup_id") in voided:
            continue
        a, b = resolve_matchup_models(mu, model_ids)
        if a and b:
            pairs.add(frozenset({a, b}))
    return pairs


def is_model_active(model: dict) -> bool:
    """Проверяет, что модель не заархивирована."""
    return model.get("status", "active") != "archived"


def update_model(model_id: str, name: str, status: str) -> bool:
    """Редактирует name и status модели в models.yaml и пересчитывает index."""
    models_path = REPO_ROOT / "models.yaml"
    if not models_path.exists():
        return False

    text = models_path.read_text(encoding="utf-8")
    models, preamble = parse_existing(text)

    found = False
    for m in models:
        if m["id"] == model_id:
            m["name"] = name
            m["status"] = status
            found = True
            break

    if not found:
        return False

    models.sort(key=lambda m: m["id"])

    out = preamble.rstrip() + "\n\nmodels:\n"
    for m in models:
        out += format_model(m) + "\n"

    models_path.write_text(out, encoding="utf-8")

    index_data = generate_index()
    save_index(index_data)
    return True


def get_recommendations(index_data: dict, top_n: int = 3) -> list[dict]:
    """Рекомендует пары моделей для следующего прогона.

    Алгоритм (двухуровневый):
    1. Берём все пары моделей из index.json
    2. Исключаем пары, которые уже сравнивались
    3. Оставшиеся раскладываем по тирам калибровки (по min_games —
       числу игр менее игранной модели в паре):
       - тир 0: min_games == 0 (новая модель, ещё не играла)
       - тир 1: min_games < 3 (мало игр, нужна калибровка)
       - тир 2: остальные
    4. Внутри тира сортируем по близости ELO (меньше elo_diff — выше):
       самый равный бой в тире идёт первым
    5. Возвращаем top_n (тир 0 всегда выше любого тира 1 и 2)

    Возвращает список dict: {model_a, model_b, name_a, name_b, elo_a, elo_b, reason}
    """
    models = index_data.get("models", {})
    name_map = get_model_name_map()

    # Только active-модели с данными из index
    model_ids = sorted(
        mid for mid, info in models.items() if is_model_active(info)
    )
    if len(model_ids) < 2:
        return []

    # ELO и игры из index
    elo_map = {mid: models[mid].get("elo", DEFAULT_ELO) for mid in model_ids}
    games_map = {mid: models[mid].get("games", 0) for mid in model_ids}

    compared = get_all_matchup_pairs()

    candidates = []
    for i in range(len(model_ids)):
        for j in range(i + 1, len(model_ids)):
            a, b = model_ids[i], model_ids[j]
            pair_key = frozenset({a, b})
            if pair_key in compared:
                continue

            elo_a = elo_map[a]
            elo_b = elo_map[b]
            elo_diff = abs(elo_a - elo_b)
            min_games = min(games_map[a], games_map[b])

            # Тир калибровки: новая модель всегда выше калибрующейся,
            # калибрующаяся — выше сыгранных. Внутри тира — близость ELO.
            if min_games == 0:
                tier = 0
                reason = "новая модель, ещё не играла"
            elif min_games < 3:
                tier = 1
                reason = f"мало игр ({min_games}), нужна калибровка"
            elif elo_diff < 50:
                tier = 2
                reason = f"близкий рейтинг (разница {elo_diff})"
            elif elo_diff < 150:
                tier = 2
                reason = f"рейтинг различается умеренно (Δ{elo_diff})"
            else:
                tier = 2
                reason = f"разный уровень (Δ{elo_diff}) — проверить апсет"

            # score = близость ELO: монотонно убывает с ростом diff,
            # внутри тира больший score идёт первым
            closeness = 1.0 / (1.0 + elo_diff / 100.0)

            candidates.append({
                "model_a": a,
                "model_b": b,
                "name_a": name_map.get(a, a),
                "name_b": name_map.get(b, b),
                "elo_a": elo_a,
                "elo_b": elo_b,
                "elo_diff": elo_diff,
                "reason": reason,
                "tier": tier,
                "score": closeness,
            })

    candidates.sort(key=lambda c: (c["tier"], -c["score"]))
    return candidates[:top_n]


# ─── HTML: shared CSS ───────────────────────────────────────────────

CSS = """
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    background: #0f172a;
    color: #e2e8f0;
    line-height: 1.5;
  }
  .page {
    width: 100%;
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
  }
  .header h1 {
    font-size: 1.6rem;
    color: #f1f5f9;
    font-weight: 700;
  }
  .btn {
    display: inline-block;
    padding: 10px 22px;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    text-decoration: none;
    transition: background 0.15s;
  }
  .btn-primary { background: #6366f1; color: white; }
  .btn-primary:hover { background: #818cf8; }
  .btn-secondary { background: #334155; color: #cbd5e1; }
  .btn-secondary:hover { background: #475569; }
  .btn-win { background: #10b981; color: white; }
  .btn-win:hover { background: #34d399; }
  .btn-lose { background: #ef4444; color: white; }
  .btn-lose:hover { background: #f87171; }
  .btn-draw { background: #475569; color: #e2e8f0; }
  .btn-draw:hover { background: #64748b; }
  .btn:disabled { background: #1e293b; color: #475569; cursor: not-allowed; }
  .card {
    background: #1e293b;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    border: 1px solid #334155;
  }
  .card h2 {
    font-size: 1.15rem;
    color: #f1f5f9;
    margin-bottom: 16px;
    font-weight: 600;
  }
  .stats {
    color: #64748b;
    font-size: 0.85rem;
    margin-bottom: 12px;
  }
  .controls {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 24px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th, td {
    padding: 12px 14px;
    text-align: left;
    border-bottom: 1px solid #334155;
  }
  th {
    font-size: 0.8rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  tbody tr:hover { background: #334155; }
  .rank { color: #64748b; font-weight: 600; }
  .wld { font-weight: 600; }
  .w { color: #34d399; }
  .l { color: #f87171; }
  .d { color: #94a3b8; }
  .form-group { margin-bottom: 16px; }
  .form-group label {
    display: block;
    font-size: 0.85rem;
    font-weight: 600;
    color: #94a3b8;
    margin-bottom: 6px;
  }
  .form-group select, .form-group input[type="text"] {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #475569;
    border-radius: 8px;
    font-size: 1rem;
    color: #e2e8f0;
    background: #0f172a;
  }
  .form-group select:focus, .form-group input[type="text"]:focus {
    outline: none;
    border-color: #6366f1;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.2);
  }
  .verdict-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
  }
  .verdict-actions {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }
  .verdict-actions .btn { flex: 1; min-width: 120px; text-align: center; padding: 12px; }
  .alert {
    padding: 12px 16px;
    border-radius: 8px;
    margin-bottom: 20px;
    font-size: 0.9rem;
    font-weight: 500;
  }
  .alert-error { background: #7f1d1d; color: #fca5a5; }
  .alert-success { background: #064e3b; color: #6ee7b7; }
  .history-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid #334155;
    font-size: 0.9rem;
  }
  .history-item:last-child { border-bottom: none; }
  .history-model { font-weight: 600; color: #e2e8f0; min-width: 140px; }
  .history-elo { font-weight: 700; color: #f1f5f9; white-space: nowrap; }
  .history-elo-arrow { color: #64748b; }
  .history-delta-up { color: #34d399; font-weight: 600; }
  .history-delta-down { color: #f87171; font-weight: 600; }
  .history-delta-neutral { color: #64748b; }
  .history-date { color: #64748b; font-size: 0.8rem; margin-left: auto; }
  .empty-state {
    text-align: center;
    padding: 40px 20px;
    color: #64748b;
    font-size: 0.95rem;
  }
  .add-form { max-width: 420px; }
  .back-link {
    display: inline-block;
    margin-bottom: 20px;
    color: #818cf8;
    text-decoration: none;
    font-size: 0.9rem;
    font-weight: 500;
  }
  .back-link:hover { text-decoration: underline; color: #a5b4fc; }
  .hint { color: #64748b; font-size: 0.85rem; margin-top: 8px; }
  .rec-card {
    background: #1e1b4b;
    border: 1px solid #4338ca;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 20px;
  }
  .rec-card h2 {
    font-size: 1.15rem;
    color: #a5b4fc;
    margin-bottom: 14px;
    font-weight: 600;
  }
  .rec-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 0 4px;
  }
  .rec-pair {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .rec-model {
    font-weight: 600;
    color: #e0e7ff;
  }
  .rec-elo {
    font-size: 0.8rem;
    color: #818cf8;
    font-weight: 600;
  }
  .rec-vs {
    color: #6366f1;
    font-size: 0.85rem;
    font-weight: 600;
  }
  .rec-reason {
    color: #a5b4fc;
    font-size: 0.82rem;
    margin-top: 4px;
  }
  .rec-info {
    flex: 1;
    min-width: 0;
  }
  .rec-btn {
    padding: 8px 18px;
    background: #6366f1;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .rec-btn:hover { background: #818cf8; }
  .rec-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 6px;
  }
  .rec-header h2 { margin-bottom: 0; }
  .rec-nav {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
  .rec-counter {
    font-size: 0.8rem;
    color: #818cf8;
    font-weight: 600;
    white-space: nowrap;
  }
  .rec-next {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    border: 1px solid #4338ca;
    background: #312e81;
    color: #e0e7ff;
    font-size: 1.1rem;
    font-weight: 700;
    cursor: pointer;
    line-height: 1;
    transition: background 0.15s;
  }
  .rec-next:hover { background: #4338ca; }
  .filter-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }
  .filter-bar label {
    font-size: 0.85rem;
    color: #94a3b8;
    font-weight: 600;
  }
  .filter-bar select {
    padding: 8px 12px;
    border: 1px solid #475569;
    border-radius: 8px;
    background: #0f172a;
    color: #e2e8f0;
    font-size: 0.95rem;
    cursor: pointer;
  }
  .edit-link {
    color: #e2e8f0;
    text-decoration: none;
    font-weight: 600;
  }
  .edit-link:hover { color: #818cf8; text-decoration: underline; }
  .status-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-left: 8px;
  }
  .status-active { background: #064e3b; color: #6ee7b7; }
  .status-archived { background: #475569; color: #cbd5e1; }
  tr.archived td { opacity: 0.6; }

  /* Content grid */
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
  .sidebar .card { margin-bottom: 0; }

  .table-wrap {
    overflow-x: auto;
    margin: 0 -24px;
    padding: 0 24px;
  }
  .table-wrap table {
    width: 100%;
    min-width: 0;
  }
  th, td {
    white-space: nowrap;
  }
  th:first-child, td:first-child {
    padding-left: 24px;
  }
  th:last-child, td:last-child {
    padding-right: 24px;
  }
  .model-cell, .model-cell .edit-link {
    white-space: normal;
  }
  .model-cell .status-pill {
    white-space: nowrap;
  }

  /* Collapsible history */
  .history-details summary {
    list-style: none;
    cursor: pointer;
    font-size: 1.15rem;
    font-weight: 600;
    color: #f1f5f9;
    padding: 24px;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .history-details summary::-webkit-details-marker { display: none; }
  .history-details summary::after {
    content: '▼';
    font-size: 0.8rem;
    color: #94a3b8;
    transition: transform 0.2s;
  }
  .history-details[open] summary::after { transform: rotate(180deg); }
  .history-details .card {
    border-top-left-radius: 0;
    border-top-right-radius: 0;
    border-top: none;
    margin-top: -1px;
  }
  .pagination {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 8px;
    margin-top: 16px;
    flex-wrap: wrap;
  }
  .pagination a, .pagination span {
    display: inline-flex;
    justify-content: center;
    align-items: center;
    min-width: 32px;
    height: 32px;
    padding: 0 8px;
    border-radius: 6px;
    background: #0f172a;
    border: 1px solid #475569;
    color: #e2e8f0;
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 600;
  }
  .pagination a:hover { background: #334155; }
  .pagination span.current { background: #6366f1; border-color: #6366f1; }
  .pagination .disabled { opacity: 0.4; pointer-events: none; }

  /* Responsive */
  @media (max-width: 900px) {
    .content-grid {
      grid-template-columns: 1fr;
      grid-template-areas: "rating" "history" "sidebar";
    }
    .page { padding: 16px; }
    .table-wrap { margin: 0 -16px; padding: 0 16px; }
    th:first-child, td:first-child { padding-left: 16px; }
    th:last-child, td:last-child { padding-right: 16px; }
  }
"""


# ─── HTML: Leaderboard page ─────────────────────────────────────────

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>ELO Benchmark</h1>
    <a href="/add" class="btn btn-primary">+ Добавить модель</a>
  </div>

  {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

  <div class="controls">
    <div class="stats">
      Моделей: {{ filtered_count }} из {{ models_count }} · Вердиктов: {{ matchups_count }} · Обновлено: {{ updated }}
    </div>
    <form method="GET" action="/" class="filter-bar">
      <label for="filter">Показывать</label>
      <select name="filter" id="filter" onchange="this.form.submit()">
        <option value="active" {% if filter == 'active' %}selected{% endif %}>Только активные</option>
        <option value="all" {% if filter == 'all' %}selected{% endif %}>Все</option>
        <option value="inactive" {% if filter == 'inactive' %}selected{% endif %}>Только неактивные</option>
      </select>
    </form>
  </div>

  <div class="content-grid">
    <div class="main-column">
      <div class="card rating-card">
        <h2>Рейтинг</h2>
        {% if models_sorted %}
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Модель</th>
                <th>ELO</th>
                <th>Побед</th>
                <th>Поражений</th>
                <th>Ничьих</th>
                <th>Всего</th>
              </tr>
            </thead>
            <tbody>
              {% for m in models_sorted %}
              <tr class="{{ 'archived' if m.status == 'archived' }}">
                <td class="rank">{{ loop.index }}</td>
                <td class="model-cell">
                  <a href="/edit/{{ m.id }}" class="edit-link">{{ m.name }}</a>
                  {% if m.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>{% endif %}
                </td>
                <td>{{ m.elo }}</td>
                <td class="wld w">{{ m.wins }}</td>
                <td class="wld l">{{ m.losses }}</td>
                <td class="wld d">{{ m.draws }}</td>
                <td>{{ m.games }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% else %}
        <div class="empty-state">
          {% if filter == 'active' %}
          Нет активных моделей. Переключите фильтр или добавьте новую модель.
          {% elif filter == 'inactive' %}
          Нет неактивных (архивных) моделей.
          {% else %}
          Нет моделей. Нажмите «+ Добавить модель», чтобы начать.
          {% endif %}
        </div>
        {% endif %}
      </div>

      {% if history %}
      <details class="history-details">
        <summary>История <span style="color:#64748b;font-size:0.85rem;font-weight:400;margin-left:8px;">({{ history_total }})</span></summary>
        <div class="card">
          <h2 style="display:none;">История</h2>
          {% for item in history %}
          <div class="history-item">
            <span class="history-model">{{ item.model_a_name }} vs {{ item.model_b_name }}</span>
            <span class="history-elo">{{ item.elo_a_before }} <span class="history-elo-arrow">→</span> {{ item.elo_a_after }}</span>
            <span class="{{ item.elo_a_delta_class }}">{{ item.elo_a_delta_str }}</span>
            <span class="history-elo">{{ item.elo_b_before }} <span class="history-elo-arrow">→</span> {{ item.elo_b_after }}</span>
            <span class="{{ item.elo_b_delta_class }}">{{ item.elo_b_delta_str }}</span>
            <span class="history-date">{{ item.date_str }}</span>
          </div>
          {% endfor %}
          {% if history_pages > 1 %}
          <div class="pagination">
            {% for p in range(1, history_pages + 1) %}
            {% if p == history_page %}<span class="current">{{ p }}</span>
            {% else %}<a href="?filter={{ filter }}&page={{ p }}">{{ p }}</a>{% endif %}
            {% endfor %}
          </div>
          {% endif %}
        </div>
      </details>
      {% endif %}
    </div>

    <div class="sidebar">
      {% if recommendations %}
      <div class="card">
        <div class="rec-header">
          <h2>Рекомендуемые модели к прогону</h2>
          {% if recommendations|length > 1 %}
          <div class="rec-nav">
            <span class="rec-counter" id="recCounter">1 / {{ recommendations|length }}</span>
            <button type="button" class="rec-next" onclick="nextRec()" title="Следующая рекомендация">→</button>
          </div>
          {% endif %}
        </div>
        {% for rec in recommendations %}
        <div class="rec-item" data-rec-index="{{ loop.index0 }}"{% if not loop.first %} style="display:none;"{% endif %}>
          <div class="rec-info">
            <div class="rec-pair">
              <span class="rec-model">{{ rec.name_a }}</span>
              <span class="rec-elo">{{ rec.elo_a }}</span>
              <span class="rec-vs">vs</span>
              <span class="rec-model">{{ rec.name_b }}</span>
              <span class="rec-elo">{{ rec.elo_b }}</span>
            </div>
            <div class="rec-reason">{{ rec.reason }}</div>
          </div>
          <button class="rec-btn" onclick="usePair('{{ rec.model_a }}', '{{ rec.model_b }}')">Прогнать</button>
        </div>
        {% endfor %}
      </div>
      {% elif models_count|int >= 2 %}
      <div class="card" style="background: #1e293b; border-color: #334155;">
        <h2 style="color: #94a3b8;">Все пары уже прогнаны</h2>
        <div class="rec-reason" style="color: #64748b;">Все возможные пары моделей уже сравнены. Добавьте новую модель или повторите сравнение.</div>
      </div>
      {% endif %}
      <div class="card">
        <h2>Записать результат</h2>
        {% if models_list|length >= 2 %}
        <form method="POST" action="/verdict" id="verdictForm">
          <div class="verdict-row">
            <div class="form-group">
              <label>Модель A</label>
              <select name="model_a" id="modelA" onchange="validate()">
                <option value="">— выбрать —</option>
                {% for mid, mname in models_list %}
                <option value="{{ mid }}">{{ mname }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="form-group">
              <label>Модель B</label>
              <select name="model_b" id="modelB" onchange="validate()">
                <option value="">— выбрать —</option>
                {% for mid, mname in models_list %}
                <option value="{{ mid }}">{{ mname }}</option>
                {% endfor %}
              </select>
            </div>
          </div>
          <div class="verdict-actions">
            <button type="submit" name="winner" value="a" class="btn btn-win" id="btnA" disabled>Победила A</button>
            <button type="submit" name="winner" value="b" class="btn btn-lose" id="btnB" disabled>Победила B</button>
            <button type="submit" name="winner" value="draw" class="btn btn-draw" id="btnDraw" disabled>Ничья</button>
          </div>
        </form>
        {% else %}
        <div class="empty-state">
          Нужно минимум 2 модели, чтобы записать результат.
        </div>
        {% endif %}
      </div>
    </div>
  </div>
</div>

<script>
let recIndex = 0;
function showRec(i) {
  const items = document.querySelectorAll('.rec-item[data-rec-index]');
  if (!items.length) return;
  recIndex = (i + items.length) % items.length;
  items.forEach((el) => {
    el.style.display = (parseInt(el.dataset.recIndex, 10) === recIndex) ? '' : 'none';
  });
  const counter = document.getElementById('recCounter');
  if (counter) counter.textContent = (recIndex + 1) + ' / ' + items.length;
}

function nextRec() {
  showRec(recIndex + 1);
}

function validate() {
  const a = document.getElementById('modelA').value;
  const b = document.getElementById('modelB').value;
  const ok = a && b && a !== b;
  document.getElementById('btnA').disabled = !ok;
  document.getElementById('btnB').disabled = !ok;
  document.getElementById('btnDraw').disabled = !ok;
}

function usePair(a, b) {
  document.getElementById('modelA').value = a;
  document.getElementById('modelB').value = b;
  validate();
}
</script>
</body>
</html>
"""


# ─── HTML: Add model page ───────────────────────────────────────────

ADD_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Добавить модель — ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<a href="/" class="back-link">&larr; Назад к рейтингу</a>

<div class="header">
  <h1>Добавить модель</h1>
</div>

{% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/add_model">
    <div class="form-group">
      <label>Название модели</label>
      <input type="text" name="name" required placeholder="Например: GPT-4o" autofocus>
    </div>
    <div class="hint">Стартовый ELO: {{ default_elo }}</div>
    <div style="margin-top:16px;">
      <button type="submit" class="btn btn-primary">Добавить</button>
    </div>
  </form>
</div>

{% if models_list %}
<div class="card">
  <h2>Уже в списке ({{ models_list|length }})</h2>
  <table>
    <thead><tr><th>Модель</th><th>Статус</th><th>ELO</th><th>Игр</th><th></th></tr></thead>
    <tbody>
      {% for mid, mname, elo, games, status in models_list %}
      <tr class="{{ 'archived' if status == 'archived' }}">
        <td><a href="/edit/{{ mid }}" class="edit-link">{{ mname }}</a></td>
        <td>
          {% if status == 'archived' %}<span class="status-pill status-archived">неактивна</span>
          {% else %}<span class="status-pill status-active">активна</span>{% endif %}
        </td>
        <td>{{ elo }}</td>
        <td>{{ games }}</td>
        <td><a href="/edit/{{ mid }}" class="btn btn-secondary" style="padding:6px 12px;font-size:0.8rem;">Изменить</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}
</body>
</html>
"""


# ─── HTML: Edit model page ──────────────────────────────────────────

EDIT_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Редактировать модель — ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<a href="/" class="back-link">&larr; Назад к рейтингу</a>

<div class="header">
  <h1>Редактировать модель</h1>
</div>

{% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/edit/{{ model.id }}">
    <div class="form-group">
      <label>ID модели</label>
      <input type="text" value="{{ model.id }}" disabled>
      <div class="hint">ID менять нельзя — он стабилен для истории.</div>
    </div>
    <div class="form-group">
      <label>Название модели</label>
      <input type="text" name="name" value="{{ model.name }}" required autofocus>
    </div>
    <div class="form-group">
      <label>Статус активности</label>
      <select name="status">
        <option value="active" {% if model.status == 'active' %}selected{% endif %}>Активна</option>
        <option value="archived" {% if model.status == 'archived' %}selected{% endif %}>Неактивна (архив)</option>
      </select>
    </div>
    <div style="margin-top:16px;">
      <button type="submit" class="btn btn-primary">Сохранить</button>
      <a href="/" class="btn btn-secondary" style="margin-left:8px;">Отмена</a>
    </div>
  </form>
</div>
</body>
</html>
"""


# ─── Routes ─────────────────────────────────────────────────────────


@app.route("/")
def leaderboard():
    index_data = ensure_index()

    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")

    # Фильтр таблицы: active / all / inactive
    filter_mode = request.args.get("filter", "active").strip().lower()
    if filter_mode not in ("active", "all", "inactive"):
        filter_mode = "active"

    if filter_mode == "active":
        models_sorted = [
            info for info in models.values()
            if is_model_active(info)
        ]
    elif filter_mode == "inactive":
        models_sorted = [
            info for info in models.values()
            if not is_model_active(info)
        ]
    else:
        models_sorted = list(models.values())

    models_sorted.sort(key=lambda m: m.get("elo", DEFAULT_ELO), reverse=True)

    # Для формы вердикта — только активные модели
    active_models = {
        mid: info for mid, info in models.items() if is_model_active(info)
    }
    models_list = sorted(
        ((mid, info.get("name", mid)) for mid, info in active_models.items()),
        key=lambda x: x[1].lower(),
    )

    # Рекомендации пар
    recommendations = get_recommendations(index_data, top_n=3)

    # История: пагинация по 20 записей, новые сверху
    name_map = {mid: info.get("name", mid) for mid, info in models.items()}
    raw_history = list(reversed(index_data.get("elo_history", [])))
    history_page = request.args.get("page", "1").strip()
    try:
        history_page = int(history_page)
    except ValueError:
        history_page = 1
    page_size = 20
    total_history = len(raw_history)
    history_pages = (total_history + page_size - 1) // page_size if total_history else 1
    history_page = max(1, min(history_page, history_pages))
    start = (history_page - 1) * page_size
    end = start + page_size
    history = format_elo_history(raw_history[start:end], name_map)

    return render_template_string(
        INDEX_TEMPLATE,
        models_sorted=models_sorted,
        models_count=len(models),
        filtered_count=len(models_sorted),
        matchups_count=len(index_data.get("matchups_index", [])),
        updated=index_data.get("updated", ""),
        models_list=models_list,
        recommendations=recommendations,
        history=history,
        history_page=history_page,
        history_pages=history_pages,
        history_total=total_history,
        filter=filter_mode,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


@app.route("/add")
def add_page():
    index_data = ensure_index()
    models_data = index_data.get("models", {})

    # (id, name, elo, games, status) — актуальный ELO из index.json
    models_list = []
    for mid, info in models_data.items():
        mname = info.get("name", mid)
        elo = info.get("elo", DEFAULT_ELO)
        games = info.get("games", 0)
        status = info.get("status", "active")
        models_list.append((mid, mname, elo, games, status))
    models_list.sort(key=lambda x: x[1].lower())

    return render_template_string(
        ADD_TEMPLATE,
        models_list=models_list,
        default_elo=DEFAULT_ELO,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


@app.route("/add_model", methods=["POST"])
def add_model():
    name = request.form.get("name", "").strip()

    if not name:
        return redirect(url_for("add_page", error="Введите название модели"))

    models_path = REPO_ROOT / "models.yaml"
    if not models_path.exists():
        return redirect(url_for("add_page", error="models.yaml не найден"))

    text = models_path.read_text(encoding="utf-8")
    models, preamble = parse_existing(text)

    existing_ids = [m["id"] for m in models]
    model_id = slugify(name, existing_ids)

    new_model = {
        "id": model_id,
        "name": name,
        "provider": "",
        "version": "",
        "released": "",
        "status": "active",
        "notes": "",
    }
    models.append(new_model)
    models.sort(key=lambda m: m["id"])

    out = preamble.rstrip() + "\n\nmodels:\n"
    for m in models:
        out += format_model(m) + "\n"

    models_path.write_text(out, encoding="utf-8")

    index_data = generate_index()
    save_index(index_data)

    return redirect(url_for("add_page", success=f"Модель «{name}» добавлена. Стартовый ELO: {DEFAULT_ELO}"))


@app.route("/verdict", methods=["POST"])
def record_verdict_route():
    model_a = request.form.get("model_a", "").strip()
    model_b = request.form.get("model_b", "").strip()
    winner = request.form.get("winner", "").strip()

    if not model_a or not model_b or not winner:
        return redirect(url_for("leaderboard", error="Выберите обе модели и победителя"))

    if model_a == model_b:
        return redirect(url_for("leaderboard", error="Модели должны различаться"))

    if winner not in ("a", "b", "draw"):
        return redirect(url_for("leaderboard", error="Неверный победитель"))

    try:
        result = record_verdict(
            task=DEFAULT_TASK,
            model_a=model_a,
            model_b=model_b,
            winner=winner,
        )
    except ValueError as e:
        return redirect(url_for("leaderboard", error=str(e)))

    name_map = get_model_name_map()
    name_a = name_map.get(model_a, model_a)
    name_b = name_map.get(model_b, model_b)
    winner_label = {"a": name_a, "b": name_b, "draw": "Ничья"}[winner]

    return redirect(url_for(
        "leaderboard",
        success=f"Записано: {name_a} vs {name_b} → {winner_label}",
    ))


@app.route("/edit/<model_id>")
def edit_page(model_id: str):
    index_data = ensure_index()
    info = index_data.get("models", {}).get(model_id)
    if not info:
        return redirect(url_for("leaderboard", error="Модель не найдена"))

    return render_template_string(
        EDIT_TEMPLATE,
        model={
            "id": model_id,
            "name": info.get("name", ""),
            "status": info.get("status", "active"),
        },
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


@app.route("/edit/<model_id>", methods=["POST"])
def edit_model(model_id: str):
    name = request.form.get("name", "").strip()
    status = request.form.get("status", "").strip()

    if not name:
        return redirect(url_for("edit_page", model_id=model_id, error="Введите название модели"))

    if status not in ("active", "archived"):
        return redirect(url_for("edit_page", model_id=model_id, error="Неверный статус"))

    if not update_model(model_id, name, status):
        return redirect(url_for("leaderboard", error="Не удалось обновить модель"))

    status_label = "активна" if status == "active" else "неактивна (архив)"
    return redirect(url_for(
        "leaderboard",
        filter="active",
        success=f"Модель «{name}» обновлена, статус: {status_label}.",
    ))


# ─── Port handling ──────────────────────────────────────────────────


def find_free_port(start: int = 5000, max_tries: int = 10) -> int:
    import socket
    for port in range(start, start + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start


# ─── Main ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = find_free_port()
    print(f"ELO Benchmark сервер: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
