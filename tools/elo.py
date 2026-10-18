#!/usr/bin/env python3
"""
elo.py — ELO-движок и журнал вердиктов для бенчмарка LLM-моделей.

Вердикты — append-only журнал событий data/matchups/journal.jsonl
(одна JSON-строка на событие). Каждое событие (версия 2) содержит:
  seq         — глобальный монотонный номер (порядок реплея)
  matchup     — id события вида <task>/<NNN>
  recorded_at — ISO 8601 с таймзоной (ставит инструмент, не человек)
  model_a/model_b       — как записано (слот modelA/modelB или id)
  model_a_id/model_b_id — разрешённые id из models.yaml
  elo_before/elo_after/delta — снэпшот рейтинга на момент записи
  void_of     — (tombstone) id аннулируемого события, сам игр не создаёт

Порядок реплея — строго по возрастанию seq. Оборванная последняя строка
(аварийное прерывание записи) игнорируется чтением с предупреждением.
Запись — append под межпроцессным lock, flush + fsync (см. record_verdict).
--check проверяет: снэпшоты сходятся с реплеем (детект правки истории),
seq уникален, recorded_at неубывает вместе с seq, модели разрешимы,
нет невалидных строк и висячих void_of-ссылок.

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
import time
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
MATCHUPS_DIR = DATA_DIR / "matchups"
JOURNAL_PATH = MATCHUPS_DIR / "journal.jsonl"
JOURNAL_REL = "data/matchups/journal.jsonl"
ANSWERS_DIR = DATA_DIR / "answers"
TASKS_DIR = DATA_DIR / "tasks"
INDEX_PATH = DATA_DIR / "index.json"
MODELS_PATH = DATA_DIR / "models.yaml"
SETTINGS_PATH = DATA_DIR / "settings.yaml"
ANSWER_FLAGS_PATH = DATA_DIR / "answer_flags.yaml"

DEFAULT_ELO = 1200
VERDICT_VERSION = 2

# Append-протокол (см. journal_lock): таймаут ожидания лока и шаг опроса.
LOCK_TIMEOUT = 15.0
LOCK_POLL = 0.05

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
    """Ключ сортировки реплея — строго по возрастанию `seq`.

    События без seq (защита от битого журнала) идут первыми и
    репортируются `--check` как проблема.
    """
    seq = mu.get("seq")
    return int(seq) if seq is not None else 0


def read_journal() -> tuple[list[dict], list[str]]:
    """Читает `data/matchups/journal.jsonl` → (события, проблемы).

    События — в порядке возрастания `seq`; `_matchup_id` заполняется из
    поля `matchup`, `_file` — диагностический относительный путь.
    Оборванная последняя строка (аварийное прерывание) и невалидные
    строки пропускаются и возвращаются в списке проблем; печать — на
    вызывающей стороне (load_matchups / --check).
    """
    events: list[dict] = []
    problems: list[str] = []
    if not JOURNAL_PATH.exists():
        return events, problems

    try:
        text = JOURNAL_PATH.read_text(encoding="utf-8")
    except OSError as e:
        problems.append(f"{JOURNAL_REL}: не читается: {e}")
        return events, problems

    lines = text.splitlines()
    ordered = True
    prev_seq = -1
    for i, raw in enumerate(lines):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            where = (
                "оборванная последняя строка"
                if i == len(lines) - 1
                else f"строка {i + 1}"
            )
            problems.append(f"{JOURNAL_REL}: невалидный JSON ({where}): {e}")
            continue
        if not isinstance(data, dict):
            problems.append(f"{JOURNAL_REL}: строка {i + 1} — не объект события")
            continue
        seq = data.get("seq")
        if seq is None:
            ordered = False
        else:
            seq_int = int(seq)
            if seq_int < prev_seq:
                ordered = False
            prev_seq = seq_int
        data["_matchup_id"] = data.get("matchup", "")
        data["_file"] = JOURNAL_REL
        events.append(data)

    if not ordered:
        events.sort(key=matchup_sort_key)
    return events, problems


def load_matchups() -> list[dict]:
    """Загружает все события журнала в порядке реплея (по `seq`)."""
    events, problems = read_journal()
    for p in problems:
        print(f"WARNING: {p}", file=sys.stderr)
    return events


def matchups_digest() -> str:
    """sha256 содержимого `data/matchups/journal.jsonl`.

    Используется для инвалидации index.json и memo-слоя: любая правка/
    удаление/дописывание строки журнала меняет дайджест. Отсутствующий
    файл — дайджест пустого хранилища.
    """
    h = hashlib.sha256()
    try:
        h.update(JOURNAL_PATH.read_bytes())
    except OSError:
        pass
    return h.hexdigest()


# ─── Model resolution ───────────────────────────────────────────────


def resolve_matchup_models(mu: dict, model_ids: set[str]) -> tuple[str | None, str | None]:
    """Разрешает моделей вердикта в реальные id.

    Приоритет:
      1. model_a_id / model_b_id (записано инструментом при создании)
      2. model_a / model_b, если это уже id из реестра
    Возвращает (id_a, id_b); неразрешённый — None.
    """
    def resolve(side: str) -> str | None:
        rid = mu.get(f"model_{side}_id")
        if rid:
            return rid if rid in model_ids else None
        raw = mu.get(f"model_{side}")
        if raw in model_ids:
            return raw
        return None

    return resolve("a"), resolve("b")


# ─── Ledger write path ──────────────────────────────────────────────


@contextmanager
def journal_lock(timeout: float = LOCK_TIMEOUT):
    """Межпроцессный эксклюзивный lock журнала для read-modify-append.

    Windows: `msvcrt.locking` на байте за пределами файла — читатели
    (lock не берут) не упираются в заблокированный диапазон данных.
    POSIX: `fcntl.flock`. Ожидание с ретраями до `timeout` секунд.
    """
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    f = open(JOURNAL_PATH, "a+b")
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    f.seek(1 << 40)
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"не удалось получить блокировку журнала за {timeout:.0f} с"
                    )
                time.sleep(LOCK_POLL)
        yield f
    finally:
        try:
            if os.name == "nt":
                f.seek(1 << 40)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        f.close()


def append_event(f, event: dict) -> None:
    """Дозаписывает событие в журнал: один write + flush + fsync.

    Вызывается только с открытым дескриптором под `journal_lock`.
    """
    line = json.dumps(event, ensure_ascii=False) + "\n"
    f.write(line.encode("utf-8"))
    f.flush()
    os.fsync(f.fileno())


def next_matchup_id(task: str, events: list[dict] | None = None) -> str:
    """Следующий id события задачи: max существующего NNN + 1 (<task>/NNN)."""
    if events is None:
        events = load_matchups()
    prefix = f"{task}/"
    max_n = 0
    for mu in events:
        mid = mu.get("_matchup_id", "")
        if mid.startswith(prefix):
            tail = mid[len(prefix):]
            if tail.isdigit():
                max_n = max(max_n, int(tail))
    return f"{task}/{max_n + 1:03d}"


def _next_seq(events: list[dict]) -> int:
    """Глобальный seq следующего события: max существующего + 1."""
    return max(
        (int(mu["seq"]) for mu in events if mu.get("seq") is not None),
        default=0,
    ) + 1


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _replay_state(matchups: list[dict], model_ids: list[str]) -> tuple[dict, dict]:
    """Реплей событий журнала → (elo, stats). Нужно для снэпшота записи."""
    elo: dict[str, int] = {mid: DEFAULT_ELO for mid in model_ids}
    stats: dict[str, dict] = {
        mid: {"games": 0, "wins": 0, "losses": 0, "draws": 0} for mid in model_ids
    }
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
    model_id_set = set(model_ids)
    for mu in matchups:
        if mu.get("void_of") or mu["_matchup_id"] in voided:
            continue
        a, b = resolve_matchup_models(mu, model_id_set)
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


def _parse_verdict_date(value: str) -> str:
    """Проверяет дату вердикта: ровно `YYYY-MM-DD` и календарно корректную.

    Возвращает нормализованную строку; бросает ValueError.
    """
    value = value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(
            f"Дата вердикта должна быть в формате YYYY-MM-DD, получено '{value}'"
        )
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Некорректная дата вердикта: '{value}'") from None
    return value


def record_verdict(
    task: str,
    model_a: str,
    model_b: str,
    winner: str,
    *,
    recorded_at: str | None = None,
    verdict_date: str | None = None,
    regenerate_index: bool = True,
) -> dict:
    """Записывает вердикт в журнал — ЕДИНСТВЕННАЯ точка записи.

    - model_a/model_b SHALL быть реальными id из models.yaml.
    - Назначает глобальный seq и matchup (<task>/NNN), штампует
      recorded_at системным временем.
    - verdict_date — дата вердикта (YYYY-MM-DD, по умолчанию — сегодня);
      пустое значение эквивалентно «сегодня».
    - Вычисляет и записывает снэпшот ELO (before/after/delta) — делает
      подмену или вставку задним числом детектируемой через --check.
    - Дозаписывает строку в data/matchups/journal.jsonl под
      межпроцессным lock (append + flush + fsync).
    - Перегенерирует index.json (если regenerate_index).

    Возвращает dict с path и записанным вердиктом. Бросает ValueError.
    """
    if not is_valid_task_id(task):
        raise ValueError(f"Некорректный task: '{task}'. Допустимы только идентификаторы вида T-NNN.")
    if winner not in ("a", "b", "draw"):
        raise ValueError(f"winner должен быть a|b|draw, получено '{winner}'")
    if model_a == model_b:
        raise ValueError("Модели A и B должны различаться")
    if verdict_date:
        verdict_date = _parse_verdict_date(verdict_date)

    settings = load_settings()

    model_ids = {m["id"] for m in load_models_yaml()}

    # model_a/model_b SHALL быть реальными id из models.yaml
    id_a = model_a if model_a in model_ids else None
    id_b = model_b if model_b in model_ids else None

    # Read-modify-append под межпроцессным lock: seq, matchup, проверка
    # таска и снэпшот считаются от одного и того же состояния журнала.
    with journal_lock() as f:
        events = load_matchups()
        if task not in active_tasks(settings, events):
            raise ValueError(f"Таск '{task}' неактивна или неизвестна.")
        if not id_a:
            raise ValueError(
                f"Модель A не разрешена: '{model_a}'. "
                f"Укажи реальный id из models.yaml."
            )
        if not id_b:
            raise ValueError(
                f"Модель B не разрешена: '{model_b}'. "
                f"Укажи реальный id из models.yaml."
            )
        elo, stats = _replay_state(events, sorted(model_ids))
        r_a, r_b = elo[id_a], elo[id_b]
        s_a, s_b = (1.0, 0.0) if winner == "a" else (0.0, 1.0) if winner == "b" else (0.5, 0.5)
        e_a = expected_score(r_a, r_b)
        new_a, new_b = update_elo(
            r_a, k_factor(stats[id_a]["games"]), s_a, e_a,
            r_b, k_factor(stats[id_b]["games"]), s_b, 1.0 - e_a,
        )

        seq = _next_seq(events)
        matchup_id = next_matchup_id(task, events)

        verdict = {
            "version": VERDICT_VERSION,
            "seq": seq,
            "task": task,
            "matchup": matchup_id,
            "model_a": model_a,
            "model_b": model_b,
            "model_a_id": id_a,
            "model_b_id": id_b,
            "winner": winner,
            "date": verdict_date or date.today().isoformat(),
            "recorded_at": recorded_at or now_iso(),
            "elo": {
                id_a: {"before": r_a, "after": new_a, "delta": new_a - r_a},
                id_b: {"before": r_b, "after": new_b, "delta": new_b - r_b},
            },
        }
        append_event(f, verdict)

    if regenerate_index:
        save_index(generate_index())

    return {"path": JOURNAL_PATH, "verdict": verdict, "matchup_id": matchup_id}


def void_matchup(matchup_id: str, reason: str = "") -> dict:
    """Аннулирует вердикт tombstone-событием (сам вердикт не удаляется).

    matchup_id вида 'T-001/001'; цель ищется среди событий журнала.
    Повторное аннулирование и аннулирование tombstone-события отклоняются
    с ValueError до записи. Возвращает dict с path журнала и id нового события.
    """
    if "/" not in matchup_id:
        raise ValueError(f"matchup_id должен быть вида '<task>/<NNN>', получено '{matchup_id}'")
    task = matchup_id.split("/", 1)[0]

    with journal_lock() as f:
        events = load_matchups()
        target = next((mu for mu in events if mu.get("_matchup_id") == matchup_id), None)
        if target is None:
            raise ValueError(f"Вердикт {matchup_id} не найден в журнале")
        if target.get("void_of"):
            raise ValueError(
                f"{matchup_id} — событие аннулирования: аннулировать его нельзя"
            )
        if any(mu.get("void_of") == matchup_id for mu in events):
            raise ValueError(f"Вердикт {matchup_id} уже аннулирован")

        seq = _next_seq(events)
        new_id = next_matchup_id(task, events)

        tombstone = {
            "version": VERDICT_VERSION,
            "seq": seq,
            "task": task,
            "matchup": new_id,
            "void_of": matchup_id,
            "reason": reason,
            "date": date.today().isoformat(),
            "recorded_at": now_iso(),
        }
        append_event(f, tombstone)

    save_index(generate_index())
    return {"path": JOURNAL_PATH, "matchup_id": new_id}


# ─── Full recalculation (tasks 2.4, 2.5) ────────────────────────────


def recalculate(matchups: list[dict], model_ids: list[str]) -> dict:
    """Полный пересчёт ELO из всех вердиктов в порядке журнала.

    Возвращает dict:
      models: {id: {elo, games, wins, losses, draws}}
      elo_history: [{matchup, seq, date, recorded_at, model_a_id, model_b_id,
                     winner, elo_a, elo_b}, ...]
      voided_history: [{matchup, seq, task, date, recorded_at, model_a_id,
                        model_b_id, winner, elo_a, elo_b, void}, ...]
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
            warnings.append(f"tombstone ссылается на несуществующее событие: {vid}")

    # Аудит аннулированных: детали исходной записи (снэпшот как записан)
    # плюс tombstone-событие. На ELO, elo_history и счётчики не влияет.
    # При исторических дублях tombstone на одну цель берётся первый по seq.
    voided_history: list[dict] = []
    seen_voided: set[str] = set()
    events_by_id = {mu.get("_matchup_id"): mu for mu in matchups}
    for mu in sorted(
        (m for m in matchups if m.get("void_of")),
        key=lambda m: m.get("seq") or 0,
    ):
        vid = mu["void_of"]
        if vid in seen_voided:
            continue
        target = events_by_id.get(vid)
        if target is None:
            continue  # висячая ссылка — уже в warnings
        seen_voided.add(vid)
        a = target.get("model_a_id", "")
        b = target.get("model_b_id", "")
        snap = target.get("elo") or {}
        snap_a = snap.get(a) if a else None
        snap_b = snap.get(b) if b else None
        voided_history.append({
            "matchup": vid,
            "seq": target.get("seq"),
            "task": target.get("task", ""),
            "date": target.get("date", ""),
            "recorded_at": target.get("recorded_at", ""),
            "model_a_id": a,
            "model_b_id": b,
            "winner": target.get("winner", ""),
            "elo_a": snap_a if isinstance(snap_a, dict)
            else {"before": DEFAULT_ELO, "after": DEFAULT_ELO, "delta": 0},
            "elo_b": snap_b if isinstance(snap_b, dict)
            else {"before": DEFAULT_ELO, "after": DEFAULT_ELO, "delta": 0},
            "void": {
                "reason": mu.get("reason", ""),
                "date": mu.get("date", ""),
                "recorded_at": mu.get("recorded_at", ""),
                "matchup": mu.get("_matchup_id", mu.get("matchup", "")),
            },
        })
    voided_history.sort(key=lambda e: e.get("seq") or 0)

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
        "voided_history": voided_history,
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
            problems.append(f"{mu_id}: нет seq — событие вне append-протокола")

        if not (mu.get("matchup") or mu.get("_matchup_id")):
            problems.append(f"{mu_id or '?'}: отсутствует поле matchup")
        if not mu.get("task"):
            problems.append(f"{mu_id}: отсутствует поле task")

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
    """Парсит models.yaml — возвращает список моделей
    (id, name, agent, provider, released, added, status)."""
    models_path = MODELS_PATH
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


