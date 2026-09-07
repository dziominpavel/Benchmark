#!/usr/bin/env python3
"""archive_model.py — архивация и разархивация моделей в models.yaml.

Использование:
    python tools/archive_model.py <model-id>           # заархивировать
    python tools/archive_model.py --restore <model-id> # разархивировать

Архивная модель:
  - status: archived в models.yaml
  - ELO замораживается (нет новых вердиктов)
  - История сохраняется
  - В leaderboard отображается серым (при включении фильтра)

Зависимости: только stdlib.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from elo import generate_index, save_index, MODELS_PATH
from register_model import parse_existing, format_model


def update_status(model_id: str, new_status: str) -> bool:
    """Обновляет status модели в models.yaml и пересчитывает index.json."""
    if not MODELS_PATH.exists():
        print(f"Файл {MODELS_PATH} не найден.", file=sys.stderr)
        return False

    text = MODELS_PATH.read_text(encoding="utf-8")
    models, preamble = parse_existing(text)

    found = False
    for m in models:
        if m["id"] == model_id:
            m["status"] = new_status
            found = True
            break

    if not found:
        print(f"Модель '{model_id}' не найдена в {MODELS_PATH}.", file=sys.stderr)
        return False

    models.sort(key=lambda m: m["id"])

    out = preamble.rstrip() + "\n\nmodels:\n"
    for m in models:
        out += format_model(m) + "\n"

    MODELS_PATH.write_text(out, encoding="utf-8")

    # Пересчитываем index.json, чтобы рекомендации и фильтр отразили новый статус
    try:
        save_index(generate_index())
    except Exception as e:
        print(f"WARNING: не удалось обновить index.json: {e}", file=sys.stderr)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Архивация модели в models.yaml")
    parser.add_argument("model_id", nargs="?", help="ID модели для архивации")
    parser.add_argument("--restore", metavar="ID", help="Разархивировать модель")
    args = parser.parse_args()

    if args.restore:
        model_id = args.restore
        new_status = "active"
        action = "разархивирована"
    elif args.model_id:
        model_id = args.model_id
        new_status = "archived"
        action = "заархивирована"
    else:
        parser.print_help()
        return 1

    if update_status(model_id, new_status):
        print(f"Модель '{model_id}' {action} (status: {new_status}).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
