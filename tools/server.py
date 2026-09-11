#!/usr/bin/env python3
"""
server.py — локальный веб-сервер для бенчмарка LLM-моделей.

Предоставляет:
  - Leaderboard (таблица ELO-рейтинга)
  - Форму записи вердикта (попарное сравнение: A vs B → победитель, таск)
  - Страницу настроек /settings (добавление модели, активные таски)
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
    load_settings, save_settings, known_tasks, active_tasks, is_task_active,
    resolve_current_task, get_coverage, is_valid_task_id,
    load_answer_flags, save_answer_flags, get_answer_matrix,
    DEFAULT_ELO,
    MATCHUPS_DIR, TASKS_DIR, INDEX_PATH, MODELS_PATH,
)

from register_task import (
    next_task_id, unique_slug_dir, fill_template, TEMPLATE_PATH, slugify as slugify_task,
)

from render_helpers import (
    format_elo_history, format_winrate, get_model_detail, build_elo_svg,
)

from register_model import parse_existing, format_model

from flask import Flask, request, redirect, url_for, render_template_string

app = Flask(__name__)


# ─── Helpers ────────────────────────────────────────────────────────


def ensure_index() -> dict:
    """Загружает index.json, пересчитывает если устарел."""
    if is_index_stale():
        data = generate_index()
        save_index(data)
        return data
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


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


def get_pair_stats() -> dict[frozenset[str], dict]:
    """Возвращает статистику пары: {frozenset{id_a, id_b}: {"games": int, "wins": {id: int}}}.

    Использует resolved ids (model_a_id/model_b_id) и пропускает
    tombstone- и аннулированные вердикты. `winner: "draw"` увеличивает
    только games, не меняя счёт побед.
    """
    model_ids = {m["id"] for m in load_models_yaml()}
    stats: dict[frozenset[str], dict] = {}
    if not MATCHUPS_DIR.exists():
        return stats
    matchups = load_matchups()
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
    for mu in matchups:
        if mu.get("void_of"):
            continue
        if mu.get("_matchup_id") in voided:
            continue
        a, b = resolve_matchup_models(mu, model_ids)
        if a and b:
            key = frozenset({a, b})
            st = stats.setdefault(key, {"games": 0, "wins": {a: 0, b: 0}})
            st["games"] += 1
            winner = mu.get("winner")
            if winner == "a":
                st["wins"][a] += 1
            elif winner == "b":
                st["wins"][b] += 1
    return stats


def is_model_active(model: dict) -> bool:
    """Проверяет, что модель не заархивирована."""
    return model.get("status", "active") != "archived"


def valid_answer_filter(value: str | None) -> str:
    """Валидирует фильтр матрицы ответов; невалидное → 'active'."""
    v = (value or "active").strip().lower()
    return v if v in ("active", "all", "inactive") else "active"


def get_pair_task_verdicts() -> dict[frozenset[str], set[str]]:
    """Возвращает {frozenset{id_a, id_b}: set(task_id)} с тасками,
    в которых у пары есть неаннулированный вердикт.

    Использует resolved ids (model_a_id/model_b_id) и пропускает
    tombstone- и аннулированные вердикты.
    """
    model_ids = {m["id"] for m in load_models_yaml()}
    verdicts: dict[frozenset[str], set[str]] = {}
    if not MATCHUPS_DIR.exists():
        return verdicts
    matchups = load_matchups()
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
    for mu in matchups:
        if mu.get("void_of"):
            continue
        if mu.get("_matchup_id") in voided:
            continue
        a, b = resolve_matchup_models(mu, model_ids)
        if a and b:
            key = frozenset({a, b})
            task = mu.get("task")
            if not task:
                task = str(mu.get("_matchup_id", "")).split("/", 1)[0]
            if task:
                verdicts.setdefault(key, set()).add(task)
    return verdicts


def find_task_dir(task_id: str) -> Path | None:
    """Находит директорию tasks/T-NNN-<slug> по id."""
    if not TASKS_DIR.exists():
        return None
    for d in TASKS_DIR.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        if re.match(rf"^{re.escape(task_id)}(?:$|-)", d.name):
            return d
    return None


def parse_task_md(text: str) -> dict:
    """Парсит task.md на front matter и тело."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"title": "", "project": "", "baseline_commit": "", "body": text}
    front = parts[1]
    body = parts[2].strip()
    data = {}
    for raw in front.splitlines():
        # Убираем inline-комментарии и лишние пробелы
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        data[k] = v
    return {
        "title": data.get("title", ""),
        "project": data.get("project", ""),
        "baseline_commit": data.get("baseline_commit", ""),
        "body": body,
    }


def format_task_md(task_id: str, title: str, project: str, baseline: str, body: str) -> str:
    """Форматирует содержимое task.md."""
    return (
        f"---\n"
        f"id: {task_id}\n"
        f"title: \"{title}\"\n"
        f"project: \"{project}\"\n"
        f"baseline_commit: \"{baseline}\"\n"
        f"---\n\n"
        f"{body.strip()}\n"
    )


def get_task_info(task_id: str) -> dict | None:
    """Возвращает метаданные и тело task.md по id.

    Если директории/файла нет, возвращает stub на основе _TEMPLATE.md,
    чтобы можно было создать задачу через форму редактирования.
    """
    task_dir = find_task_dir(task_id)
    task_file = task_dir / "task.md" if task_dir else None
    if task_file and task_file.exists():
        info = parse_task_md(task_file.read_text(encoding="utf-8"))
        info["id"] = task_id
        info["dir"] = task_dir
        return info

    # Stub: таска есть в настройках, но ещё без task.md
    if not TEMPLATE_PATH.exists():
        return None
    info = parse_task_md(TEMPLATE_PATH.read_text(encoding="utf-8"))
    info["id"] = task_id
    info["missing"] = True
    info["title"] = ""
    return info


def create_task(title: str, slug: str = "", project: str = "", baseline: str = "") -> dict:
    """Создаёт новую задачу: папку, task.md, обновляет settings."""
    if not title:
        raise ValueError("Введите название задачи")
    if not TEMPLATE_PATH.exists():
        raise ValueError("Шаблон tasks/_TEMPLATE.md не найден")

    task_id = next_task_id()
    if not slug:
        slug = slugify_task(title)
    if not slug:
        slug = "task"

    task_dir = unique_slug_dir(task_id, slug)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    filled = fill_template(template, task_id, title, project, baseline)

    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(filled, encoding="utf-8")

    settings = load_settings()
    settings["tasks"][task_id] = "active"
    settings["current_task"] = task_id
    save_settings(settings)

    return {"id": task_id, "dir": task_dir}