def collect_tasks_info(journal: list[dict] | None = None) -> dict:
    """Собирает сводку по задачам из tasks/ и событий журнала.

    `matchups_count` — число событий журнала с полем `task`, равным id
    задачи (вердикты, аннулирования, tombstone). Отдельных файлов вердиктов
    больше нет. Наличие ответов здесь не учитывается: тексты хранятся вне
    проекта, учёт ведётся вручную в data/answer_flags.yaml.
    """
    if journal is None:
        journal = load_matchups()

    per_task: dict[str, int] = {}
    for mu in journal:
        task = mu.get("task") or str(mu.get("_matchup_id", "")).split("/", 1)[0]
        if task:
            per_task[task] = per_task.get(task, 0) + 1

    tasks_info = {}

    if TASKS_DIR.exists():
        for d in sorted(TASKS_DIR.iterdir()):
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

            tasks_info[task_id] = {
                "slug": d.name,
                "title": title,
                "matchups_count": per_task.get(task_id, 0),
            }

    return tasks_info


def build_matchups_summary(applied: list[str], voided: list[str],
                           tombstones: list[str], skipped: list[str],
                           total: int) -> dict:
    """Агрегат журнала для index.json: счётчики событий по статусам.

    Полный список не храним — детали только в data/matchups/journal.jsonl.
    """
    return {
        "total": total,
        "applied": len(applied),
        "voided": len(voided),
        "tombstone": len(tombstones),
        "skipped": len(skipped),
    }


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
            "agent": m.get("agent", ""),
            "provider": m.get("provider", ""),
            "added": m.get("added", ""),
            "status": m.get("status", "active"),
            "elo": elo_info["elo"],
            "games": elo_info["games"],
            "wins": elo_info["wins"],
            "losses": elo_info["losses"],
            "draws": elo_info["draws"],
        }

    tasks_info = collect_tasks_info(matchups)
    matchups_summary = build_matchups_summary(
        elo_data["applied"],
        elo_data["voided"],
        elo_data["tombstones"],
        elo_data["skipped"],
        len(matchups),
    )

    return {
        "version": 2,
        "updated": date.today().isoformat(),
        "matchups_digest": matchups_digest(),
        "models": models_out,
        "tasks": tasks_info,
        "matchups_summary": matchups_summary,
        "elo_history": elo_data["elo_history"],
        "voided_history": elo_data["voided_history"],
    }


