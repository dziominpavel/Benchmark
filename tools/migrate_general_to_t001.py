#!/usr/bin/env python3
"""
migrate_general_to_t001.py — одноразовая миграция корзины general.

Переносит все вердикты из matchups/general/ в matchups/T-001/,
переписывает поле task с "general" на "T-001", удаляет пустую
matchups/general/, обновляет settings.yaml и пересчитывает index.json.

Использование:
    python tools/migrate_general_to_t001.py
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import (
    REPO_ROOT,
    generate_index,
    load_settings,
    save_index,
    save_settings,
)


def main() -> int:
    general_dir = REPO_ROOT / "matchups" / "general"
    t001_dir = REPO_ROOT / "matchups" / "T-001"

    if not general_dir.exists():
        print("matchups/general/ не найдена — нечего мигрировать.")
        return 0

    t001_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(general_dir.glob("*.json"))
    if not files:
        print("matchups/general/ пуста — удаляю.")
        shutil.rmtree(general_dir)
        return 0

    # Если в T-001 уже есть файлы, аварийно останавливаемся — нужно ручное решение.
    existing_t001 = sorted(t001_dir.glob("*.json"))
    if existing_t001:
        print(
            f"ОШИБКА: matchups/T-001/ уже содержит {len(existing_t001)} файл(ов). "
            "Миграция не выполнена.",
            file=sys.stderr,
        )
        return 1

    moved = 0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        data["task"] = "T-001"
        target = t001_dir / f.name
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        moved += 1

    # Удаляем исходную директорию
    shutil.rmtree(general_dir)

    # Обновляем settings.yaml
    settings = load_settings()
    tasks = settings.get("tasks", {})
    tasks.pop("general", None)
    tasks["T-001"] = "active"
    settings["current_task"] = "T-001"
    settings["tasks"] = tasks
    save_settings(settings)

    # Пересчитываем index.json
    idx = generate_index()
    save_index(idx)

    print(f"Мигрировано {moved} вердиктов из general в T-001.")
    print(f"matchups/T-001/ now has {len(sorted(t001_dir.glob('*.json')))} files.")
    print("settings.yaml и index.json обновлены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