def update_task(task_id: str, title: str, project: str, baseline: str, body: str) -> bool:
    """Обновляет task.md; если директории нет — создаёт её."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        slug = slugify_task(title) or "task"
        task_dir = unique_slug_dir(task_id, slug)
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / "task.md"
    task_file.write_text(format_task_md(task_id, title, project, baseline, body), encoding="utf-8")
    return True


def toggle_task_status(task_id: str) -> bool:
    """Переключает статус задачи active/inactive."""
    if not is_valid_task_id(task_id):
        return False
    settings = load_settings()
    current = settings.get("tasks", {}).get(task_id, "active")
    new_status = "inactive" if current == "active" else "active"
    settings["tasks"][task_id] = new_status

    # Если деактивировали текущую — переключаем current на первую активную
    if new_status == "inactive" and settings.get("current_task") == task_id:
        active = [t for t in known_tasks(settings) if is_task_active(settings, t) and t != task_id]
        settings["current_task"] = active[0] if active else ""

    save_settings(settings)
    return True


def set_current_task(task_id: str) -> bool:
    """Назначает текущей задачей, если она активна."""
    if not is_valid_task_id(task_id):
        return False
    settings = load_settings()
    if not is_task_active(settings, task_id):
        return False
    settings["current_task"] = task_id
    save_settings(settings)
    return True


def update_model(model_id: str, name: str, status: str) -> bool:
    """Редактирует name и status модели в models.yaml и пересчитывает index."""
    models_path = MODELS_PATH
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

    Алгоритм (трёхуровневый):
    1. Берём все пары активных моделей из index.json
    2. Сортировка лексикографическая:
       - сначала pair_games по возрастанию (несыгранные пары выше
         любых рематчей — круг завершается до начала повторов)
       - затем тир калибровки (по min_games — числу игр менее
         игранной модели в паре):
         тир 0: min_games == 0 (новая модель, ещё не играла)
         тир 1: min_games < 3 (мало игр, нужна калибровка)
         тир 2: остальные
       - внутри тира по близости ELO (меньше elo_diff — выше):
         самый равный бой идёт первым
    3. Возвращаем top_n

    Возвращает список dict: {model_a, model_b, name_a, name_b, elo_a,
    elo_b, elo_diff, pair_games, pair_wins_a, pair_wins_b, h2h_label,
    tier, score, recommended_task}
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

    pair_stats = get_pair_stats()
    pair_task_verdicts = get_pair_task_verdicts()
    active_task_ids = active_tasks(load_settings())

    candidates = []
    for i in range(len(model_ids)):
        for j in range(i + 1, len(model_ids)):
            a, b = model_ids[i], model_ids[j]
            pair_key = frozenset({a, b})
            st = pair_stats.get(pair_key)
            pair_games = st["games"] if st else 0
            pair_wins_a = st["wins"].get(a, 0) if st else 0
            pair_wins_b = st["wins"].get(b, 0) if st else 0

            elo_a = elo_map[a]
            elo_b = elo_map[b]
            elo_diff = abs(elo_a - elo_b)
            min_games = min(games_map[a], games_map[b])

            # Тир калибровки: новая модель всегда выше калибрующейся,
            # калибрующаяся — выше сыгранных. Внутри тира — близость ELO.
            if min_games == 0:
                tier = 0
            elif min_games < 3:
                tier = 1
            else:
                tier = 2

            # Строка личных встреч: число вердиктов пары и счёт по победам
            # в порядке отображения карточки (model_a : model_b). Ничьи
            # входят в pair_games, но в счёт не выделяются.
            if pair_games > 0:
                h2h_label = (
                    f"личные встречи: {pair_games} · "
                    f"счёт {pair_wins_a}:{pair_wins_b}"
                )
            else:
                h2h_label = "личные встречи: не встречались"

            # score = близость ELO: монотонно убывает с ростом diff,
            # внутри тира больший score идёт первым
            closeness = 1.0 / (1.0 + elo_diff / 100.0)

            # Первый активный таск по порядку T-NNN, в котором у пары
            # нет вердикта. Если все заполнены — берём первый активный.
            verdict_tasks = pair_task_verdicts.get(pair_key, set())
            if active_task_ids:
                recommended_task = next(
                    (t for t in active_task_ids if t not in verdict_tasks),
                    active_task_ids[0],
                )
            else:
                recommended_task = ""

            candidates.append({
                "model_a": a,
                "model_b": b,
                "name_a": name_map.get(a, a),
                "name_b": name_map.get(b, b),
                "elo_a": elo_a,
                "elo_b": elo_b,
                "elo_diff": elo_diff,
                "pair_games": pair_games,
                "pair_wins_a": pair_wins_a,
                "pair_wins_b": pair_wins_b,
                "h2h_label": h2h_label,
                "tier": tier,
                "score": closeness,
                "recommended_task": recommended_task,
            })

    candidates.sort(key=lambda c: (c["pair_games"], c["tier"], -c["score"]))
    return candidates[:top_n]


def format_reason(rec: dict) -> str:
    """Строка-обоснование рекомендации (только отображение).

    Вычисляется из готовых полей рекомендации; вывод get_recommendations
    не меняется (поле reason в нём запрещено спекой pairing-algorithm).
    """
    games = rec.get("pair_games", 0)
    diff = rec.get("elo_diff", 0)
    if games == 0:
        text = f"не встречались · Δ={diff}"
        if rec.get("tier", 2) == 0:
            text += " · новая модель"
        return text
    return (
        f"счёт {rec.get('pair_wins_a', 0)}:{rec.get('pair_wins_b', 0)}"
        f" · Δ={diff}"
    )


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
    max-width: 100%;
    margin: 0 auto;
    padding: 24px 4%;
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
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-bottom: 16px;
  }
  .verdict-actions {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
  }
  .verdict-actions .btn { flex: 1 1 0; min-width: 0; text-align: center; padding: 12px; }
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
    flex-wrap: wrap;
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
  .rec-h2h {
    color: #a5b4fc;
    font-size: 0.82rem;
    margin-top: 4px;
  }
  .rec-reason {
    color: #94a3b8;
    font-size: 0.82rem;
    margin-top: 2px;
  }
  .rec-task {
    color: #94a3b8;
    font-size: 0.82rem;
    margin-top: 2px;
  }
  .legend {
    color: #64748b;
    font-size: 0.8rem;
    margin-top: 10px;
  }
  tr.top-1 td { background: rgba(52, 211, 153, 0.08); }
  tr.top-2 td { background: rgba(129, 140, 248, 0.08); }
  tr.top-3 td { background: rgba(251, 191, 36, 0.08); }
  .medal { margin-right: 6px; }
  .archived-section {
    margin-top: 16px;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 12px 16px;
    color: #94a3b8;
    font-size: 0.85rem;
  }
  .archived-section summary { cursor: pointer; font-weight: 600; }
  .archived-section ul { list-style: none; margin: 8px 0 0; padding: 0; }
  .archived-section li {
    padding: 4px 0;
    border-bottom: 1px solid #1e293b;
    display: flex;
    justify-content: space-between;
    gap: 12px;
  }
  .detail-header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
  .detail-header h1 { margin: 0; }
  .detail-elo { font-size: 1.4rem; font-weight: 700; color: #818cf8; }
  .back-link { display: inline-block; color: #94a3b8; text-decoration: none; font-size: 0.9rem; margin-bottom: 16px; }
  .back-link:hover { color: #e2e8f0; }
  .stats-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 20px 0 24px; }
  .stat-card { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px; text-align: center; }
  .stat-card .stat-value { font-size: 1.25rem; font-weight: 700; }
  .stat-card .stat-label { font-size: 0.75rem; color: #94a3b8; margin-top: 4px; }
  .chart { width: 100%; height: auto; }
  .chart-line { stroke: #818cf8; stroke-width: 2; }
  .chart-dot { fill: #818cf8; }
  .chart-grid { stroke: #1e293b; stroke-width: 1; }
  .chart-tick { fill: #64748b; font-size: 12px; }
  .chart-mark { fill: #94a3b8; font-size: 12px; font-weight: 600; }
  .chart-empty { color: #64748b; padding: 24px; text-align: center; }
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
    grid-template-columns: minmax(0, 1fr) 380px;
    grid-template-areas: "rating sidebar";
    row-gap: 16px;
    column-gap: 24px;
    align-items: stretch;
  }
  .main-column { display: contents; }
  .rating-card { grid-area: rating; }
  .sidebar {
    grid-area: sidebar;
    display: flex;
    flex-direction: column;
    gap: 16px;
    height: 100%;
    min-width: 0;
  }
  .sidebar .card { margin-bottom: 0; }

  /* Settings page */
  .settings-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 20px;
    align-items: stretch;
  }
  .settings-grid .card {
    margin-bottom: 0;
    display: flex;
    flex-direction: column;
  }
  .settings-grid .card > form {
    display: flex;
    flex-direction: column;
    flex: 1;
  }
  .card-actions {
    margin-top: auto;
    padding-top: 16px;
  }
  .tasks-table input[type="checkbox"],
  .tasks-table input[type="radio"] {
    width: 18px;
    height: 18px;
    accent-color: #6366f1;
    cursor: pointer;
  }
  .tasks-table td { text-align: left; vertical-align: middle; }
  .tasks-table .id-col { font-weight: 600; white-space: nowrap; padding-right: 12px; }
  .tasks-table .title-col { width: 99%; white-space: normal; }
  .tasks-table .title-col .status-pill { margin-left: 8px; white-space: nowrap; }
  .tasks-table .actions-col { text-align: right; white-space: nowrap; padding-left: 12px; }

  /* Settings page: раскрываемые группы моделей */
  .model-groups > .model-row { border-bottom: 1px solid #334155; }
  .model-groups > div.model-row,
  .model-groups > details.model-row > summary {
    display: flex;
    justify-content: space-between;
    padding: 12px 14px;
  }
  .model-groups summary { cursor: pointer; list-style: none; }
  .model-groups summary::-webkit-details-marker { display: none; }
  .model-groups summary:hover { background: #334155; }
  .model-groups summary .mg-label::before {
    content: "\\25B8";
    display: inline-block;
    margin-right: 6px;
    color: #64748b;
  }
  .model-groups details[open] > summary .mg-label::before { content: "\\25BE"; }
  .model-groups .model-list {
    list-style: none;
    margin: 0;
    padding: 4px 14px 12px 28px;
  }
  .model-groups .model-list li {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 6px 0;
    border-bottom: 1px solid #334155;
  }
  .model-groups .model-list li:last-child { border-bottom: none; }
  .model-groups .model-empty { color: #64748b; }

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
  .flags-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
    font-size: 0.85rem;
    color: #94a3b8;
  }
  .flags-bar label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    font-weight: 600;
  }
  .flags-table input[type="checkbox"] {
    width: 18px;
    height: 18px;
    accent-color: #6366f1;
    cursor: pointer;
  }
  .flags-table th, .flags-table td { text-align: center; }
  .flags-table th:first-child, .flags-table td:first-child { text-align: left; }
  .flags-table .col-btn {
    padding: 2px 8px;
    font-size: 0.75rem;
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

  /* Progress status bar */
  .progress-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 18px 24px;
    margin-bottom: 20px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  }
  .progress-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 12px;
  }
  .progress-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .progress-pct {
    font-size: 1.5rem;
    font-weight: 700;
    color: #f1f5f9;
  }
  .progress-track {
    height: 12px;
    background: #0f172a;
    border: 1px solid #334155;
    border-radius: 999px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #6366f1, #10b981);
    transition: width 0.4s ease;
    position: relative;
  }
  .progress-fill::after {
    content: "";
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
      -45deg,
      rgba(255,255,255,0.15) 0 8px,
      transparent 8px 16px
    );
    animation: progress-stripes 1.2s linear infinite;
  }
  @keyframes progress-stripes {
    from { background-position: 0 0; }
    to { background-position: 22.63px 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .progress-fill::after { animation: none; }
    .progress-fill { transition: none; }
  }
  .progress-meta {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 10px;
    font-size: 0.85rem;
    color: #94a3b8;
  }
  .progress-card--empty .progress-pct { color: #64748b; }
  .progress-card--empty .progress-track { opacity: 0.5; }
  .progress-card--done .progress-fill { background: #10b981; }
  .progress-card--done .progress-fill::after { display: none; }
  .progress-card--done .progress-pct { color: #34d399; }

  /* Responsive */
  @media (max-width: 900px) {
    .content-grid {
      grid-template-columns: 1fr;
      grid-template-areas: "rating" "sidebar";
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
    <div style="display:flex;gap:12px;align-items:center;">
      <a href="/history" class="btn btn-secondary">История</a>
      <a href="/settings" class="btn btn-primary">Настройки</a>
    </div>
  </div>

  {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

  <div class="progress-card{% if coverage_pct is none %} progress-card--empty{% elif coverage_done %} progress-card--done{% endif %}">
    <div class="progress-head">
      <span class="progress-title">Прогресс прогона</span>
      <span class="progress-pct">{% if coverage_pct is none %}—{% else %}{{ coverage_pct }}%{% endif %}</span>
    </div>
    <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100"{% if coverage_pct is not none %} aria-valuenow="{{ coverage_pct }}"{% endif %} aria-label="Прогресс прогона">
      <div class="progress-fill" style="width: {{ coverage.percent or 0 }}%"></div>
    </div>
    <div class="progress-meta">
      {% if coverage_pct is none %}
      <span>Нет данных о покрытии</span>
      {% elif coverage_done %}
      <span>Все пары закрыты</span>
      {% else %}
      <span>закрыто {{ coverage.filled }} из {{ coverage.total }}</span>
      <span>осталось {{ remaining }}</span>
      {% endif %}
    </div>
  </div>

  <div class="controls">
    <div class="stats">
      Моделей: {{ filtered_count }} из {{ models_count }} · Вердиктов: {{ matchups_count }} · Обновлено: {{ updated }}
    </div>
    <div class="legend">Старт 1200 · K 40/32/24 · ничья 0.5</div>
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
                <th>Винрейт, %</th>
              </tr>
            </thead>
            <tbody>
              {% for m in models_sorted %}
              <tr class="{{ 'archived' if m.status == 'archived' }}{{ (' top-%d' % medals[m.id]) if m.id in medals and filter != 'inactive' }}">
                <td class="rank">{% if m.id in medals and filter != 'inactive' %}<span class="medal">{{ medal_icons[medals[m.id] - 1] }}</span>{% endif %}{{ loop.index }}</td>
                <td class="model-cell">
                  <a href="/model/{{ m.id }}" class="edit-link">{{ m.name }}</a>
                  {% if m.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>{% endif %}
                </td>
                <td>{{ m.elo }}</td>
                <td class="wld w">{{ m.wins }}</td>
                <td class="wld l">{{ m.losses }}</td>
                <td class="wld d">{{ m.draws }}</td>
                <td>{{ m.games }}</td>
                <td class="winrate">{{ format_winrate(m.wins, m.games) }}</td>
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
          Нет моделей. Добавьте модель через «Настройки», чтобы начать.
          {% endif %}
        </div>
        {% endif %}
        {% if filter == 'active' and archived_list %}
        <details class="archived-section">
          <summary>Архивные модели ({{ archived_list|length }})</summary>
          <ul>
            {% for a in archived_list %}
            <li><a href="/model/{{ a.id }}" class="edit-link">{{ a.name }}</a><span>{{ a.elo }}</span></li>
            {% endfor %}
          </ul>
        </details>
        {% endif %}
      </div>


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
            <div class="rec-h2h">{{ rec.h2h_label }}</div>
            <div class="rec-reason">{{ rec.reason }}</div>
            <div class="rec-task">таск: {{ rec.recommended_task }}</div>
          </div>
          <button class="rec-btn" onclick="usePair('{{ rec.model_a }}', '{{ rec.model_b }}', '{{ rec.recommended_task }}')">Прогнать</button>
        </div>
        {% endfor %}
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
            <div class="form-group">
              <label>Таск</label>
              <select name="task" id="taskField" onchange="validate()" required>
                <option value="">— выбрать —</option>
                {% for t in task_options %}
                <option value="{{ t }}" {% if t == current_task %}selected{% endif %}>{{ t }}</option>
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
  const t = document.getElementById('taskField').value.trim();
  const ok = a && b && a !== b && t;
  document.getElementById('btnA').disabled = !ok;
  document.getElementById('btnB').disabled = !ok;
  document.getElementById('btnDraw').disabled = !ok;
}

function usePair(a, b, task) {
  document.getElementById('modelA').value = a;
  document.getElementById('modelB').value = b;
  document.getElementById('taskField').value = task;
  validate();
}
</script>
</body>
</html>
"""