def save_index(data: dict) -> None:
    """Записывает index.json (атомарно)."""
    _atomic_write_json(INDEX_PATH, data)


# ─── Settings & coverage ────────────────────────────────────────────


def _unquote(val: str) -> str:
    """Снимает кавычки с простого YAML-скаляра."""
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        return val[1:-1]
    return val


def load_settings(path: Path | None = None) -> dict:
    """Читает settings.yaml → {"current_task": str, "tasks": {id: status}}.

    Файл может отсутствовать или быть частичным — применяются дефолты
    (`current_task: ""`, пустой реестр тасков). Таска без записи
    в реестре считается активной (см. is_task_active).
    """
    if path is None:
        path = SETTINGS_PATH
    settings: dict = {"current_task": "", "tasks": {}}
    if not path.exists():
        return settings
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return settings

    in_tasks = False
    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indented = raw[:1] in (" ", "\t")
        key, sep, val = raw.strip().partition(":")
        if not sep:
            continue
        key, val = key.strip(), _unquote(val)
        if not indented:
            in_tasks = key == "tasks"
            if key == "current_task" and val:
                settings["current_task"] = val
        elif in_tasks and val:
            settings["tasks"][key] = val
    return settings


def save_settings(settings: dict, path: Path | None = None) -> None:
    """Записывает settings.yaml (UTF-8 без BOM, детерминированный вид)."""
    if path is None:
        path = SETTINGS_PATH
    out = ["# Настройки бенчмарка: активные таски и текущая таска.",
           "# tasks: <id> -> active | inactive; без записи таска активна.",
           f"current_task: {settings.get('current_task', 'general')}",
           "tasks:"]
    for tid in sorted(settings.get("tasks", {})):
        out.append(f"  {tid}: {settings['tasks'][tid]}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def load_answer_flags(path: Path | None = None) -> dict:
    """Читает answer_flags.yaml → {task_id: {model_id: bool}}.

    Разреженный формат: отсутствие записи = false (нет ответа).
    Неизвестные task/model (опечатки, удалённые) возвращаются как есть —
    фильтрация по реестру выполняется при построении матрицы, запись
    таких id никогда не падает.
    """
    if path is None:
        path = ANSWER_FLAGS_PATH
    flags: dict = {}
    if not path.exists():
        return flags
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return flags

    in_flags = False
    current_task: str | None = None
    for raw in lines:
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" \t"))
        key, sep, val = raw.strip().partition(":")
        if not sep:
            continue
        key, val = key.strip(), _unquote(val).strip()
        if indent == 0:
            in_flags = key == "answer_flags"
            current_task = None
            if in_flags and val not in ("", "{}"):
                in_flags = False
        elif in_flags and indent == 2 and current_task is None:
            # Строка таска — только при отступе ровно 2 от answer_flags.
            # Вложенность глубже без таска игнорируется.
            if val == "":
                current_task = key
                flags.setdefault(key, {})
            elif val == "{}":
                flags.setdefault(key, {})
        elif in_flags and indent >= 4 and current_task is not None:
            flags.setdefault(current_task, {})[key] = val.lower() in (
                "true", "yes", "1", "on",
            )
        elif in_flags and indent == 2:
            # Новый таск после моделей предыдущего.
            current_task = None
            if val == "":
                current_task = key
                flags.setdefault(key, {})
            elif val == "{}":
                flags.setdefault(key, {})
    return flags


