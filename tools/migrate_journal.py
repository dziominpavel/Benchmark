#!/usr/bin/env python3
"""migrate_journal.py — миграция legacy-файлов вердиктов в журнал.

Использование:
    python tools/migrate_journal.py [--dry-run]

Переносит `data/matchups/T-NNN/*.json` (и `state.json`) в единый
append-only `data/matchups/journal.jsonl`:

  1. abort, если журнал уже существует (идемпотентность);
  2. сбор событий из `T-NNN/*.json` (собственный reader; `matchup`
     восстанавливается из пути), файлы без `seq` — abort;
  3. сортировка по `seq`; дубликаты `seq` — abort;
  4. `expected` — полный реплей из файлов (модели, `elo_history`,
     счётчики applied/skipped/voided/tombstones);
  5. журнал пишется во временный файл + `os.replace`;
  6. `actual` — реплей из журнала через продуктовый reader; при
     расхождении журнал удаляется, exit 1, старые файлы не тронуты;
  7. `generate_index()` + `save_index()` (индекс на новом дайджесте);
  8. удаление старых файлов, пустых каталогов задач и `state.json`.

`--dry-run`: шаги 1–4 и печать плана, без записи и удаления.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import elo  # noqa: E402


def collect_legacy_events(matchups_dir: Path) -> tuple[list[dict], list[str]]:
    """Собирает события журнала из legacy-файлов (собственный reader).

    Возвращает (события, проблемы). Файлы без `seq` и нечитаемые файлы
    попадают в проблемы — миграция по ним не выполняется.
    """
    events: list[dict] = []
    problems: list[str] = []
    if not matchups_dir.exists():
        return events, problems

    for task_dir in sorted(matchups_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        for f in sorted(task_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                problems.append(f"{f}: не читается: {e}")
                continue
            if not isinstance(data, dict):
                problems.append(f"{f}: не объект события")
                continue
            if data.get("seq") is None:
                problems.append(f"{f}: нет seq — событие вне append-протокола")
                continue
            event = {k: v for k, v in data.items() if not k.startswith("_")}
            event["matchup"] = f"{task_dir.name}/{f.stem}"
            events.append(event)

    events.sort(key=elo.matchup_sort_key)

    seen: dict[int, str] = {}
    for mu in events:
        seq = int(mu["seq"])
        if seq in seen:
            problems.append(
                f"дубликат seq={seq}: {seen[seq]} и {mu['matchup']}"
            )
        seen[seq] = mu["matchup"]

    return events, problems


def _replay_diff(expected: dict, actual: dict) -> list[str]:
    """Полное сравнение реплея до/после миграции."""
    problems: list[str] = []
    for mid, info in expected["models"].items():
        if actual["models"].get(mid) != info:
            problems.append(
                f"модель {mid}: до {info}, после {actual['models'].get(mid)}"
            )
    if expected["elo_history"] != actual["elo_history"]:
        problems.append(
            f"elo_history расходится: {len(expected['elo_history'])} "
            f"записей до, {len(actual['elo_history'])} после"
        )
        for i, (e, a) in enumerate(
            zip(expected["elo_history"], actual["elo_history"])
        ):
            if e != a:
                problems.append(f"  первое расхождение в позиции {i}: {e} != {a}")
                break
    for key in ("applied", "skipped", "voided", "tombstones", "warnings"):
        if expected[key] != actual[key]:
            problems.append(f"{key}: до {expected[key][:5]}, после {actual[key][:5]}")
    return problems


def migrate(dry_run: bool = False) -> int:
    """Выполняет миграцию; возвращает exit code."""
    journal_path: Path = elo.JOURNAL_PATH
    matchups_dir: Path = elo.MATCHUPS_DIR
    state_path = matchups_dir / "state.json"

    if journal_path.exists():
        print(
            f"ОШИБКА: журнал уже существует: {journal_path} — "
            f"миграция не нужна.",
            file=sys.stderr,
        )
        return 1

    events, problems = collect_legacy_events(matchups_dir)
    if problems:
        print("ОШИБКА: legacy-файлы не годятся для миграции:", file=sys.stderr)
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1
    if not events:
        print(
            "ОШИБКА: в каталоге нет legacy-файлов вердиктов для миграции.",
            file=sys.stderr,
        )
        return 1

    model_ids = [m["id"] for m in elo.load_models_yaml()]
    for mu in events:
        mu["_matchup_id"] = mu["matchup"]
    expected = elo.recalculate(events, model_ids)

    verdicts = sum(1 for mu in events if not mu.get("void_of"))
    tombstones = len(events) - verdicts
    seqs = [int(mu["seq"]) for mu in events]
    print(
        f"Legacy-события: {len(events)} "
        f"(вердиктов {verdicts}, tombstone {tombstones}), "
        f"seq {min(seqs)}..{max(seqs)}"
    )
    print(
        f"Реплей из файлов: применено {len(expected['applied'])}, "
        f"пропущено {len(expected['skipped'])}, "
        f"аннулировано {len(expected['voided'])}, "
        f"предупреждений {len(expected['warnings'])}"
    )
    for w in expected["warnings"]:
        print(f"  ⚠ {w}")

    if dry_run:
        print(
            f"\nDRY-RUN: журнал {journal_path} не записан, "
            f"legacy-файлы и {state_path.name} не удалены."
        )
        return 0

    # 5. Журнал во временный файл + os.replace (атомарно).
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = journal_path.with_name(journal_path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
        for mu in events:
            line = {k: v for k, v in mu.items() if not k.startswith("_")}
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, journal_path)
    print(f"Журнал записан: {journal_path} ({len(events)} строк)")

    # 6. Полное сравнение реплея до/после через продуктовый reader.
    actual_events, journal_problems = elo.read_journal()
    if journal_problems:
        problems.extend(journal_problems)
    actual = elo.recalculate(actual_events, model_ids)
    problems.extend(_replay_diff(expected, actual))
    if problems:
        journal_path.unlink(missing_ok=True)
        print(
            "ОШИБКА: реплей после миграции расходится — журнал удалён, "
            "legacy-файлы не тронуты:",
            file=sys.stderr,
        )
        for p in problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1

    # 7. Индекс на новом дайджесте журнала.
    elo.save_index(elo.generate_index())
    print(f"Индекс пересобран: {elo.INDEX_PATH}")

    # 8. Уборка legacy-хранилища (только после успешной верификации).
    removed = 0
    for task_dir in sorted(matchups_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        for f in sorted(task_dir.glob("*.json")):
            f.unlink()
            removed += 1
        if not any(task_dir.iterdir()):
            task_dir.rmdir()
    if state_path.exists():
        state_path.unlink()
        print(f"Удалён {state_path}")
    print(f"Удалено legacy-файлов: {removed} → строк журнала: {len(events)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Миграция matchups/T-NNN/*.json в единый журнал "
                    "data/matchups/journal.jsonl"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Показать план миграции, ничего не записывая и не удаляя",
    )
    args = parser.parse_args()
    return migrate(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
