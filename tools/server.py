#!/usr/bin/env python3
"""
server.py — локальный веб-сервер для бенчмарка LLM-моделей.

Предоставляет:
  - Leaderboard (таблица ELO-рейтинга с фильтром архивных)
  - Форму записи вердикта (попарное сравнение)
  - Блок рекомендации следующей пары (pairing algorithm)

Запуск:
    python tools/server.py
    → http://localhost:5000

Зависимости: Flask, PyYAML (опц., для models.yaml).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Добавляем tools/ в path для импорта elo.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import (
    generate_index, save_index, load_models_yaml, load_matchups,
    is_index_stale, DEFAULT_ELO, REPO_ROOT,
)

from flask import Flask, request, redirect, url_for, render_template_string

app = Flask(__name__)

ANSWERS_DIR = REPO_ROOT / "answers"
MATCHUPS_DIR = REPO_ROOT / "matchups"
TASKS_DIR = REPO_ROOT / "tasks"


# ─── Pairing algorithm (tasks 4.1-4.4) ──────────────────────────────


def get_answers_for_task(task_id: str) -> list[str]:
    """Возвращает список model_id, у которых есть ответ на задачу."""
    task_answers = ANSWERS_DIR / task_id
    if not task_answers.exists():
        return []
    return sorted(
        f.stem for f in task_answers.glob("*.md")
        if not f.name.startswith("_")
    )


def get_existing_matchups_for_task(task_id: str) -> set[tuple[str, str]]:
    """Возвращает множество уже оценённых пар (frozenset{a, b}) для задачи."""
    task_matchups = MATCHUPS_DIR / task_id
    if not task_matchups.exists():
        return set()
    pairs = set()
    for f in task_matchups.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            a, b = data.get("model_a"), data.get("model_b")
            if a and b:
                pairs.add(frozenset({a, b}))
        except (json.JSONDecodeError, OSError):
            continue
    return pairs


def get_active_models() -> dict[str, dict]:
    """Возвращает {id: model_dict} только active-моделей."""
    models = load_models_yaml()
    return {
        m["id"]: m for m in models
        if m.get("status", "active") == "active"
    }


def get_model_games(index_data: dict) -> dict[str, int]:
    """Возвращает {model_id: games_count} из index.json."""
    models = index_data.get("models", {})
    return {mid: info.get("games", 0) for mid, info in models.items()}


def get_model_elo(index_data: dict) -> dict[str, int]:
    """Возвращает {model_id: elo} из index.json."""
    models = index_data.get("models", {})
    return {mid: info.get("elo", DEFAULT_ELO) for mid, info in models.items()}


def collect_pair_candidates(index_data: dict) -> list[dict]:
    """Собирает все неоценённые пары для всех задач с ≥2 active-ответами.

    Task 4.1: источник пар
    Task 4.2: фильтрация архивных и уже оценённых
    """
    active = get_active_models()
    elo_map = get_model_elo(index_data)
    games_map = get_model_games(index_data)

    candidates = []

    # Сканируем задачи
    if not TASKS_DIR.exists():
        return candidates

    for task_dir in sorted(TASKS_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name.startswith("_"):
            continue
        task_id = task_dir.name.split("-")[0]  # T-001-slug → T-001

        answers = get_answers_for_task(task_id)
        # Фильтр: только active-модели (task 4.2)
        active_answers = [a for a in answers if a in active]
        if len(active_answers) < 2:
            continue

        existing_pairs = get_existing_matchups_for_task(task_id)

        # Генерируем все неоценённые пары
        for i in range(len(active_answers)):
            for j in range(i + 1, len(active_answers)):
                a, b = active_answers[i], active_answers[j]
                pair_key = frozenset({a, b})
                if pair_key in existing_pairs:
                    continue  # task 4.2: уже оценена

                elo_a = elo_map.get(a, DEFAULT_ELO)
                elo_b = elo_map.get(b, DEFAULT_ELO)
                games_a = games_map.get(a, 0)
                games_b = games_map.get(b, 0)

                # Композитный score (task 4.3)
                undersampled = 1.0 / (1.0 + min(games_a, games_b))
                elo_diff = abs(elo_a - elo_b)
                close_elo = 1.0 / (1.0 + elo_diff / 100.0)
                few_games = 1.0 / (1.0 + min(games_a, games_b) / 10.0)

                score = 0.5 * undersampled + 0.3 * close_elo + 0.2 * few_games

                # Определение причины (task 4.4)
                if min(games_a, games_b) < 3:
                    reason = "новая модель (калибровка)"
                elif elo_diff < 50:
                    reason = f"близкий ELO (разница {elo_diff})"
                else:
                    reason = f"мало голосов (всего {min(games_a, games_b)})"

                candidates.append({
                    "task": task_id,
                    "model_a": a,
                    "model_b": b,
                    "elo_a": elo_a,
                    "elo_b": elo_b,
                    "score": score,
                    "reason": reason,
                })

    # Сортировка по score (убывание)
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def best_pair_recommendation(index_data: dict) -> dict | None:
    """Возвращает лучшую пару для сравнения или None."""
    candidates = collect_pair_candidates(index_data)
    return candidates[0] if candidates else None


# ─── Data loading ───────────────────────────────────────────────────


def ensure_index() -> dict:
    """Загружает index.json, пересчитывает если устарел."""
    if is_index_stale():
        data = generate_index()
        save_index(data)
        return data
    return json.loads((REPO_ROOT / "index.json").read_text(encoding="utf-8"))


def get_tasks_with_answers() -> list[tuple[str, str]]:
    """Возвращает [(task_id, display_name)] для задач с ≥1 ответом."""
    result = []
    if not TASKS_DIR.exists():
        return result
    for d in sorted(TASKS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        task_id = d.name.split("-")[0]
        answers = get_answers_for_task(task_id)
        if len(answers) >= 2:
            # Читаем title из task.md
            title = task_id
            task_file = d / "task.md"
            if task_file.exists():
                import re
                text = task_file.read_text(encoding="utf-8")
                m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
                if m:
                    title = m.group(1).strip().strip('"').strip("'")
            result.append((task_id, f"{task_id} — {title}"))
    return result


# ─── HTML template ──────────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ELO Benchmark — Leaderboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; padding: 20px; max-width: 1200px; margin: 0 auto; }
  h1 { margin-bottom: 20px; color: #1a1a2e; }
  h2 { margin: 30px 0 15px; color: #1a1a2e; border-bottom: 2px solid #ddd; padding-bottom: 8px; }
  table { width: 100%; border-collapse: collapse; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
  th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #1a1a2e; color: white; font-weight: 600; }
  tr:hover { background: #f0f4ff; }
  .archived { color: #999; font-style: italic; }
  .rank { font-weight: bold; color: #666; }
  .elo { font-weight: bold; font-size: 1.1em; }
  .elo-high { color: #2e7d32; }
  .elo-mid { color: #f57f17; }
  .elo-low { color: #c62828; }
  .controls { margin-bottom: 20px; }
  .controls label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  .recommendation { background: #e8f5e9; border: 1px solid #4caf50; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
  .recommendation h3 { color: #2e7d32; margin-bottom: 8px; }
  .recommendation .pair { font-size: 1.15em; font-weight: bold; margin: 8px 0; }
  .recommendation .reason { color: #555; font-size: 0.95em; }
  .recommendation button { margin-top: 10px; padding: 8px 20px; background: #4caf50; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1em; }
  .recommendation button:hover { background: #388e3c; }
  .verdict-form { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin-bottom: 20px; }
  .verdict-form select, .verdict-form input[type="radio"] { margin: 5px 0 15px; }
  .verdict-form select { padding: 8px; font-size: 1em; width: 100%; max-width: 400px; }
  .verdict-form .radio-group { display: flex; gap: 20px; margin: 10px 0 15px; }
  .verdict-form .radio-group label { display: inline-flex; align-items: center; gap: 6px; }
  .verdict-form button { padding: 10px 30px; background: #1a1a2e; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1em; }
  .verdict-form button:hover { background: #2a2a4e; }
  .verdict-form button:disabled { background: #ccc; cursor: not-allowed; }
  .error { color: #c62828; margin: 10px 0; }
  .success { color: #2e7d32; margin: 10px 0; }
  .stats { color: #666; font-size: 0.9em; margin-bottom: 20px; }
</style>
</head>
<body>
<h1>ELO Benchmark — Leaderboard</h1>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}
{% if success %}
<div class="success">{{ success }}</div>
{% endif %}

<div class="stats">
  Всего моделей: {{ models_count }} · Вердиктов: {{ matchups_count }} · Обновлено: {{ updated }}
</div>

{% if recommendation %}
<div class="recommendation" id="recommendation">
  <h3>Рекомендуемая пара для сравнения</h3>
  <div class="pair">Задача {{ recommendation.task }} | {{ recommendation.model_a }} (ELO {{ recommendation.elo_a }}) vs {{ recommendation.model_b }} (ELO {{ recommendation.elo_b }})</div>
  <div class="reason">Причина: {{ recommendation.reason }}</div>
  <button onclick="fillForm('{{ recommendation.task }}', '{{ recommendation.model_a }}', '{{ recommendation.model_b }}')">Сравнить</button>
</div>
{% else %}
<div class="recommendation" style="background: #f5f5f5; border-color: #ccc;">
  <h3 style="color: #666;">Все пары оценены</h3>
  <div class="reason">Создайте новую задачу или добавьте модель.</div>
</div>
{% endif %}

<h2>Рейтинг моделей</h2>
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
    {% for m in models_sorted %}
    <tr class="{{ 'archived' if m.status == 'archived' else '' }}" data-archived="{{ 'true' if m.status == 'archived' else 'false' }}">
      <td class="rank">{{ loop.index }}</td>
      <td>{{ m.name }}</td>
      <td>{{ m.provider }}</td>
      <td class="elo {{ 'elo-high' if m.elo >= 1300 else ('elo-mid' if m.elo >= 1150 else 'elo-low') }}">{{ m.elo }}</td>
      <td>{{ m.wins }}</td>
      <td>{{ m.losses }}</td>
      <td>{{ m.draws }}</td>
      <td>{{ m.games }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<h2>Записать вердикт</h2>
<form class="verdict-form" method="POST" action="/verdict" id="verdictForm">
  <label for="task">Задача:</label><br>
  <select name="task" id="taskSelect" onchange="updateModelDropdowns()">
    <option value="">— выберите задачу —</option>
    {% for task_id, task_name in tasks_with_answers %}
    <option value="{{ task_id }}">{{ task_name }}</option>
    {% endfor %}
  </select><br>

  <label for="model_a">Модель A:</label><br>
  <select name="model_a" id="modelA" disabled>
    <option value="">— сначала выберите задачу —</option>
  </select><br>

  <label for="model_b">Модель B:</label><br>
  <select name="model_b" id="modelB" disabled>
    <option value="">— сначала выберите задачу —</option>
  </select><br>

  <label>Победитель:</label>
  <div class="radio-group">
    <label><input type="radio" name="winner" value="a" required> Модель A</label>
    <label><input type="radio" name="winner" value="b"> Модель B</label>
    <label><input type="radio" name="winner" value="draw"> Ничья</label>
  </div>

  <button type="submit" id="submitBtn" disabled>Записать</button>
</form>

<script>
// Данные для динамических dropdown
const taskAnswers = {{ task_answers_json | safe }};

function updateModelDropdowns() {
  const task = document.getElementById('taskSelect').value;
  const modelA = document.getElementById('modelA');
  const modelB = document.getElementById('modelB');
  const submitBtn = document.getElementById('submitBtn');

  if (!task || !taskAnswers[task]) {
    modelA.innerHTML = '<option value="">— сначала выберите задачу —</option>';
    modelB.innerHTML = '<option value="">— сначала выберите задачу —</option>';
    modelA.disabled = modelB.disabled = true;
    submitBtn.disabled = true;
    return;
  }

  const answers = taskAnswers[task];
  const options = '<option value="">— выберите модель —</option>' +
    answers.map(a => '<option value="' + a + '">' + a + '</option>').join('');
  modelA.innerHTML = options;
  modelB.innerHTML = options;
  modelA.disabled = modelB.disabled = false;
  validateForm();
}

function validateForm() {
  const a = document.getElementById('modelA').value;
  const b = document.getElementById('modelB').value;
  const task = document.getElementById('taskSelect').value;
  const submitBtn = document.getElementById('submitBtn');
  submitBtn.disabled = !(a && b && task && a !== b);
}

document.addEventListener('change', validateForm);

function toggleArchived() {
  const show = document.getElementById('showArchived').checked;
  document.querySelectorAll('#leaderboard tbody tr').forEach(row => {
    if (row.dataset.archived === 'true') {
      row.style.display = show ? '' : 'none';
    }
  });
}

// Скрываем архивные при загрузке
document.addEventListener('DOMContentLoaded', () => {
  toggleArchived();
});

function fillForm(task, a, b) {
  document.getElementById('taskSelect').value = task;
  updateModelDropdowns();
  document.getElementById('modelA').value = a;
  document.getElementById('modelB').value = b;
  validateForm();
  document.getElementById('verdictForm').scrollIntoView({ behavior: 'smooth' });
}
</script>
</body>
</html>
"""