# ─── HTML: History page ─────────────────────────────────────────────

HISTORY_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>История — ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<div class="page">
  <a href="/" class="back-link">&larr; Назад к рейтингу</a>

  <div class="header">
    <h1>История ELO</h1>
  </div>

  <div class="controls">
    <div class="stats">
      Всего записей: {{ history_total }}{% if model %} · Фильтр: {{ model_name }}{% endif %}
    </div>
    <form method="GET" action="/history" class="filter-bar">
      <label for="model">Модель</label>
      <select name="model" id="model" onchange="this.form.submit()">
        {% for m in models_dropdown %}
        <option value="{{ m.id }}" {% if m.selected %}selected{% endif %}>{{ m.name }}{% if m.archived %} (неактивна){% endif %}</option>
        {% endfor %}
      </select>
      <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;">
        <input type="checkbox" name="include_inactive" value="1" {% if include_inactive %}checked{% endif %} onchange="this.form.submit()">
        Включать неактивные
      </label>
    </form>
  </div>

  <div class="card">
    <h2 style="display:none;">История</h2>
    {% if history %}
    {% for item in history %}
    <div class="history-item">
      <span class="history-model">{{ item.model_a_name }} vs {{ item.model_b_name }}</span>
      <span class="history-elo">{{ item.elo_a_before }} <span class="history-elo-arrow">&rarr;</span> {{ item.elo_a_after }}</span>
      <span class="{{ item.elo_a_delta_class }}">{{ item.elo_a_delta_str }}</span>
      <span class="history-elo">{{ item.elo_b_before }} <span class="history-elo-arrow">&rarr;</span> {{ item.elo_b_after }}</span>
      <span class="{{ item.elo_b_delta_class }}">{{ item.elo_b_delta_str }}</span>
      <span class="history-date">{{ item.date_str }}</span>
    </div>
    {% endfor %}
    {% if history_pages > 1 %}
    <div class="pagination">
      {% for p in range(1, history_pages + 1) %}
      {% if p == history_page %}<span class="current">{{ p }}</span>
      {% else %}<a href="?page={{ p }}{% if model %}&model={{ model }}{% endif %}{% if include_inactive %}&include_inactive=1{% endif %}">{{ p }}</a>{% endif %}
      {% endfor %}
    </div>
    {% endif %}
    {% else %}
    <div class="empty-state">Нет истории</div>
    {% endif %}
  </div>