def save_answer_flags(flags: dict, path: Path | None = None) -> None:
    """Записывает answer_flags.yaml (UTF-8 без BOM, детерминированный вид).

    Пишет только true-записи, отсортированные по task и model;
    отсутствие = false. Вызывающая сторона передаёт только известные
    id (матрица строится по реестру), поэтому мусорные записи при
    сохранении через UI исчезают.
    """
    if path is None:
        path = ANSWER_FLAGS_PATH
    out = ["# Ручной учёт наличия ответов: task -> model -> true. Отсутствие = нет ответа.",
           "# Тексты ответов хранятся вне проекта; здесь только флаги."]
    tasks = sorted(t for t, m in flags.items() if any(bool(v) for v in (m or {}).values()))
    if not tasks:
        out.append("answer_flags: {}")
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
        return
    out.append("answer_flags:")
    for tid in tasks:
        out.append(f"  {tid}:")
        for mid in sorted(m for m, v in flags[tid].items() if v):
            out.append(f"    {mid}: true")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def is_valid_task_id(task: str) -> bool:
    """Проверяет, что task — корректный идентификатор вида T-NNN."""
    return bool(TASK_ID_RE.fullmatch(task or ""))


def known_tasks(settings: dict | None = None,
                journal: list[dict] | None = None) -> list[str]:
    """Известные таски: события журнала ∪ tasks/T-NNN-* ∪ settings.tasks (только T-NNN)."""
    if settings is None:
        settings = load_settings()
    if journal is None:
        journal = load_matchups()
    known = {
        t for t in settings.get("tasks", {})
        if is_valid_task_id(t)
    }
    for mu in journal:
        task = mu.get("task") or str(mu.get("_matchup_id", "")).split("/", 1)[0]
        if task not in known and is_valid_task_id(task):
            known.add(task)
    if TASKS_DIR.exists():
        for d in TASKS_DIR.iterdir():
            if not d.is_dir() or d.name.startswith("_"):
                continue
            m = TASK_ID_RE.match(d.name)
            if m and is_valid_task_id(m.group(1)):
                known.add(m.group(1))
    return sorted(known)


