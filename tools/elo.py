#!/usr/bin/env python3
"""
elo.py — ELO-движок и журнал вердиктов для бенчмарка LLM-моделей.

Вердикты — append-only журнал событий в matchups/<task>/NNN.json.
Каждое событие (версия 2) содержит:
  seq         — глобальный монотонный номер (порядок реплея)
  recorded_at — ISO 8601 с таймзоной (ставит инструмент, не человек)
  model_a/model_b       — как записано (слот modelA/modelB или id)
  model_a_id/model_b_id — разрешённые id из models.yaml
  elo_before/elo_after/delta — снэпшот рейтинга на момент записи
  void_of     — (tombstone) id аннулируемого вердикта, сам игр не создаёт

Порядок реплея: события с seq — строго по seq; события без seq —
легаси, сортируются по (date, matchup_id) и идут ДО событий с seq.
--check проверяет: снэпшоты сходятся с реплеем (детект правки истории),
seq уникален, recorded_at неубывает вместе с seq, модели разрешимы.

index.json — производная проекция, всегда пересчитывается из журнала.

Использование:
    python tools/elo.py                    # пересчёт + запись index.json
    python tools/elo.py --check            # проверка целостности (без записи)

Зависимости: только stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
MATCHUPS_DIR = REPO_ROOT / "matchups"
ANSWERS_DIR = REPO_ROOT / "answers"
INDEX_PATH = REPO_ROOT / "index.json"
STATE_PATH = MATCHUPS_DIR / "state.json"

DEFAULT_ELO = 1200
VERDICT_VERSION = 2
SLOT_NAMES = ("modelA", "modelB")

TASK_ID_RE = re.compile(r"^(T-\d+)")


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


def now_iso() -> str:
    """Текущее время в ISO 8601 с таймзоной, до секунд."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ─── Loading data ───────────────────────────────────────────────────


def matchup_sort_key(mu: dict):
    """Ключ сортировки реплея.

    События с seq идут строго по seq. События без seq — легаси:
    сортируются по (date, matchup_id) и располагаются ДО событий с seq.
    """
    seq = mu.get("seq")
    if seq is not None:
        return (1, int(seq), "")
    return (0, mu.get("date", ""), mu.get("_matchup_id", ""))