</div>
</body>
</html>
"""


# ─── HTML: Model page ─────────────────────────────────────────────

MODEL_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ detail.name }} — ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<div class="page">
  <a href="/" class="back-link">&larr; Назад к рейтингу</a>

  <div class="detail-header">
    <h1>{{ detail.name }}</h1>
    <span class="detail-elo">{{ detail.elo }}</span>
    {% if detail.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>{% endif %}
    <a href="/edit/{{ detail.id }}" class="btn btn-secondary">Изменить</a>
  </div>

  {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-value">{{ detail.elo }}</div><div class="stat-label">ELO</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.games }}</div><div class="stat-label">Матчей</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.wins }}</div><div class="stat-label">Побед</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.losses }}</div><div class="stat-label">Поражений</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.draws }}</div><div class="stat-label">Ничьих</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.winrate }}</div><div class="stat-label">Винрейт</div></div>
  </div>

  <div class="card">
    <h2>Динамика ELO</h2>
    {{ chart_svg|safe }}
  </div>

  <div class="card">
    <h2>Личные встречи</h2>
    {% if detail.h2h %}
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Соперник</th><th>Встреч</th><th>W</th><th>L</th><th>D</th><th>Винрейт</th></tr>
        </thead>
        <tbody>
          {% for r in detail.h2h %}
          <tr>
            <td><a href="/model/{{ r.id }}" class="edit-link">{{ r.name }}</a></td>
            <td>{{ r.games }}</td>
            <td class="wld w">{{ r.w }}</td>
            <td class="wld l">{{ r.l }}</td>
            <td class="wld d">{{ r.d }}</td>
            <td class="winrate">{{ r.winrate }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="empty-state">Пока нет встреч</div>
    {% endif %}
  </div>

  <div class="card">
    <h2>История матчей</h2>
    {% if detail.history %}
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Соперник</th><th>Дата</th><th>Исход</th><th>ELO до</th><th>Δ</th><th>ELO после</th></tr>
        </thead>
        <tbody>
          {% for h in detail.history %}
          <tr>
            <td><a href="/model/{{ h.opp_id }}" class="edit-link">{{ h.opp_name }}</a></td>
            <td>{{ h.date_str }}</td>
            <td>{{ h.outcome }}</td>
            <td>{{ h.before }}</td>
            <td class="{{ h.delta_class }}">{{ h.delta_str }}</td>
            <td>{{ h.after }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="empty-state">Пока нет матчей</div>
    {% endif %}
  </div>
</div>
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
<a href="/model/{{ model.id }}" class="back-link">&larr; Назад к модели</a>

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
      <a href="/model/{{ model.id }}" class="btn btn-secondary" style="margin-left:8px;">Отмена</a>
    </div>
  </form>
</div>
</body>
</html>
"""


