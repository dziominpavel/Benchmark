#!/usr/bin/env python3
"""
archive_model.py — архивация и разархивация моделей в models.yaml.

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

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_PATH = REPO_ROOT / "models.yaml"


def parse_and_update(model_id: str, new_status: str) -> bool:
    """Обновляет status модели в models.yaml. Возвращает True если найдена."""
    if not MODELS_PATH.exists():
        print(f"Файл {MODELS_PATH} не найден.", file=sys.stderr)
        return False

    text = MODELS_PATH.read_text(encoding="utf-8")

    # Ищем запись модели по id
    # Паттерн: "- id: <model_id>" ... до следующего "- id:" или конца
    pattern = rf"(^\s*-\s+id:\s*{re.escape(model_id)}\s*$.*?)(?=^\s*-\s+id:|\Z)"
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)

    if not match:
        print(f"Модель '{model_id}' не найдена в {MODELS_PATH}.", file=sys.stderr)
        return False

    entry = match.group(1)

    # Проверяем, есть ли уже поле status
    status_pattern = r"^(\s*status:\s*)(\w+)\s*$"
    status_match = re.search(status_pattern, entry, re.MULTILINE)

    if status_match:
        # Обновляем существующее поле
        updated_entry = re.sub(
            status_pattern,
            rf"\g<1>{new_status}",
            entry,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Добавляем поле status после блока модели (перед notes если есть, иначе в конец)
        # Ищем notes, вставляем перед ним; иначе добавляем в конец
        notes_match = re.search(r"^(\s*notes:\s*.+)$", entry, re.MULTILINE)
        if notes_match:
            updated_entry = entry.replace(
                notes_match.group(0),
                f"    status: {new_status}\n" + notes_match.group(0),
                1,
            )
        else:
            # Добавляем в конец записи
            updated_entry = entry.rstrip() + f"\n    status: {new_status}\n"

    updated_text = text[: match.start()] + updated_entry + text[match.end():]
    MODELS_PATH.write_text(updated_text, encoding="utf-8")
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

    if parse_and_update(model_id, new_status):
        print(f"Модель '{model_id}' {action} (status: {new_status}).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
