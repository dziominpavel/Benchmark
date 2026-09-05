#!/usr/bin/env python3
"""migrate_recorded_at.py — бэкфилл recorded_at для legacy-вердиктов.

Использование:
    python tools/migrate_recorded_at.py [--dry-run]

Для каждого файла matchups/<task>/<NNN>.json без recorded_at:
  - берёт date и seq из файла;
  - проставляет синтетическое recorded_at вида
    "{date}T00:00:{02+seq:02d}+00:00", чтобы сохранить монотонность по seq.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
MATCHUPS_DIR = REPO_ROOT / "matchups"


def backfill_recorded_at(dry_run: bool = False) -> list[Path]:
    changed: list[Path] = []
    if not MATCHUPS_DIR.exists():
        return changed

    for task_dir in sorted(MATCHUPS_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name == "state.json":
            continue
        for f in sorted(task_dir.glob("*.json")):
            if f.name == "state.json":
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"WARNING: не удалось прочитать {f}: {e}", file=sys.stderr)
                continue

            if data.get("recorded_at"):
                continue

            seq = data.get("seq")
            if seq is None:
                # Если seq нет, пробуем номер файла
                try:
                    seq = int(f.stem)
                except ValueError:
                    seq = 0

            date = data.get("date", "")
            if not date:
                print(f"WARNING: {f} не содержит date, пропуск", file=sys.stderr)
                continue

            synthetic = f"{date}T00:00:{2 + int(seq):02d}+00:00"
            data["recorded_at"] = synthetic

            if dry_run:
                print(f"DRY-RUN {f}: recorded_at = {synthetic}")
            else:
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                tmp.replace(f)
                print(f"{f}: recorded_at = {synthetic}")

            changed.append(f)

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Бэкфилл recorded_at в matchups/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать, что было бы изменено, не записывая")
    args = parser.parse_args()

    changed = backfill_recorded_at(dry_run=args.dry_run)
    print(f"\n{'Было бы изменено' if args.dry_run else 'Изменено'} файлов: {len(changed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
