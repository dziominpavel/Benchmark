#!/usr/bin/env python3
"""
migrate_answers_v3.py — раскладка папок ответов под трёхпараметрический реестр.

Было (плоско):
    data/answers/<T-NNN>/<старое имя модели>/modelA.md

Стало (с группировкой по харнессу):
    data/answers/<T-NNN>/<harness>/<name>/modelA.md

Группировка по харнессу сохраняет контекст запуска после того, как названия
харнессов убрали из поля name, и разводит одноимённые модели (например,
Kimi K3 Max у Cursor и Devin).

Запуск:
    python tools/migrate_answers_v3.py            # показать план
    python tools/migrate_answers_v3.py --write    # выполнить
    python tools/migrate_answers_v3.py --task T-001 --write
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import ANSWERS_DIR, load_models_yaml  # noqa: E402

# Старые имена, которые не выводятся из нового name автоматически.
FOLDER_ALIASES = {
    "cursor-fable-5-1-1m-max": ["Cursor Fable 5.1 1M Max"],
    "cursor-sonnet-5-5-1m-max": ["Cursor Sonnet 5.5 1M Max"],
}


def candidate_names(model: dict) -> list[str]:
    """Возможные имена старой папки для модели."""
    name = str(model.get("name") or "").strip()
    harness = str(model.get("harness") or "").strip()
    candidates = [name]
    if harness and name:
        candidates.append(f"{harness} {name}")
    candidates.extend(FOLDER_ALIASES.get(model["id"], []))
    # Убираем пустые и дубликаты без учёта регистра, сохраняя порядок.
    seen: set[str] = set()
    result: list[str] = []
    for value in candidates:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def task_dirs(root: Path, task: str) -> list[Path]:
    if task:
        path = root / task
        return [path] if path.is_dir() else []
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir() if p.is_dir() and p.name.startswith("T-")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Раскладка папок ответов по харнессам")
    parser.add_argument("--task", default="", help="только один таск, например T-001")
    parser.add_argument("--write", action="store_true", help="выполнить перемещение")
    args = parser.parse_args()

    models = load_models_yaml()
    if not models:
        print("Реестр моделей пуст или не найден.", file=sys.stderr)
        return 1

    plans: list[tuple[Path, Path, str]] = []
    warnings: list[str] = []

    harness_names = {
        str(m.get("harness") or "").strip()
        for m in models
        if str(m.get("harness") or "").strip()
    }
    for task_dir in task_dirs(ANSWERS_DIR, args.task.strip()):
        folders = {
            d.name: d
            for d in task_dir.iterdir()
            if d.is_dir()
        }
        if folders and set(folders).issubset(harness_names):
            # Уже разложено по харнессам — миграция не нужна.
            continue
        used: set[str] = set()
        for model in models:
            matches = [
                folder for folder in folders
                if folder.casefold() in {c.casefold() for c in candidate_names(model)}
            ]
            if not matches:
                continue
            if len(matches) > 1:
                warnings.append(
                    f"{task_dir.name}/{model['id']}: несколько папок {matches}, "
                    "беру первую"
                )
            source_name = sorted(matches)[0]
            source = folders[source_name]
            used.add(source_name)
            target = task_dir / str(model["harness"]) / str(model["name"])
            plans.append((source, target, model["id"]))

        for folder in sorted(set(folders) - used):
            warnings.append(f"{task_dir.name}/{folder}: папка не сопоставлена с моделью")

    if not plans:
        print("Нечего перемещать: папки уже разложены или не найдены.")
        for warning in warnings:
            print(f"  ! {warning}", file=sys.stderr)
        return 0

    for source, target, model_id in plans:
        print(f"{source.relative_to(ANSWERS_DIR)} -> {target.relative_to(ANSWERS_DIR)}  [{model_id}]")
    for warning in warnings:
        print(f"  ! {warning}", file=sys.stderr)

    if not args.write:
        print(f"\nDry-run: {len(plans)} папок. Для перемещения добавьте --write.")
        return 0

    # Сначала проверяем конфликты, чтобы не оставить половину переносов.
    for source, target, _ in plans:
        if target.exists() and target.resolve() != source.resolve():
            print(f"Конфликт: {target} уже существует.", file=sys.stderr)
            return 1

    for source, target, _ in plans:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        print(f"Перемещено: {source.name} -> {target.relative_to(ANSWERS_DIR)}")

    print(f"\nГотово: {len(plans)} папок.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