def is_task_active(settings: dict, task: str) -> bool:
    """Таска активна, если не помечена inactive в settings.tasks."""
    return settings.get("tasks", {}).get(task, "active") != "inactive"


def active_tasks(settings: dict | None = None,
                 journal: list[dict] | None = None) -> list[str]:
    """Список известных активных тасков."""
    if settings is None:
        settings = load_settings()
    return [t for t in known_tasks(settings, journal) if is_task_active(settings, t)]


def resolve_current_task(settings: dict | None = None,
                         journal: list[dict] | None = None) -> str:
    """Текущая таска для формы вердикта; неактивная/неизвестная → первая активная T-NNN."""
    if settings is None:
        settings = load_settings()
    current = settings.get("current_task", "")
    if (is_valid_task_id(current)
            and (current in settings.get("tasks", {})
                 or current in known_tasks(settings, journal))
            and is_task_active(settings, current)):
        return current
    active = active_tasks(settings, journal)
    return active[0] if active else ""


def get_coverage(
    settings: dict | None = None,
    matchups: list[dict] | None = None,
    models: list[dict] | None = None,
    flags: dict | None = None,
    verdicts: dict | None = None,
    tasks: list[str] | None = None,
) -> dict:
    """Покрытие прогона: видимые ячейки (таск × пара активных моделей).

    Видимая ячейка — активный таск + активная пара, у обеих моделей
    которой флаг ответа true на этот таск (answer_flags.yaml;
    отсутствие записи = false, отсутствие файла = все BLOCKED).
    BLOCKED-ячейки (хотя бы одного ответа нет) исключаются и из
    числителя, и из знаменателя. Видимая ячейка DONE, если у пары
    есть ≥1 неаннулированный вердикт в этом таске, иначе READY.
    Повторы и рематчи в ячейке не засчитываются.
    Возвращает {"filled" (DONE), "total" (READY+DONE), "percent"};
    percent=None, если метрика не определена (нет активных тасков,
    <2 активных моделей или видимых ячеек 0). Процент ограничен
    сверху 100.0: есть READY → строго меньше 100%.

    `verdicts` — необязательная готовая карта «пара → таски» с
    неаннулированными вердиктами (pair_task_verdicts консоли): заменяет
    пересборку ячеек из `matchups`. `tasks` — необязательный готовый
    список активных тасков (иначе считается здесь).
    """
    if settings is None:
        settings = load_settings()
    if models is None:
        models = load_models_yaml()
    if matchups is None:
        matchups = load_matchups()
    if flags is None:
        flags = load_answer_flags()

    active_model_ids = {
        m["id"] for m in models if m.get("status", "active") != "archived"
    }
    if len(active_model_ids) < 2:
        return {"filled": 0, "total": 0, "percent": None}
    if tasks is None:
        tasks = active_tasks(settings, matchups)
    if not tasks:
        return {"filled": 0, "total": 0, "percent": None}

    if verdicts is None:
        model_ids = {m["id"] for m in models}
        voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
        verdict_cells: set[tuple[str, frozenset]] = set()
        for mu in matchups:
            if mu.get("void_of") or mu.get("_matchup_id") in voided:
                continue
            task = mu.get("task") or str(mu.get("_matchup_id", "")).split("/", 1)[0]
            if task not in tasks:
                continue
            a, b = resolve_matchup_models(mu, model_ids)
            if not a or not b or a not in active_model_ids or b not in active_model_ids:
                continue
            verdict_cells.add((task, frozenset((a, b))))

    # Знаменатель — пары размеченных моделей (оба флага true) на активный
    # таск: C(k,2) без перечисления самих пар (до 1000 активных моделей).
    total = 0
    for task in tasks:
        task_flags = flags.get(task) or {}
        k = sum(1 for mid in active_model_ids if task_flags.get(mid))
        total += k * (k - 1) // 2

    if total == 0:
        return {"filled": 0, "total": 0, "percent": None}

    # DONE — видимая ячейка с неаннулированным вердиктом (повторы не считаются).
    filled = 0
    if verdicts is None:
        for task, pair in verdict_cells:
            task_flags = flags.get(task) or {}
            a, b = tuple(pair)
            if task_flags.get(a) and task_flags.get(b):
                filled += 1
    else:
        # Готовая карта «пара → таски» (pair_task_verdicts консоли):
        # ячейки не пересобираются из событий, фильтры — при подсчёте.
        for pair, pair_tasks in verdicts.items():
            a, b = tuple(pair)
            if a not in active_model_ids or b not in active_model_ids:
                continue
            for task in pair_tasks:
                if task not in tasks:
                    continue
                task_flags = flags.get(task) or {}
                if task_flags.get(a) and task_flags.get(b):
                    filled += 1

    return {
        "filled": filled,
        "total": total,
        "percent": min(100.0, filled / total * 100),
    }


