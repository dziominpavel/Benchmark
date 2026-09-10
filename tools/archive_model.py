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

Правила архивации (жёсткий блок, см. MIN_GAMES и BOTTOM_K ниже):
  - у модели >= MIN_GAMES вердиктов — меньше нельзя, ELO ещё в
    провизорной зоне (K=40) и заморозка зафиксирует шум;
  - модель входит в нижние BOTTOM_K активных по ELO — архивируем
    только самых слабых, не «кого захотелось».
Разархивация (--restore) правилами не ограничивается.

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
from elo import (
    generate_index, save_index, MODELS_PATH,
    load_matchups, recalculate, DEFAULT_ELO,
)
from register_model import parse_existing, format_model

# Правила архивации
MIN_GAMES = 10  # минимум вердиктов: совпадает с границей K=40→32 в elo.py
BOTTOM_K = 3    # архивировать можно только модели из нижних K активных по ELO


def _active_ranking(models: list[dict]) -> tuple[dict, list[tuple[str, int]]]:
    """Пересчёт ELO + список активных моделей по возрастанию ELO."""
    elo_data = recalculate(load_matchups(), [m["id"] for m in models])
    active = sorted(
        (
            (m["id"], elo_data["models"].get(m["id"], {}).get("elo", DEFAULT_ELO))
            for m in models
            if m.get("status", "active") != "archived"
        ),
        key=lambda x: x[1],
    )
    return elo_data, active


def check_archivable(model_id: str, models: list[dict]) -> tuple[list[str], list[str] | None]:
    """→ (причины отказа, id архивируемых сейчас). Пустые причины = можно.
    eligible=None при ошибках вида «не найдена» / «уже в архиве» — подсказку
    показывать не имеет смысла."""
    model = next((m for m in models if m["id"] == model_id), None)
    if model is None:
        return [f"модель '{model_id}' не найдена в реестре"], None
    if model.get("status", "active") == "archived":
        return [f"модель '{model_id}' уже в архиве"], None

    elo_data, active = _active_ranking(models)
    info = elo_data["models"].get(model_id, {"elo": DEFAULT_ELO, "games": 0})
    reasons = []

    if info["games"] < MIN_GAMES:
        reasons.append(
            f"мало игр: {info['games']} < {MIN_GAMES} "
            f"(ELO ещё нестабилен, провизорная зона K=40)"
        )

    bottom_ids = {mid for mid, _ in active[:BOTTOM_K]}
    if model_id not in bottom_ids:
        rank = next(i for i, (mid, _) in enumerate(active) if mid == model_id)
        reasons.append(
            f"не в нижних {BOTTOM_K} активных по ELO: "
            f"{rank + 1}-е место снизу из {len(active)} (ELO {info['elo']})"
        )

    eligible = [
        mid for mid, _ in active[:BOTTOM_K]
        if mid != model_id
        and elo_data["models"].get(mid, {}).get("games", 0) >= MIN_GAMES
    ]
    return reasons, eligible


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

    if new_status == "archived" and MODELS_PATH.exists():
        models, _ = parse_existing(MODELS_PATH.read_text(encoding="utf-8"))
        reasons, eligible = check_archivable(model_id, models)
        if reasons:
            print(f"Модель '{model_id}' нельзя заархивировать:", file=sys.stderr)
            for r in reasons:
                print(f"  - {r}", file=sys.stderr)
            if eligible:
                print(f"Сейчас можно архивировать: {', '.join(eligible)}", file=sys.stderr)
            elif eligible is not None:
                print("Сейчас ни одна модель не проходит правила архивации.", file=sys.stderr)
            return 1

    if update_status(model_id, new_status):
        print(f"Модель '{model_id}' {action} (status: {new_status}).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