def load_matchups() -> list[dict]:
    """Загружает все вердикты из matchups/ в порядке реплея.

    Порядок: seq (события v2), затем легаси по (date, matchup_id).
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

    matchups.sort(key=matchup_sort_key)
    return matchups


def matchups_digest() -> str:
    """sha256 над содержимым всех файлов вердиктов (путь + байты).

    Используется для инвалидации index.json: любая правка/удаление/
    переименование файла в matchups/ меняет дайджест.
    """
    h = hashlib.sha256()
    if not MATCHUPS_DIR.exists():
        return h.hexdigest()
    files = sorted(
        p for p in MATCHUPS_DIR.rglob("*.json")
        if p.name != STATE_PATH.name
    )
    for p in files:
        h.update(str(p.relative_to(REPO_ROOT)).encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(p.read_bytes())
        except OSError:
            continue
        h.update(b"\0")
    return h.hexdigest()


# ─── Slot resolution ────────────────────────────────────────────────


def load_slots_map(task_id: str) -> dict:
    """Читает answers/<task_id>/slots.json → {modelA: <id>, modelB: <id>}."""
    path = ANSWERS_DIR / task_id / "slots.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data.get("slots", {}) if isinstance(data, dict) else {}


def resolve_matchup_models(mu: dict, model_ids: set[str]) -> tuple[str | None, str | None]:
    """Разрешает моделей вердикта в реальные id.

    Приоритет:
      1. model_a_id / model_b_id (записано инструментом при создании)
      2. model_a / model_b, если это уже id из реестра
      3. слот (modelA/modelB) → answers/<task>/slots.json (легаси-вердикты)
    Возвращает (id_a, id_b); неразрешённый — None.
    """
    slots_cache = {}

    def resolve(side: str) -> str | None:
        rid = mu.get(f"model_{side}_id")
        if rid:
            return rid if rid in model_ids else None
        raw = mu.get(f"model_{side}")
        if raw in model_ids:
            return raw
        if raw in SLOT_NAMES:
            task = mu.get("task", "")
            if task not in slots_cache:
                slots_cache[task] = load_slots_map(task)
            rid = slots_cache[task].get(raw)
            if rid and rid in model_ids:
                return rid
        return None

    return resolve("a"), resolve("b")


# ─── Ledger write path ──────────────────────────────────────────────


def load_state() -> dict:
    """matchups/state.json — {next_seq}. Самовосстановление по max(seq)+1."""
    state = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
    max_seq = 0
    for mu in load_matchups():
        if mu.get("seq") is not None:
            max_seq = max(max_seq, int(mu["seq"]))
    next_seq = max(int(state.get("next_seq", 0) or 0), max_seq + 1)
    return {"next_seq": next_seq}


def save_state(state: dict) -> None:
    MATCHUPS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, STATE_PATH)


def next_matchup_path(task: str) -> Path:
    """Следующий matchups/<task>/NNN.json — max существующих + 1."""
    task_dir = MATCHUPS_DIR / task
    task_dir.mkdir(parents=True, exist_ok=True)
    max_n = 0
    for f in task_dir.glob("*.json"):
        if f.stem.isdigit():
            max_n = max(max_n, int(f.stem))
    return task_dir / f"{max_n + 1:03d}.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _current_elo_state(model_ids: list[str]) -> tuple[dict, dict]:
    """Реплей текущего журнала → (elo, stats). Нужно для снэпшота."""
    matchups = load_matchups()
    elo: dict[str, int] = {mid: DEFAULT_ELO for mid in model_ids}
    stats: dict[str, dict] = {
        mid: {"games": 0, "wins": 0, "losses": 0, "draws": 0} for mid in model_ids
    }
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
    for mu in matchups:
        if mu.get("void_of") or mu["_matchup_id"] in voided:
            continue
        a, b = resolve_matchup_models(mu, set(model_ids))
        if not a or not b:
            continue
        winner = mu.get("winner")
        if winner not in ("a", "b", "draw"):
            continue
        s_a, s_b = (1.0, 0.0) if winner == "a" else (0.0, 1.0) if winner == "b" else (0.5, 0.5)
        e_a = expected_score(elo[a], elo[b])
        elo[a], elo[b] = update_elo(
            elo[a], k_factor(stats[a]["games"]), s_a, e_a,
            elo[b], k_factor(stats[b]["games"]), s_b, 1.0 - e_a,
        )
        stats[a]["games"] += 1
        stats[b]["games"] += 1
    return elo, stats


def record_verdict(
    task: str,
    model_a: str,
    model_b: str,
    winner: str,
    *,
    recorded_at: str | None = None,
    regenerate_index: bool = True,
) -> dict:
    """Записывает вердикт в журнал — ЕДИНСТВЕННАЯ точка записи.

    - Разрешает слоты modelA/modelB через answers/<task>/slots.json.
    - Назначает глобальный seq и штампует recorded_at системным временем.
    - Вычисляет и записывает снэпшот ELO (before/after/delta) — делает
      подмену или вставку задним числом детектируемой через --check.
    - Перегенерирует index.json (если regenerate_index).

    Возвращает dict с path и записанным вердиктом. Бросает ValueError.
    """
    if not re.fullmatch(r"[A-Za-z0-9_-]+", task or ""):
        raise ValueError(f"Некорректный task: '{task}'")
    if winner not in ("a", "b", "draw"):
        raise ValueError(f"winner должен быть a|b|draw, получено '{winner}'")
    if model_a == model_b:
        raise ValueError("Модели A и B должны различаться")

    model_ids = {m["id"] for m in load_models_yaml()}

    # Разрешение слотов в реальные id
    slots = load_slots_map(task)
    id_a = model_a if model_a in model_ids else slots.get(model_a)
    id_b = model_b if model_b in model_ids else slots.get(model_b)
    if not id_a or id_a not in model_ids:
        raise ValueError(
            f"Модель A не разрешена: '{model_a}'. "
            f"Либо это не id из models.yaml, либо нет записи в "
            f"answers/{task}/slots.json"
        )
    if not id_b or id_b not in model_ids:
        raise ValueError(
            f"Модель B не разрешена: '{model_b}'. "
            f"Либо это не id из models.yaml, либо нет записи в "
            f"answers/{task}/slots.json"
        )

    # Снэпшот: состояние до вердикта
    elo, stats = _current_elo_state(sorted(model_ids))
    r_a, r_b = elo[id_a], elo[id_b]
    s_a, s_b = (1.0, 0.0) if winner == "a" else (0.0, 1.0) if winner == "b" else (0.5, 0.5)
    e_a = expected_score(r_a, r_b)
    new_a, new_b = update_elo(
        r_a, k_factor(stats[id_a]["games"]), s_a, e_a,
        r_b, k_factor(stats[id_b]["games"]), s_b, 1.0 - e_a,
    )

    state = load_state()
    seq = state["next_seq"]

    verdict = {
        "version": VERDICT_VERSION,
        "seq": seq,
        "task": task,
        "model_a": model_a,
        "model_b": model_b,
        "model_a_id": id_a,
        "model_b_id": id_b,
        "winner": winner,
        "date": date.today().isoformat(),
        "recorded_at": recorded_at or now_iso(),
        "elo": {
            id_a: {"before": r_a, "after": new_a, "delta": new_a - r_a},
            id_b: {"before": r_b, "after": new_b, "delta": new_b - r_b},
        },
    }

    path = next_matchup_path(task)
    _atomic_write_json(path, verdict)
    save_state({"next_seq": seq + 1})

    if regenerate_index:
        save_index(generate_index())

    return {"path": path, "verdict": verdict, "matchup_id": f"{task}/{path.stem}"}


def void_matchup(matchup_id: str, reason: str = "") -> dict:
    """Аннулирует вердикт tombstone-событием (не удаляет файл).

    matchup_id вида 'T-001/001'. Возвращает dict с path нового события.
    """
    if "/" not in matchup_id:
        raise ValueError(f"matchup_id должен быть вида '<task>/<NNN>', получено '{matchup_id}'")
    task = matchup_id.split("/", 1)[0]
    target = MATCHUPS_DIR / f"{matchup_id}.json"
    if not target.exists():
        raise ValueError(f"Вердикт {matchup_id} не найден: {target}")

    state = load_state()
    seq = state["next_seq"]

    tombstone = {
        "version": VERDICT_VERSION,
        "seq": seq,
        "task": task,
        "void_of": matchup_id,
        "reason": reason,
        "date": date.today().isoformat(),
        "recorded_at": now_iso(),
    }
    path = next_matchup_path(task)
    _atomic_write_json(path, tombstone)
    save_state({"next_seq": seq + 1})
    save_index(generate_index())
    return {"path": path, "matchup_id": f"{task}/{path.stem}"}


# ─── Full recalculation (tasks 2.4, 2.5) ────────────────────────────


def recalculate(matchups: list[dict], model_ids: list[str]) -> dict:
    """Полный пересчёт ELO из всех вердиктов в порядке журнала.

    Возвращает dict:
      models: {id: {elo, games, wins, losses, draws}}
      elo_history: [{matchup, seq, date, recorded_at, model_a_id, model_b_id,
                     winner, elo_a, elo_b}, ...]
      warnings: [str]
      applied/voided/tombstone/skipped: списки matchup_id
    """
    elo: dict[str, int] = {mid: DEFAULT_ELO for mid in model_ids}
    stats: dict[str, dict] = {
        mid: {"games": 0, "wins": 0, "losses": 0, "draws": 0} for mid in model_ids
    }
    history: list[dict] = []
    warnings: list[str] = []
    applied: list[str] = []
    skipped: list[str] = []

    model_id_set = set(model_ids)
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
    tombstones = [mu["_matchup_id"] for mu in matchups if mu.get("void_of")]

    for vid in sorted(voided):
        if not any(mu["_matchup_id"] == vid for mu in matchups):
            warnings.append(f"tombstone ссылается на несуществующий вердикт: {vid}")

    for mu in matchups:
        mu_id = mu.get("_matchup_id", "")

        if mu.get("void_of"):
            continue  # tombstone — игру не создаёт
        if mu_id in voided:
            continue  # аннулирован

        a, b = resolve_matchup_models(mu, model_id_set)
        if not a or not b:
            warnings.append(
                f"вердикт {mu_id} пропущен: не разрешены модели "
                f"(model_a='{mu.get('model_a')}', model_b='{mu.get('model_b')}')"
            )
            skipped.append(mu_id)
            continue

        winner = mu.get("winner")
        if winner == "a":
            s_a, s_b = 1.0, 0.0
        elif winner == "b":
            s_a, s_b = 0.0, 1.0
        elif winner == "draw":
            s_a, s_b = 0.5, 0.5
        else:
            warnings.append(f"неизвестный winner '{winner}' в {mu_id} — пропущен")
            skipped.append(mu_id)
            continue

        r_a, r_b = elo[a], elo[b]
        e_a = expected_score(r_a, r_b)
        new_a, new_b = update_elo(
            r_a, k_factor(stats[a]["games"]), s_a, e_a,
            r_b, k_factor(stats[b]["games"]), s_b, 1.0 - e_a,
        )

        elo[a], elo[b] = new_a, new_b
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

        common = {
            "matchup": mu_id,
            "after_matchup": mu_id,  # обратная совместимость
            "seq": mu.get("seq"),
            "date": mu.get("date", ""),
            "recorded_at": mu.get("recorded_at", ""),
        }
        history.append({
            **common,
            "model_a_id": a,
            "model_b_id": b,
            "winner": winner,
            "elo_a": {"before": r_a, "after": new_a, "delta": new_a - r_a},
            "elo_b": {"before": r_b, "after": new_b, "delta": new_b - r_b},
        })
        applied.append(mu_id)

    models_out = {
        mid: {"elo": elo[mid], **stats[mid]} for mid in model_ids
    }

    return {
        "models": models_out,
        "elo_history": history,
        "warnings": warnings,
        "applied": applied,
        "skipped": skipped,
        "voided": sorted(voided),
        "tombstones": tombstones,
    }


def verify_snapshots(matchups: list[dict], model_ids: list[str]) -> list[str]:
    """Сверяет записанные в вердиктах ELO-снэпшоты с реплеем.

    Расхождение = история до этого вердикта была изменена (вставка/
    правка/аннулирование задним числом). Возвращает список проблем.
    """
    problems: list[str] = []
    model_id_set = set(model_ids)
    elo: dict[str, int] = {mid: DEFAULT_ELO for mid in model_ids}
    stats: dict[str, dict] = {mid: {"games": 0} for mid in model_ids}
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}

    seen_seq: set[int] = set()
    prev_dt: str | None = None
    for mu in matchups:
        mu_id = mu.get("_matchup_id", "")
        seq = mu.get("seq")
        if seq is not None:
            if seq in seen_seq:
                problems.append(f"{mu_id}: дубликат seq={seq}")
            seen_seq.add(int(seq))
        else:
            problems.append(f"{mu_id}: нет seq — легаси/записан вне record_verdict.py")

        dt = mu.get("recorded_at")
        if not dt:
            problems.append(f"{mu_id}: отсутствует recorded_at")
        else:
            if prev_dt and dt < prev_dt:
                problems.append(
                    f"{mu_id}: recorded_at '{dt}' раньше предыдущего '{prev_dt}' "
                    f"(нарушен порядок журнала)"
                )
            prev_dt = dt

        if mu.get("void_of") or mu_id in voided:
            continue
        a, b = resolve_matchup_models(mu, model_id_set)
        if not a or not b:
            continue
        winner = mu.get("winner")
        if winner not in ("a", "b", "draw"):
            continue

        s_a, s_b = (1.0, 0.0) if winner == "a" else (0.0, 1.0) if winner == "b" else (0.5, 0.5)
        e_a = expected_score(elo[a], elo[b])
        new_a, new_b = update_elo(
            elo[a], k_factor(stats[a]["games"]), s_a, e_a,
            elo[b], k_factor(stats[b]["games"]), s_b, 1.0 - e_a,
        )

        snap = mu.get("elo")
        if snap:
            for mid, side_new in ((a, new_a), (b, new_b)):
                rec = snap.get(mid)
                if rec and (rec.get("before") != elo[mid] or rec.get("after") != side_new):
                    problems.append(
                        f"{mu_id}: снэпшот {mid} расходится с реплеем "
                        f"(записано {rec.get('before')}→{rec.get('after')}, "
                        f"реплей {elo[mid]}→{side_new}) — история изменена задним числом"
                    )

        elo[a], elo[b] = new_a, new_b
        stats[a]["games"] += 1
        stats[b]["games"] += 1

    return problems


# ─── Index.json generation ──────────────────────────────────────────


def load_models_yaml() -> list[dict]:
    """Парсит models.yaml — возвращает список моделей (id, name, provider, status)."""
    models_path = REPO_ROOT / "models.yaml"
    if not models_path.exists():
        return []

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

    if tasks_dir.exists():
        for d in sorted(tasks_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("_"):
                continue
            # T-001-slug → T-001; если не T-NNN — берём имя целиком
            m = TASK_ID_RE.match(d.name)
            task_id = m.group(1) if m else d.name
            task_file = d / "task.md"
            title = ""
            if task_file.exists():
                text = task_file.read_text(encoding="utf-8")
                m2 = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
                if m2:
                    title = m2.group(1).strip().strip('"').strip("'")

            answers = []
            if answers_dir.exists():
                task_answers = answers_dir / task_id
                if task_answers.exists():
                    answers = sorted(
                        f.stem for f in task_answers.glob("*.md")
                        if not f.name.startswith("_")
                    )

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


def build_matchups_index(matchups: list[dict], applied: set[str],
                         voided: set[str], skipped: set[str]) -> list[dict]:
    """Сводка вердиктов для index.json со статусом и resolved ids."""
    model_ids = {m["id"] for m in load_models_yaml()}
    result = []
    for mu in matchups:
        mu_id = mu.get("_matchup_id", "")
        if mu.get("void_of"):
            status = "tombstone"
        elif mu_id in voided:
            status = "voided"
        elif mu_id in applied:
            status = "applied"
        else:
            status = "skipped"
        a_id, b_id = resolve_matchup_models(mu, model_ids)
        result.append({
            "id": mu_id,
            "seq": mu.get("seq"),
            "task": mu.get("task", ""),
            "model_a": mu.get("model_a", ""),
            "model_b": mu.get("model_b", ""),
            "model_a_id": a_id or "",
            "model_b_id": b_id or "",
            "winner": mu.get("winner", ""),
            "date": mu.get("date", ""),
            "recorded_at": mu.get("recorded_at", ""),
            "status": status,
        })
    return result


def generate_index() -> dict:
    """Полная генерация index.json."""
    models = load_models_yaml()
    model_ids = [m["id"] for m in models]
    matchups = load_matchups()
    elo_data = recalculate(matchups, model_ids)

    for w in elo_data["warnings"]:
        print(f"WARNING: {w}", file=sys.stderr)

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
    matchups_idx = build_matchups_index(
        matchups,
        set(elo_data["applied"]),
        set(elo_data["voided"]),
        set(elo_data["skipped"]),
    )

    return {
        "version": 2,
        "updated": date.today().isoformat(),
        "matchups_digest": matchups_digest(),
        "models": models_out,
        "tasks": tasks_info,
        "matchups_index": matchups_idx,
        "elo_history": elo_data["elo_history"],
    }


def save_index(data: dict) -> None:
    """Записывает index.json (атомарно)."""
    _atomic_write_json(INDEX_PATH, data)


# ─── Integrity check ────────────────────────────────────────────────


def is_index_stale() -> bool:
    """Проверяет, устарел ли index.json vs файлы в matchups/ и models.yaml."""
    if not INDEX_PATH.exists():
        return True
    try:
        idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True

    # Дайджест содержимого вердиктов — ловит правки, не только добавления
    if idx.get("matchups_digest") != matchups_digest():
        return True

    indexed_models = set(idx.get("models", {}).keys())
    yaml_models = {m["id"] for m in load_models_yaml()}
    if indexed_models != yaml_models:
        return True

    # Метаданные моделей (status, name, provider) тоже влияют на UI/рекомендации
    for m in load_models_yaml():
        mid = m["id"]
        info = idx.get("models", {}).get(mid, {})
        for key in ("name", "provider", "status"):
            if info.get(key) != m.get(key, ""):
                return True

    return False


def run_check() -> int:
    """Полная проверка целостности журнала и индекса. Возвращает exit code."""
    problems: list[str] = []

    models = load_models_yaml()
    model_ids = [m["id"] for m in models]
    matchups = load_matchups()

    # Снэпшоты, порядок seq/recorded_at, дубликаты seq
    problems.extend(verify_snapshots(matchups, model_ids))

    # Неразрешённые модели / невалидные winner / void-ссылки
    elo_data = recalculate(matchups, model_ids)
    problems.extend(elo_data["warnings"])

    if is_index_stale():
        problems.append("index.json устарел или отсутствует — нужен пересчёт")

    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        print(f"\nНайдено проблем: {len(problems)}")
        return 1
    print("index.json актуален, журнал вердиктов целостен.")
    return 0


# ─── CLI ────────────────────────────────────────────────────────────


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="ELO-движок бенчмарка")
    parser.add_argument("--check", action="store_true",
                        help="Проверить целостность журнала и индекса (без записи)")
    args = parser.parse_args()

    if args.check:
        return run_check()

    data = generate_index()
    save_index(data)

    models_count = len(data["models"])
    matchups_count = len(data["matchups_index"])
    applied = sum(1 for m in data["matchups_index"] if m["status"] == "applied")
    print(f"index.json обновлён: {models_count} моделей, {matchups_count} вердиктов "
          f"({applied} применено).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