# ─── HTML: Add task page ────────────────────────────────────────────

ADD_TASK_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Добавить таску — ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<a href="/settings" class="back-link">&larr; Назад к настройкам</a>

<div class="header">
  <h1>Добавить таску</h1>
</div>

{% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/add_task">
    <div class="form-group">
      <label>Название</label>
      <input type="text" name="title" required placeholder="Например: Bug Hunt — NewModule" autofocus>
    </div>
    <div class="form-group">
      <label>Slug (опц.)</label>
      <input type="text" name="slug" placeholder="new-module">
      <div class="hint">Если пусто, slug сгенерируется из названия.</div>
    </div>
    <div class="form-group">
      <label>Проект (опц.)</label>
      <input type="text" name="project" placeholder="Например: VoiceMind">
    </div>
    <div class="form-group">
      <label>Baseline commit (опц.)</label>
      <input type="text" name="baseline" placeholder="abc1234...">
    </div>
    <div style="margin-top:16px;">
      <button type="submit" class="btn btn-primary">Добавить</button>
      <a href="/settings" class="btn btn-secondary" style="margin-left:8px;">Отмена</a>
    </div>
  </form>
</div>
</body>
</html>
"""


# ─── HTML: Edit task page ───────────────────────────────────────────

EDIT_TASK_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Редактировать таску — ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<a href="/settings" class="back-link">&larr; Назад к настройкам</a>

<div class="header">
  <h1>Редактировать таску {{ task.id }}</h1>
</div>

{% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/edit_task/{{ task.id }}">
    <input type="hidden" name="id" value="{{ task.id }}">
    <div class="hint" style="margin-bottom:16px;">
      Обязательны только <strong>название</strong> и <strong>описание</strong>.
      Проект и baseline_commit — опциональны, нужны skills прогонов.
    </div>
    <div class="form-group">
      <label>Название</label>
      <input type="text" name="title" value="{{ task.title }}" required autofocus placeholder="Bug Hunt — NewModule">
    </div>
    <div class="form-group">
      <label>Описание и критерии (Markdown)</label>
      <textarea name="body" rows="12" style="width:100%;padding:10px 12px;border:1px solid #475569;border-radius:8px;font-size:1rem;color:#e2e8f0;background:#0f172a;">{{ task.body }}</textarea>
    </div>
    <details class="card" style="background:transparent;border:none;padding:0;margin-bottom:16px;">
      <summary style="cursor:pointer;font-weight:600;color:#94a3b8;font-size:0.95rem;">Дополнительно: проект и baseline</summary>
      <div class="form-group" style="margin-top:12px;">
        <label>Проект (опц.)</label>
        <input type="text" name="project" value="{{ task.project }}" placeholder="Например: VoiceMind">
      </div>
      <div class="form-group">
        <label>Baseline commit (опц.)</label>
        <input type="text" name="baseline" value="{{ task.baseline_commit }}" placeholder="abc1234...">
      </div>
    </details>
    <div style="margin-top:16px;">
      <button type="submit" class="btn btn-primary">Сохранить</button>
      <a href="/settings" class="btn btn-secondary" style="margin-left:8px;">Отмена</a>
    </div>
  </form>
</div>
</body>
</html>
"""


# ─── HTML: Settings page ────────────────────────────────────────────

SETTINGS_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Настройки — ELO Benchmark</title>
<style>""" + CSS + """</style>
</head>
<body>
<div class="page">
  <a href="/" class="back-link">&larr; Назад к рейтингу</a>

  <div class="header">
    <h1>Настройки</h1>
  </div>

  {% if error %}<div class="alert alert-error">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}

  <div class="settings-grid">
    <div class="card">
      <h2>Модели</h2>
      <div class="model-groups">
        <div class="model-row">
          <span>Всего в реестре</span>
          <span>{{ models_total }}</span>
        </div>
        <details class="model-row">
          <summary>
            <span class="mg-label">Активных</span>
            <span>{{ models_active }}</span>
          </summary>
          <ul class="model-list">
            {% for m in models_active_list %}
            <li>
              <a href="/model/{{ m.id }}" class="edit-link">{{ m.name }}</a>
              <span>{{ m.elo }}</span>
            </li>
            {% else %}
            <li class="model-empty">Нет активных моделей</li>
            {% endfor %}
          </ul>
        </details>
        <details class="model-row">
          <summary>
            <span class="mg-label">Неактивных (архив)</span>
            <span>{{ models_archived }}</span>
          </summary>
          <ul class="model-list">
            {% for m in models_archived_list %}
            <li>
              <a href="/model/{{ m.id }}" class="edit-link">{{ m.name }}</a>
              <span>{{ m.elo }}</span>
            </li>
            {% else %}
            <li class="model-empty">Нет неактивных моделей</li>
            {% endfor %}
          </ul>
        </details>
      </div>
      <div class="hint">
        Модель добавляется одним полем — названием; id генерируется
        автоматически. Изменить или архивировать — по ссылке «Изменить»
        в списке моделей.
      </div>
      <div class="card-actions">
        <a href="/add" class="btn btn-primary">+ Добавить модель</a>
      </div>
    </div>

    <div class="card">
      <h2>Таски</h2>
      {% if tasks_list %}
      <table class="tasks-table">
        <thead>
          <tr><th class="id-col">ID</th><th class="title-col">Название</th><th class="actions-col">Действия</th></tr>
        </thead>
        <tbody>
          {% for t in tasks_list %}
          <tr class="{{ 'archived' if not t.active }}">
            <td class="id-col">{{ t.id }}</td>
            <td class="title-col">
              {{ t.title }}
              {% if t.active %}<span class="status-pill status-active">активна</span>
              {% else %}<span class="status-pill status-archived">неактивна</span>{% endif %}
              {% if t.current %}<span class="status-pill status-active">текущая</span>{% endif %}
            </td>
            <td class="actions-col">
              <form method="POST" action="/task/{{ t.id }}/current" style="display:inline;">
                <input type="hidden" name="answer_filter" value="{{ answer_filter }}">
                <button type="submit" class="btn btn-secondary" style="padding:6px 12px;font-size:0.8rem;" {% if not t.active or t.current %}disabled{% endif %}>Текущая</button>
              </form>
              <form method="POST" action="/task/{{ t.id }}/toggle" style="display:inline;margin-left:6px;">
                <input type="hidden" name="answer_filter" value="{{ answer_filter }}">
                <button type="submit" class="btn btn-secondary" style="padding:6px 12px;font-size:0.8rem;">
                  {% if t.active %}Деактивировать{% else %}Активировать{% endif %}
                </button>
              </form>
              <a href="/edit_task/{{ t.id }}" class="btn btn-secondary" style="padding:6px 12px;font-size:0.8rem;margin-left:6px;">Изменить</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <div class="empty-state">Тасков пока нет — добавьте первую.</div>
      {% endif %}
      <div class="hint">
        Активные таски участвуют в прогрессе и доступны в форме вердикта.
        Текущая таска подставляется по умолчанию. «Удаление» = деактивация,
        файлы задачи остаются.
      </div>
      <div class="card-actions">
        <a href="/add_task" class="btn btn-primary">+ Добавить таску</a>
      </div>
    </div>
  </div>

  <div class="card" id="answer-coverage">
    <h2>Наличие ответов</h2>
    {% if answer_has_active %}
    <div class="stats">ответы: закрыто {{ answer_filled }} из {{ answer_total }} · осталось {{ answer_remaining }}</div>
    {% else %}
    <div class="stats">ответы: — (нет активных моделей или активных тасков)</div>
    {% endif %}
    <div class="hint">
      Тексты ответов хранятся вне проекта; здесь только флаги «ответ получен».
      Новая модель и новый таск по умолчанию считаются долгом.
      Флаги моделей вне фильтра и неактивных тасков сохраняются без изменений.
    </div>
    {% if answer_active_tasks %}
    <form method="GET" action="/settings" class="filter-bar">
      <label for="answer_filter">Показывать</label>
      <select name="answer_filter" id="answer_filter" onchange="this.form.submit()">
        <option value="active" {% if answer_filter == 'active' %}selected{% endif %}>Только активные</option>
        <option value="all" {% if answer_filter == 'all' %}selected{% endif %}>Все</option>
        <option value="inactive" {% if answer_filter == 'inactive' %}selected{% endif %}>Только неактивные</option>
      </select>
    </form>
    {% if answer_rows %}
    <form method="POST" action="/answer_flags?answer_filter={{ answer_filter }}" id="flagsForm">
      <input type="hidden" name="answer_filter" value="{{ answer_filter }}">
      <div class="flags-bar">
        <label><input type="checkbox" id="onlyDebts"> только долги</label>
        <span id="flagsCounter"></span>
      </div>
      <div class="table-wrap">
        <table class="flags-table">
          <thead>
            <tr>
              <th>Модель</th>
              {% for t in answer_active_tasks %}
              <th>{{ t }}<br>
                <button type="button" class="btn btn-secondary col-btn" onclick="colSet('{{ t }}', true)">все</button>
                <button type="button" class="btn btn-secondary col-btn" onclick="colSet('{{ t }}', false)">сброс</button>
              </th>
              {% endfor %}
              <th>Долг</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {% for r in answer_rows %}
            <tr data-debt="{{ r.debt }}" class="{{ 'archived' if r.status == 'archived' }}">
              <td class="model-cell">{{ r.name }}{% if r.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>{% endif %}</td>
              {% for t in answer_active_tasks %}
              <td><input type="checkbox" name="flag" value="{{ r.id }}||{{ t }}" data-col="{{ t }}" {% if r.cells[t] %}checked{% endif %}></td>
              {% endfor %}
              <td>{{ r.debt }}</td>
              <td><button type="button" class="btn btn-secondary col-btn" onclick="rowToggle(this)">строка</button></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% if answer_inactive_tasks %}
      <div class="hint">Неактивные таски скрыты: {{ answer_inactive_tasks|join(', ') }}. Их флаги сохраняются без изменений.</div>
      {% endif %}
      <div class="card-actions">
        <button type="submit" class="btn btn-primary">Сохранить</button>
      </div>
    </form>
    {% else %}
    <div class="empty-state">
      {% if answer_filter == 'inactive' %}
      Нет неактивных моделей для учёта.
      {% elif answer_filter == 'all' %}
      Нет моделей для учёта.
      {% else %}
      Нет активных моделей для учёта.
      {% endif %}
    </div>
    {% endif %}
    {% else %}
    <div class="empty-state">Нет активных моделей или активных тасков для учёта.</div>
    {% endif %}
  </div>