# ─── Routes ─────────────────────────────────────────────────────────


@app.route("/")
def leaderboard():
    index_data = ensure_index()

    # Сортировка моделей по ELO (убывание)
    models = index_data.get("models", {})
    models_sorted = sorted(
        models.values(), key=lambda m: m.get("elo", DEFAULT_ELO), reverse=True
    )

    # Задачи с ≥2 ответами (для dropdown)
    tasks_list = get_tasks_with_answers()

    # task_answers для JS: {task_id: [model_ids]}
    task_answers = {}
    for task_id, _ in tasks_list:
        task_answers[task_id] = get_answers_for_task(task_id)

    # Рекомендация пары
    rec = best_pair_recommendation(index_data)

    return render_template_string(
        HTML_TEMPLATE,
        models_sorted=models_sorted,
        models_count=len(models),
        matchups_count=len(index_data.get("matchups_index", [])),
        updated=index_data.get("updated", ""),
        tasks_with_answers=tasks_list,
        task_answers_json=json.dumps(task_answers),
        recommendation=rec,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
    )


@app.route("/verdict", methods=["POST"])
def record_verdict():
    task = request.form.get("task", "").strip()
    model_a = request.form.get("model_a", "").strip()
    model_b = request.form.get("model_b", "").strip()
    winner = request.form.get("winner", "").strip()

    # Валидация
    if not task or not model_a or not model_b or not winner:
        return redirect(url_for("leaderboard", error="Все поля обязательны"))

    if model_a == model_b:
        return redirect(url_for("leaderboard", error="Модели должны различаться"))

    if winner not in ("a", "b", "draw"):
        return redirect(url_for("leaderboard", error="Неверный победитель"))

    # Проверка моделей в реестре
    models = load_models_yaml()
    model_ids = {m["id"] for m in models}
    if model_a not in model_ids:
        return redirect(url_for("leaderboard", error=f"Модель {model_a} не найдена в реестре"))
    if model_b not in model_ids:
        return redirect(url_for("leaderboard", error=f"Модель {model_b} не найдена в реестре"))

    # Проверка наличия ответов
    answers = get_answers_for_task(task)
    if model_a not in answers:
        return redirect(url_for("leaderboard", error=f"У модели {model_a} нет ответа на задачу {task}"))
    if model_b not in answers:
        return redirect(url_for("leaderboard", error=f"У модели {model_b} нет ответа на задачу {task}"))

    # Запись вердикта
    task_matchups_dir = MATCHUPS_DIR / task
    task_matchups_dir.mkdir(parents=True, exist_ok=True)

    # Определение следующего номера
    existing = sorted(task_matchups_dir.glob("*.json"))
    next_num = len(existing) + 1
    matchup_file = task_matchups_dir / f"{next_num:03d}.json"

    verdict = {
        "task": task,
        "model_a": model_a,
        "model_b": model_b,
        "winner": winner,
        "date": date.today().isoformat(),
    }

    matchup_file.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Пересчёт ELO + обновление index.json
    index_data = generate_index()
    save_index(index_data)

    return redirect(url_for("leaderboard", success=f"Вердикт записан: {model_a} vs {model_b}, победитель: {winner}"))


# ─── Port handling (task 3.9) ───────────────────────────────────────


def find_free_port(start: int = 5000, max_tries: int = 10) -> int:
    """Находит свободный порт начиная с start."""
    import socket
    for port in range(start, start + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start  # fallback


# ─── Main ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = find_free_port()
    print(f"ELO Benchmark сервер: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
