#!/usr/bin/env python3
"""
migrate_answers_v4.py — раскладка архива ответов по харнессу и провайдеру.

Было (v3):
    data/answers/<T-NNN>/<harness>/<name>/modelA.md

Стало (v4):
    data/answers/<T-NNN>/<harness>/<provider>/<name>/modelA.md

Провайдер берётся из models.yaml. Пустой provider раскладывается в
UNKNOWN_PROVIDER ("Unknown"), чтобы путь не схлопывался на уровень модели.
Ожидается раскладка v3; старую плоскую раскладку сначала прогоните через
tools/migrate_answers_v3.py.

Скрипт идемпотентен: уже разложенные по провайдерам папки пропускаются.
Конфликты проверяются до перемещения: при конфликте не двигается ничего.

Запуск:
    python tools/migrate_answers_v4.py            # показать план
    python tools/migrate_answers_v4.py --write    # выполнить
    python tools/migrate_answers_v4.py --task T-001 --write
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

UNKNOWN_PROVIDER = "Unknown"


def harness_of(model: dict) -> str:
    return str(model.get("harness") or "").strip()


def provider_of(model: dict) -> str:
    return str(model.get("provider") or "").strip() or UNKNOWN_PROVIDER


def name_of(model: dict) -> str:
    return str(model.get("name") or "").strip()


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
    parser = argparse.ArgumentParser(
        description="Раскладка архива ответов по харнессам и провайдерам"
    )
    parser.add_argument("--task", default="", help="только один таск, например T-001")
    parser.add_argument("--write", action="store_true", help="выполнить перемещение")
    args = parser.parse_args()

    models = load_models_yaml()
    if not models:
        print("Реестр моделей пуст или не найден.", file=sys.stderr)
        return 1

    # Ключи регистронезависимы: Windows не различает регистр путей, а реестр
    # и диск могут разойтись в написании.
    by_hn: dict[tuple[str, str], dict] = {}
    providers: dict[str, set[str]] = {}
    harnesses: set[str] = set()
    for model in models:
        harness = harness_of(model)
        name = name_of(model)
        if not harness or not name:
            print(
                f"Модель {model.get('id')!r}: пустые harness/name, пропуск.",
                file=sys.stderr,
            )
            continue
        key = (harness.casefold(), name.casefold())
        if key in by_hn:
            print(
                f"Реестр: дубль harness/name {harness!r}/{name!r} "
                f"({by_hn[key].get('id')} и {model.get('id')}).",
                file=sys.stderr,
            )
            return 1
        by_hn[key] = model
        harnesses.add(harness.casefold())
        providers.setdefault(harness.casefold(), set()).add(
            provider_of(model).casefold()
        )

    tasks = task_dirs(ANSWERS_DIR, args.task.strip())
    if args.task.strip() and not tasks:
        print(
            f"Каталог ответов для {args.task.strip()} не найден.",
            file=sys.stderr,
        )
        return 1

    plans: list[tuple[Path, Path, str]] = []
    conflicts: list[str] = []
    warnings: list[str] = []

    for task_dir in tasks:
        for node in sorted(p for p in task_dir.iterdir() if p.is_dir()):
            if node.name.casefold() not in harnesses:
                warnings.append(f"{task_dir.name}/{node.name}: не харнесс — пропущено")
                continue
            harness = node.name.casefold()
            for child in sorted(p for p in node.iterdir() if p.is_dir()):
                model = by_hn.get((harness, child.name.casefold()))
                if model is not None:
                    target = node / provider_of(model) / name_of(model)
                    if source_is_inside_target(child, target):
                        conflicts.append(
                            f"{task_dir.name}/{node.name}/{child.name}: "
                            "цель вложена в исходник — перемещение невозможно"
                        )
                    elif target.exists():
                        conflicts.append(
                            f"{task_dir.name}/{node.name}/{provider_of(model)}/"
                            f"{name_of(model)}: цель уже существует, "
                            f"исходник {child.name} не перемещён"
                        )
                    else:
                        plans.append((child, target, str(model.get("id"))))
                    continue

                if child.name.casefold() in providers.get(harness, set()):
                    # Уже v4: проверяем, что внутри только известные модели.
                    for grandchild in sorted(p for p in child.iterdir() if p.is_dir()):
                        if (harness, grandchild.name.casefold()) not in by_hn:
                            warnings.append(
                                f"{task_dir.name}/{node.name}/{child.name}/"
                                f"{grandchild.name}: папка не сопоставлена с моделью"
                            )
                    continue

                warnings.append(
                    f"{task_dir.name}/{node.name}/{child.name}: "
                    "папка не сопоставлена с моделью"
                )

    for label in conflicts:
        print(f"Конфликт: {label}", file=sys.stderr)
    for warning in warnings:
        print(f"  ! {warning}", file=sys.stderr)
    if conflicts:
        return 1

    if not plans:
        print("Нечего перемещать: папки уже разложены по провайдерам.")
        return 0

    for source, target, model_id in plans:
        print(
            f"{source.relative_to(ANSWERS_DIR)} -> "
            f"{target.relative_to(ANSWERS_DIR)}  [{model_id}]"
        )

    if not args.write:
        print(f"\nDry-run: {len(plans)} папок. Для перемещения добавьте --write.")
        return 0

    for source, target, _ in plans:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        print(
            f"Перемещено: {source.relative_to(ANSWERS_DIR)} -> "
            f"{target.relative_to(ANSWERS_DIR)}"
        )

    print(f"\nГотово: {len(plans)} папок.")
    return 0


def source_is_inside_target(source: Path, target: Path) -> bool:
    """Защита от перемещения папки в саму себя (например, модель названа как провайдер)."""
    return source == target or source in target.parents


if __name__ == "__main__":
    sys.exit(main())