</div>

<script>
// Матрица наличия ответов: фильтр «только долги», счётчик, bulk по строке/столбцу.
function flagsVisibleRows() {
  return Array.from(document.querySelectorAll('#flagsForm tbody tr'));
}
function updateFlagsCounter() {
  const rows = flagsVisibleRows();
  const shown = rows.filter((tr) => tr.style.display !== 'none').length;
  const el = document.getElementById('flagsCounter');
  if (el) el.textContent = 'показано ' + shown + ' из ' + rows.length + ' моделей';
}
function applyDebtsFilter() {
  const only = document.getElementById('onlyDebts');
  const hide = only && only.checked;
  flagsVisibleRows().forEach((tr) => {
    tr.style.display = (hide && tr.dataset.debt === '0') ? 'none' : '';
  });
  updateFlagsCounter();
}
function rowToggle(btn) {
  const boxes = btn.closest('tr').querySelectorAll('input[name="flag"]');
  const target = Array.from(boxes).some((cb) => !cb.checked);
  boxes.forEach((cb) => { cb.checked = target; });
}
function colSet(task, val) {
  document.querySelectorAll('#flagsForm input[name="flag"][data-col="' + task + '"]').forEach((cb) => {
    const tr = cb.closest('tr');
    if (tr && tr.style.display === 'none') return;
    cb.checked = val;
  });
}
(function initFlags() {
  const only = document.getElementById('onlyDebts');
  if (only) only.addEventListener('change', applyDebtsFilter);
  updateFlagsCounter();
})();
</script>

