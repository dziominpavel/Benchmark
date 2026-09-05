#!/usr/bin/env python3
"""
record_verdict.py — единственная точка записи вердиктов в журнал.

Использование:
    # Вердикт судьи для задачи (слоты modelA/modelB разрешаются
    # через answers/<task>/slots.json — судья не знает реальные модели):
    python tools/record_verdict.py --task T-001 --winner b

    # Явные модели (ручной прогон / веб-форма):
    python tools/record_verdict.py --task general \
        --model-a devin-swe-1-7-max --model-b opencode-mimo-v2-5-free \
        --winner a

    # Аннулировать ошибочный вердикт (tombstone, файл не удаляется):
    python tools/record_verdict.py --void T-001/001 --reason "ошибка записи"

    # Без регенерации index.json (для пакетной записи):
    python tools/record_verdict.py --task T-001 --winner b --no-index

Зависимости: только stdlib + elo.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import record_verdict, void_matchup, REPO_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Запись вердикта в журнал matchups/"
    )
    parser.add_argument("--task", help="ID задачи (T-001) или 'general'")
    parser.add_argument("--model-a", dest="model_a", default="modelA",
                        help="Модель A: id из models.yaml или слот modelA "
                             "(по умолчанию — слот)")
    parser.add_argument("--model-b", dest="model_b", default="modelB",
                        help="Модель B: id из models.yaml или слот modelB "
                             "(по умолчанию — слот)")
    parser.add_argument("--winner", choices=["a", "b", "draw"],
                        help="Победитель: a | b | draw")
    parser.add_argument("--void", metavar="MATCHUP_ID",
                        help="Аннулировать вердикт <task>/<NNN> (tombstone)")
    parser.add_argument("--reason", default="", help="Причина аннулирования")
    parser.add_argument("--no-index", action="store_true",
                        help="Не перегенерировать index.json")
    args = parser.parse_args()

    try:
        if args.void:
            result = void_matchup(args.void, args.reason)
            print(f"✓ Вердикт {args.void} аннулирован → {result['path']}")
            return 0

        if not args.task:
            parser.error("--task обязателен для записи вердикта")
        if not args.winner:
            parser.error("--winner обязателен для записи вердикта")

        result = record_verdict(
            task=args.task,
            model_a=args.model_a,
            model_b=args.model_b,
            winner=args.winner,
            regenerate_index=not args.no_index,
        )
        v = result["verdict"]
        print(f"✓ Вердикт записан: {result['path']}")
        print(f"  seq={v['seq']}  recorded_at={v['recorded_at']}")
        for side, mid in (("A", v["model_a_id"]), ("B", v["model_b_id"])):
            snap = v["elo"][mid]
            print(f"  {side}: {mid}  ELO {snap['before']} → {snap['after']} "
                  f"({snap['delta']:+d})")
        return 0
    except ValueError as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
