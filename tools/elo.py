#!/usr/bin/env python3
"""
elo.py — ELO-движок для бенчмарка LLM-моделей.

Пересчитывает рейтинги из попарных вердиктов (matchups/) с адаптивным K-factor.
Сохраняет результаты в index.json.

Использование:
    python tools/elo.py                    # пересчёт + запись index.json
    python tools/elo.py --check            # только проверка целостности (без записи)

Зависимости: только stdlib.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
MATCHUPS_DIR = REPO_ROOT / "matchups"
INDEX_PATH = REPO_ROOT / "index.json"

DEFAULT_ELO = 1200


# ─── Core ELO math (tasks 2.1, 2.2, 2.3, 2.6) ───────────────────────


def expected_score(r_a: float, r_b: float) -> float:
    """E_A = 1 / (1 + 10^((R_B - R_A) / 400))."""
    return 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))


def k_factor(games: int) -> int:
    """Адаптивный K-factor: <10 → 40, 10–30 → 32, >30 → 24."""
    if games < 10:
        return 40
    if games <= 30:
        return 32
    return 24


def round_elo(value: float) -> int:
    """Округление до целого (round half to even — banker's rounding)."""
    return int(round(value))


def update_elo(
    r_a: float, k_a: int, s_a: float, e_a: float,
    r_b: float, k_b: int, s_b: float, e_b: float,
) -> tuple[int, int]:
    """Обновляет ELO обеих моделей. Возвращает (new_r_a, new_r_b) — целые."""
    new_a = round_elo(r_a + k_a * (s_a - e_a))
    new_b = round_elo(r_b + k_b * (s_b - e_b))
    return new_a, new_b


# ─── Loading data ───────────────────────────────────────────────────


def load_matchups() -> list[dict]:
    """Загружает все вердикты из matchups/ в хронологическом порядке.

    Порядок: по дате (поле date), затем по имени файла (NNN) внутри задачи.
    """
    matchups = []
    if not MATCHUPS_DIR.exists():
        return matchups

    for task_dir in sorted(MATCHUPS_DIR.iterdir()):
        if not task_dir.is_dir():
            continue
        for f in sorted(task_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data["_file"] = str(f.relative_to(REPO_ROOT))
                data["_matchup_id"] = f"{task_dir.name}/{f.stem}"
                matchups.append(data)
            except (json.JSONDecodeError, OSError) as e:
                print(f"WARNING: не удалось прочитать {f}: {e}", file=sys.stderr)

    # Сортировка по дате, затем по _matchup_id (стабильная)
    matchups.sort(key=lambda m: (m.get("date", ""), m.get("_matchup_id", "")))
    return matchups


# ─── Full recalculation (tasks 2.4, 2.5) ────────────────────────────


def recalculate(matchups: list[dict], model_ids: list[str]) -> dict:
    """Полный пересчёт ELO из всех вердиктов.

    Возвращает dict:
      models: {id: {elo, games, wins, losses, draws}}
      elo_history: [{model, date, elo, delta, after_matchup}]
    """
    # Инициализация
    elo: dict[str, int] = {mid: DEFAULT_ELO for mid in model_ids}
    stats: dict[str, dict] = {
        mid: {"games": 0, "wins": 0, "losses": 0, "draws": 0} for mid in model_ids
    }
    history: list[dict] = []

    for mu in matchups:
        a = mu.get("model_a")
        b = mu.get("model_b")
        winner = mu.get("winner")
        mu_date = mu.get("date", "")
        mu_id = mu.get("_matchup_id", "")

        # Пропускаем вердикты с неизвестными моделями
        if a not in elo or b not in elo:
            continue

        r_a = elo[a]
        r_b = elo[b]
        games_a = stats[a]["games"]
        games_b = stats[b]["games"]
        k_a = k_factor(games_a)
        k_b = k_factor(games_b)
        e_a = expected_score(r_a, r_b)
        e_b = 1.0 - e_a

        if winner == "a":
            s_a, s_b = 1.0, 0.0
        elif winner == "b":
            s_a, s_b = 0.0, 1.0
        elif winner == "draw":
            s_a, s_b = 0.5, 0.5
        else:
            print(f"WARNING: неизвестный winner '{winner}' в {mu_id}", file=sys.stderr)
            continue

        new_a, new_b = update_elo(r_a, k_a, s_a, e_a, r_b, k_b, s_b, e_b)

        delta_a = new_a - r_a
        delta_b = new_b - r_b

        elo[a] = new_a
        elo[b] = new_b

        stats[a]["games"] += 1
        stats[b]["games"] += 1
        if winner == "a":
            stats[a]["wins"] += 1
            stats[b]["losses"] += 1
        elif winner == "b":
            stats[a]["losses"] += 1
            stats[b]["wins"] += 1
        else:
            stats[a]["draws"] += 1
            stats[b]["draws"] += 1

        history.append({
            "model": a, "date": mu_date, "elo": new_a, "delta": delta_a,
            "after_matchup": mu_id,
        })
        history.append({
            "model": b, "date": mu_date, "elo": new_b, "delta": delta_b,
            "after_matchup": mu_id,
        })

    # Собираем результат
    models_out = {}
    for mid in model_ids:
        models_out[mid] = {
            "elo": elo[mid],
            "games": stats[mid]["games"],
            "wins": stats[mid]["wins"],
            "losses": stats[mid]["losses"],
            "draws": stats[mid]["draws"],
        }

    return {"models": models_out, "elo_history": history}


# ─── Index.json generation ──────────────────────────────────────────


def load_models_yaml() -> list[dict]:
    """Парсит models.yaml — возвращает список моделей (id, name, provider, status)."""
    models_path = REPO_ROOT / "models.yaml"
    if not models_path.exists():
        return []

    import re
    text = models_path.read_text(encoding="utf-8")
    m = re.search(r"^models:[ \t]*(.*)$", text, re.MULTILINE)
    if not m:
        return []

    body = text[m.end():]
    entries = re.findall(
        r"^\s*-\s+id:\s*(.+?)(?=^\s*-\s+id:|\Z)",
        body, re.MULTILINE | re.DOTALL,
    )

    models = []
    for entry in entries:
        model = {}
        lines = entry.strip().splitlines()
        if lines:
            first = lines[0].strip()
            if ":" not in first:
                model["id"] = first
                lines = lines[1:]
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                model[key] = val
        if model.get("id"):
            model.setdefault("status", "active")
            models.append(model)
    return models


def collect_tasks_info() -> dict:
    """Собирает сводку по задачам из tasks/ и answers/."""
    tasks_dir = REPO_ROOT / "tasks"
    answers_dir = REPO_ROOT / "answers"
    matchups_dir = REPO_ROOT / "matchups"

    tasks_info = {}

    # Сканируем tasks/
    if tasks_dir.exists():
        for d in sorted(tasks_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            task_id = d.name.split("-")[0]  # T-001-slug → T-001
            task_file = d / "task.md"
            title = ""
            if task_file.exists():
                import re
                text = task_file.read_text(encoding="utf-8")
                m = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
                if m:
                    title = m.group(1).strip().strip('"').strip("'")

            # Подсчёт ответов
            answers = []
            if answers_dir.exists():
                task_answers = answers_dir / task_id
                if task_answers.exists():
                    answers = sorted(
                        f.stem for f in task_answers.glob("*.md")
                        if not f.name.startswith("_")
                    )

            # Подсчёт вердиктов
            matchups_count = 0
            if matchups_dir.exists():
                task_matchups = matchups_dir / task_id
                if task_matchups.exists():
                    matchups_count = len(list(task_matchups.glob("*.json")))

            tasks_info[task_id] = {
                "slug": d.name,
                "title": title,
                "answers": answers,
                "matchups_count": matchups_count,
            }

    return tasks_info


def build_matchups_index(matchups: list[dict]) -> list[dict]:
    """Сводка вердиктов для index.json (без _file, _matchup_id)."""
    result = []
    for mu in matchups:
        result.append({
            "id": mu.get("_matchup_id", ""),
            "task": mu.get("task", ""),
            "model_a": mu.get("model_a", ""),
            "model_b": mu.get("model_b", ""),
            "winner": mu.get("winner", ""),
            "date": mu.get("date", ""),
        })
    return result


def generate_index() -> dict:
    """Полная генерация index.json."""
    models = load_models_yaml()
    model_ids = [m["id"] for m in models]
    matchups = load_matchups()
    elo_data = recalculate(matchups, model_ids)

    # Объединяем метаданные моделей с ELO
    models_out = {}
    for m in models:
        mid = m["id"]
        elo_info = elo_data["models"].get(mid, {
            "elo": DEFAULT_ELO, "games": 0, "wins": 0, "losses": 0, "draws": 0,
        })
        models_out[mid] = {
            "name": m.get("name", ""),
            "provider": m.get("provider", ""),
            "status": m.get("status", "active"),
            "elo": elo_info["elo"],
            "games": elo_info["games"],
            "wins": elo_info["wins"],
            "losses": elo_info["losses"],
            "draws": elo_info["draws"],
        }

    tasks_info = collect_tasks_info()
    matchups_idx = build_matchups_index(matchups)

    return {
        "version": 1,
        "updated": date.today().isoformat(),
        "models": models_out,
        "tasks": tasks_info,
        "matchups_index": matchups_idx,
        "elo_history": elo_data["elo_history"],
    }


def save_index(data: dict) -> None:
    """Записывает index.json."""
    INDEX_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── Integrity check ────────────────────────────────────────────────


def is_index_stale() -> bool:
    """Проверяет, устарел ли index.json vs файлы в matchups/."""
    if not INDEX_PATH.exists():
        return True
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True

    # Сравниваем количество вердиктов
    indexed_count = len(idx.get("matchups_index", []))
    actual_matchups = load_matchups()
    if indexed_count != len(actual_matchups):
        return True

    # Проверяем модели
    indexed_models = set(idx.get("models", {}).keys())
    yaml_models = {m["id"] for m in load_models_yaml()}
    if indexed_models != yaml_models:
        return True

    return False


# ─── CLI ────────────────────────────────────────────────────────────


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="ELO-движок бенчмарка")
    parser.add_argument("--check", action="store_true",
                        help="Только проверить целостность (без записи)")
    args = parser.parse_args()

    if args.check:
        stale = is_index_stale()
        if stale:
            print("index.json устарел или отсутствует — нужен пересчёт.")
            return 1
        print("index.json актуален.")
        return 0

    data = generate_index()
    save_index(data)

    models_count = len(data["models"])
    matchups_count = len(data["matchups_index"])
    print(f"index.json обновлён: {models_count} моделей, {matchups_count} вердиктов.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