def get_answer_matrix(
    settings: dict | None = None,
    models: list[dict] | None = None,
    flags: dict | None = None,
    journal: list[dict] | None = None,
) -> dict:
    """Ручной учёт наличия ответов: матрица модель × таск.

    Источник — data/answer_flags.yaml (отсутствие = false). Записи для
    неизвестных модели/таска игнорируются. Сводка считается только по
    активным моделям × активным таскам; архивные/неактивные возвращаются
    в строках/столбцах со статусом для UI-фильтра. Строки отсортированы
    по имени модели (case-insensitive, по алфавиту). `journal` позволяет
    переиспользовать уже разобранные события (memo-слой консоли).
    """
    if settings is None:
        settings = load_settings()
    if models is None:
        models = load_models_yaml()
    if flags is None:
        flags = load_answer_flags()

    tasks_all = known_tasks(settings, journal)
    active_task_ids = active_tasks(settings, journal)
    active_set = set(active_task_ids)

    rows = []
    for m in models:
        mid = m["id"]
        status = m.get("status", "active")
        cells = {
            t: bool((flags.get(t) or {}).get(mid, False)) for t in tasks_all
        }
        debt = sum(1 for t in active_task_ids if not cells.get(t, False))
        rows.append({
            "id": mid,
            "name": m.get("name", mid),
            "status": status,
            "debt": debt,
            "cells": cells,
        })
    rows.sort(key=lambda r: r["name"].lower())

    n_active_models = sum(1 for r in rows if r["status"] != "archived")
    total = n_active_models * len(active_task_ids)
    filled = sum(
        1 for r in rows if r["status"] != "archived"
        for t in active_task_ids if r["cells"].get(t, False)
    )
    return {
        "tasks": tasks_all,
        "active_tasks": active_task_ids,
        "rows": rows,
        "filled": filled,
        "total": total,
        "remaining": total - filled,
        "has_active": bool(active_set) and n_active_models > 0,
    }