<script>
// Снятие «активна» отключает и сбрасывает радио «текущая» у этой таски.
document.querySelectorAll('input[name="active"]').forEach((cb) => {
  cb.addEventListener('change', () => {
    const radio = document.querySelector(
      'input[name="current_task"][value="' + cb.value + '"]'
    );
    if (radio) {
      radio.disabled = !cb.checked;
      if (!cb.checked && radio.checked) radio.checked = false;
    }
  });
});
</script>
</body>
</html>
"""


# ─── Routes ─────────────────────────────────────────────────────────


@app.route("/history")
def history_page():
    index_data = ensure_index()

    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")

    model_id = request.args.get("model", "").strip()
    include_inactive = request.args.get("include_inactive", "") == "1"

    # Выпадайка: активные + выбранная модель, плюс archived при чекбоксе
    all_models = sorted(models.values(), key=lambda m: m.get("name", "").lower())
    dropdown = [{"id": "", "name": "Все", "archived": False, "selected": not model_id}]
    for m in all_models:
        mid = m.get("id", "")
        status = m.get("status", "active")
        archived = status == "archived"
        if not include_inactive and archived and mid != model_id:
            continue
        dropdown.append({
            "id": mid,
            "name": m.get("name", mid),
            "archived": archived,
            "selected": mid == model_id,
        })

    name_map = {mid: info.get("name", mid) for mid, info in models.items()}
    raw_history = list(reversed(index_data.get("elo_history", [])))

    if model_id:
        raw_history = [
            h for h in raw_history
            if h.get("model_a_id") == model_id or h.get("model_b_id") == model_id
        ]

    # Пагинация по 20 записей
    page_size = 20
    total_history = len(raw_history)
    history_pages = (total_history + page_size - 1) // page_size if total_history else 1
    history_page_num = request.args.get("page", "1").strip()
    try:
        history_page_num = int(history_page_num)
    except ValueError:
        history_page_num = 1
    history_page_num = max(1, min(history_page_num, history_pages))
    start = (history_page_num - 1) * page_size
    end = start + page_size
    history = format_elo_history(raw_history[start:end], name_map)

    model_name = name_map.get(model_id, model_id) if model_id else ""

    return render_template_string(
        HISTORY_TEMPLATE,
        history=history,
        history_page=history_page_num,
        history_pages=history_pages,
        history_total=total_history,
        models_dropdown=dropdown,
        model=model_id,
        model_name=model_name,
        include_inactive=include_inactive,
    )


@app.route("/model/<model_id>")
def model_page(model_id: str):
    index_data = ensure_index()
    detail = get_model_detail(index_data, model_id)
    if detail is None:
        return render_template_string(
            "<h1>404</h1><p>Модель не найдена</p>"
            '<p><a href="/">Назад к рейтингу</a></p>'
        ), 404
    return render_template_string(
        MODEL_TEMPLATE,
        detail=detail,
        chart_svg=build_elo_svg(detail["points"]),
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


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

    # Рекомендации пар (+ строка-обоснование для отображения)
    recommendations = get_recommendations(index_data, top_n=3)
    for rec in recommendations:
        rec["reason"] = format_reason(rec)

    # Топ-3 активных по ELO — для медалей; архивные — для секции
    top_active = sorted(
        (i for i in models.values() if is_model_active(i)),
        key=lambda m: m.get("elo", DEFAULT_ELO),
        reverse=True,
    )
    medals = {info["id"]: rank for rank, info in enumerate(top_active[:3], start=1)}
    archived_list = sorted(
        (info for info in models.values() if not is_model_active(info)),
        key=lambda m: m.get("elo", DEFAULT_ELO),
        reverse=True,
    )

    # Настройки: текущая таска и прогресс покрытия
    settings = load_settings()
    current_task = resolve_current_task(settings)
    task_options = active_tasks(settings)
    coverage = get_coverage(settings)
    coverage_pct = None
    coverage_done = False
    if coverage["percent"] is not None:
        coverage_done = coverage["filled"] >= coverage["total"]
        # Незавершённый прогресс не округляем до «100%» — показываем 99
        coverage_pct = 100 if coverage_done else min(99, round(coverage["percent"]))
    remaining = coverage["total"] - coverage["filled"]

    # Счётчик вердиктов: новый агрегат, fallback на старый список
    summary = index_data.get("matchups_summary", {})
    if "total" in summary:
        matchups_count = summary["total"]
    else:
        matchups_count = len(index_data.get("matchups_index", []))

    return render_template_string(
        INDEX_TEMPLATE,
        models_sorted=models_sorted,
        models_count=len(models),
        filtered_count=len(models_sorted),
        matchups_count=matchups_count,
        updated=index_data.get("updated", ""),
        models_list=models_list,
        recommendations=recommendations,
        medals=medals,
        medal_icons=["🥇", "🥈", "🥉"],
        archived_list=archived_list,
        current_task=current_task,
        task_options=task_options,
        coverage=coverage,
        coverage_pct=coverage_pct,
        coverage_done=coverage_done,
        remaining=remaining,
        filter=filter_mode,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        format_winrate=format_winrate,
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

    models_path = MODELS_PATH
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
    task = request.form.get("task", "").strip()

    if not model_a or not model_b or not winner:
        return redirect(url_for("leaderboard", error="Выберите обе модели и победителя"))

    if model_a == model_b:
        return redirect(url_for("leaderboard", error="Модели должны различаться"))

    if winner not in ("a", "b", "draw"):
        return redirect(url_for("leaderboard", error="Неверный победитель"))

    if not task:
        return redirect(url_for("leaderboard", error="Укажите таск"))

    try:
        result = record_verdict(
            task=task,
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


@app.route("/settings")
def settings_page():
    settings = load_settings()
    current = resolve_current_task(settings)
    tasks_list = []
    for t in known_tasks(settings):
        info = get_task_info(t)
        if info:
            title = info.get("title", "")
            if not title and info.get("missing"):
                title = "(не заполнено — нажмите Изменить)"
        else:
            title = "(файл не найден)"
        tasks_list.append({
            "id": t,
            "title": title,
            "active": is_task_active(settings, t),
            "current": t == current,
        })
    index_data = ensure_index()
    models = index_data.get("models", {})
    models_active_list, models_archived_list = [], []
    for mid, info in models.items():
        entry = {
            "id": mid,
            "name": info.get("name", mid),
            "elo": info.get("elo", DEFAULT_ELO),
        }
        if is_model_active(info):
            models_active_list.append(entry)
        else:
            models_archived_list.append(entry)
    models_active_list.sort(key=lambda m: m["elo"], reverse=True)
    models_archived_list.sort(key=lambda m: m["elo"], reverse=True)
    matrix = get_answer_matrix(settings)
    # Фильтр строк матрицы: active / all / inactive (по умолчанию active)
    answer_filter = valid_answer_filter(request.args.get("answer_filter"))
    if answer_filter == "active":
        answer_rows = [r for r in matrix["rows"] if r["status"] != "archived"]
    elif answer_filter == "inactive":
        answer_rows = [r for r in matrix["rows"] if r["status"] == "archived"]
    else:
        answer_rows = list(matrix["rows"])
    answer_inactive = [t for t in matrix["tasks"] if t not in matrix["active_tasks"]]
    return render_template_string(
        SETTINGS_TEMPLATE,
        tasks_list=tasks_list,
        models_total=len(models),
        models_active=len(models_active_list),
        models_archived=len(models_archived_list),
        models_active_list=models_active_list,
        models_archived_list=models_archived_list,
        answer_rows=answer_rows,
        answer_filter=answer_filter,
        answer_active_tasks=matrix["active_tasks"],
        answer_inactive_tasks=answer_inactive,
        answer_filled=matrix["filled"],
        answer_total=matrix["total"],
        answer_remaining=matrix["remaining"],
        answer_has_active=matrix["has_active"],
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


@app.route("/settings", methods=["POST"])
def settings_save():
    # Управление тасками теперь через отдельные POST-роуты /task/<id>/toggle и /current.
    return redirect(url_for("settings_page"))


@app.route("/answer_flags", methods=["POST"])
def save_answer_flags_route():
    """Сохраняет ручной учёт наличия ответов (матрица из /settings)."""
    from elo import load_models_yaml as _load_models

    settings = load_settings()
    all_models = _load_models()
    model_ids = {m["id"] for m in all_models}
    tasks_all = known_tasks(settings)
    active_set = set(active_tasks(settings))

    # Модели вне текущего фильтра в форме скрыты — сохраняем как было.
    answer_filter = valid_answer_filter(
        request.args.get("answer_filter") or request.form.get("answer_filter")
    )
    if answer_filter == "active":
        visible = {m["id"] for m in all_models if m.get("status", "active") != "archived"}
    elif answer_filter == "inactive":
        visible = {m["id"] for m in all_models if m.get("status", "active") == "archived"}
    else:
        visible = set(model_ids)

    submitted = set(request.form.getlist("flag"))
    existing = load_answer_flags()
    new_flags: dict = {}
    for tid in tasks_all:
        for mid in model_ids:
            if tid in active_set and mid in visible:
                val = f"{mid}||{tid}" in submitted
            else:
                # Неактивные таски и скрытые фильтром модели — сохраняем как было.
                val = bool((existing.get(tid) or {}).get(mid, False))
            if val:
                new_flags.setdefault(tid, {})[mid] = True
    save_answer_flags(new_flags)

    matrix = get_answer_matrix(settings)
    return redirect(url_for(
        "settings_page",
        answer_filter=answer_filter,
        success=f"Учёт ответов сохранён: закрыто {matrix['filled']} из {matrix['total']}.",
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
        "model_page",
        model_id=model_id,
        success=f"Модель «{name}» обновлена, статус: {status_label}.",
    ))


@app.route("/add_task")
def add_task_page():
    return render_template_string(
        ADD_TASK_TEMPLATE,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


@app.route("/add_task", methods=["POST"])
def add_task():
    title = request.form.get("title", "").strip()
    slug = request.form.get("slug", "").strip()
    project = request.form.get("project", "").strip()
    baseline = request.form.get("baseline", "").strip()

    try:
        result = create_task(title, slug, project, baseline)
    except ValueError as e:
        return redirect(url_for("add_task_page", error=str(e)))

    index_data = generate_index()
    save_index(index_data)
    return redirect(url_for("settings_page", success=f"Таска {result['id']} добавлена."))


@app.route("/edit_task/<task_id>")
def edit_task_page(task_id: str):
    info = get_task_info(task_id)
    if not info:
        return redirect(url_for("settings_page", error="Таска не найдена"))
    return render_template_string(
        EDIT_TASK_TEMPLATE,
        task=info,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


@app.route("/edit_task/<task_id>", methods=["POST"])
def edit_task(task_id: str):
    title = request.form.get("title", "").strip()
    project = request.form.get("project", "").strip()
    baseline = request.form.get("baseline", "").strip()
    body = request.form.get("body", "")

    if not title:
        return redirect(url_for("edit_task_page", task_id=task_id, error="Введите название"))

    if not update_task(task_id, title, project, baseline, body):
        return redirect(url_for("settings_page", error="Не удалось обновить таску"))

    index_data = generate_index()
    save_index(index_data)
    return redirect(url_for("settings_page", success=f"Таска {task_id} обновлена."))


@app.route("/task/<task_id>/toggle", methods=["POST"])
def toggle_task(task_id: str):
    answer_filter = valid_answer_filter(request.form.get("answer_filter"))
    if not toggle_task_status(task_id):
        return redirect(url_for("settings_page", answer_filter=answer_filter, error="Не удалось переключить статус"))
    index_data = generate_index()
    save_index(index_data)
    return redirect(url_for("settings_page", answer_filter=answer_filter, success=f"Статус {task_id} изменён"))


@app.route("/task/<task_id>/current", methods=["POST"])
def set_current_task_route(task_id: str):
    answer_filter = valid_answer_filter(request.form.get("answer_filter"))
    if not set_current_task(task_id):
        return redirect(url_for("settings_page", answer_filter=answer_filter, error="Таска должна быть активной"))
    return redirect(url_for("settings_page", answer_filter=answer_filter, success=f"Текущая таска: {task_id}"))


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