# ─── Integrity check ────────────────────────────────────────────────


def is_index_stale(idx: dict | None = None, digest: str | None = None) -> bool:
    """Проверяет, устарел ли index.json vs журнал и models.yaml.

    Принимает уже прочитанный объект index.json (`idx`), чтобы консоль
    не парсила файл дважды; без аргумента читает файл сам. `digest` —
    заранее вычисленный дайджест журнала (даёт мемо-слой), иначе он
    считается здесь.
    """
    if idx is None:
        if not INDEX_PATH.exists():
            return True
        try:
            idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return True

    # Дайджест содержимого журнала — ловит правки, не только добавления
    if digest is None:
        digest = matchups_digest()
    if idx.get("matchups_digest") != digest:
        return True

    models = load_models_yaml()
    indexed_models = set(idx.get("models", {}).keys())
    yaml_models = {m["id"] for m in models}
    if indexed_models != yaml_models:
        return True

    # Метаданные моделей (status, name, agent, provider, added) тоже влияют на UI/рекомендации
    for m in models:
        mid = m["id"]
        info = idx.get("models", {}).get(mid, {})
        for key in ("name", "agent", "provider", "status", "added"):
            if info.get(key, "") != m.get(key, ""):
                return True

    return False


def run_check() -> int:
    """Полная проверка целостности журнала и индекса. Возвращает exit code."""
    problems: list[str] = []

    models = load_models_yaml()
    model_ids = [m["id"] for m in models]

    # Оборванная последняя строка и невалидные строки журнала
    matchups, journal_problems = read_journal()
    problems.extend(journal_problems)

    # Снэпшоты, порядок seq/recorded_at, дубликаты seq, поля событий
    problems.extend(verify_snapshots(matchups, model_ids))

    # Неразрешённые модели / невалидные winner / висячие void_of-ссылки
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
    parser = argparse.ArgumentParser(
        description="ELO-движок бенчмарка: реплей журнала "
                    "data/matchups/journal.jsonl → data/index.json")
    parser.add_argument("--check", action="store_true",
                        help="Проверить целостность журнала и индекса (без записи)")
    args = parser.parse_args()

    if args.check:
        return run_check()

    data = generate_index()
    save_index(data)

    models_count = len(data["models"])
    summary = data["matchups_summary"]
    print(f"index.json обновлён: {models_count} моделей, {summary['total']} вердиктов "
          f"({summary['applied']} применено).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
