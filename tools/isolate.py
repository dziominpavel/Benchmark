#!/usr/bin/env python3
"""
isolate.py — изоляция прогонов/вердиктов моделей друг от друга.

Команды:
    hide --task all --except <model-id>
        Перемещает все папки runs/<task-id>/<other-model-id>/ в .isolation-stash/.
        Оставляет только папку указанной модели во всех задачах.

    hide --task <task-id> --except <model-id>
        Скрывает чужие прогоны только для указанной задачи.

    restore
        Возвращает перемещённые папки из .isolation-stash/ обратно.

    hide-verdicts --task all --except <judge-id>
        Перемещает чужие вердикты verdicts/<task-id>/<participant>/<other-judge>.md
        в .isolation-stash-verdicts/. Оставляет только вердикты указанного судьи.

    hide-verdicts --task <task-id> --except <judge-id>
        Скрывает чужие вердикты только для указанной задачи.

    restore-verdicts
        Возвращает перемещённые вердикты обратно.

    status
        Показывает состояние изоляции (что спрятано).

Структура папок (новая архитектура, без волн):
    runs/<task-id>/<model-id>/run.md
    verdicts/<task-id>/<participant-anon-id>/<judge-id>.md

Зависимости: только stdlib.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows (cp1251 can't handle some Unicode)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
VERDICTS_DIR = REPO_ROOT / "verdicts"
TASKS_DIR = REPO_ROOT / "tasks"
STASH_RUNS = REPO_ROOT / ".isolation-stash"
STASH_VERDICTS = REPO_ROOT / ".isolation-stash-verdicts"
STASH_GOLDEN = REPO_ROOT / ".isolation-stash-golden"


def hide_runs(task: str, except_model: str) -> int:
    """Перемещает чужие папки прогонов в сташ + скрывает golden-answer.

    Структура: runs/<task-id>/<model-id>/
    Если task == 'all' — обрабатываем все задачи в runs/.
    Иначе — только runs/<task>/.

    Дополнительно: скрывает tasks/bugfix/*/golden-answer/ в сташ golden,
    чтобы участник не видел эталонное решение bugfix-задач.
    """
    if task == "all":
        task_dirs = [d for d in sorted(RUNS_DIR.iterdir()) if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_")]
    else:
        task_dir = RUNS_DIR / task
        if not task_dir.exists():
            print(f"Папка {task_dir} не существует — нечего скрывать.", file=sys.stderr)
            return 0
        task_dirs = [task_dir]

    STASH_RUNS.mkdir(exist_ok=True)
    moved = 0
    for task_dir in task_dirs:
        stash_task = STASH_RUNS / task_dir.name
        stash_task.mkdir(exist_ok=True)
        for model_dir in sorted(task_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            if model_dir.name == except_model:
                continue
            if model_dir.name.startswith(".") or model_dir.name.startswith("_"):
                continue
            dest = stash_task / model_dir.name
            if dest.exists():
                print(f"  ! {dest} уже существует в сташе, пропускаю", file=sys.stderr)
                continue
            shutil.move(str(model_dir), str(dest))
            print(f"  скрыт: {task_dir.name}/{model_dir.name} -> {dest}")
            moved += 1

    # Скрытие golden-answer от участников (bugfix tasks)
    golden_moved = hide_golden_answers(task)

    scope = "всех задачах" if task == "all" else f"задаче {task}"
    print(f"Изоляция прогонов: скрыто {moved} папок прогонов + {golden_moved} golden-answer в {scope}. Видна только {except_model}.")
    return 0


def hide_golden_answers(task: str) -> int:
    """Скрывает tasks/bugfix/*/golden-answer/ в сташ.

    Если task == 'all' — скрывает golden-answer для всех bugfix-задач.
    Иначе — только для tasks/bugfix/<task>/golden-answer/ (если задача bugfix).
    """
    if not TASKS_DIR.exists():
        return 0

    bugfix_dir = TASKS_DIR / "bugfix"
    if not bugfix_dir.exists():
        return 0

    if task == "all":
        bugfix_tasks = [d for d in sorted(bugfix_dir.iterdir()) if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_")]
    else:
        # Только если задача bugfix
        task_dir = bugfix_dir / task
        if not task_dir.exists():
            return 0
        bugfix_tasks = [task_dir]

    STASH_GOLDEN.mkdir(exist_ok=True)
    moved = 0
    for bf_task in bugfix_tasks:
        golden = bf_task / "golden-answer"
        if not golden.exists() or not golden.is_dir():
            continue
        dest = STASH_GOLDEN / bf_task.name
        if dest.exists():
            print(f"  ! golden-answer/{bf_task.name} уже в сташе, пропускаю", file=sys.stderr)
            continue
        shutil.move(str(golden), str(dest))
        print(f"  скрыт golden-answer: bugfix/{bf_task.name}/golden-answer -> {dest}")
        moved += 1
    return moved


def restore_golden_answers() -> int:
    """Возвращает golden-answer папки из сташа обратно."""
    if not STASH_GOLDEN.exists():
        return 0

    bugfix_dir = TASKS_DIR / "bugfix"
    restored = 0
    for golden_stash in sorted(STASH_GOLDEN.iterdir()):
        if not golden_stash.is_dir():
            continue
        target = bugfix_dir / golden_stash.name / "golden-answer"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            print(f"  ! {target} уже существует, пропускаю", file=sys.stderr)
            continue
        shutil.move(str(golden_stash), str(target))
        print(f"  восстановлен golden-answer: bugfix/{golden_stash.name}")
        restored += 1

    try:
        STASH_GOLDEN.rmdir()
    except OSError:
        pass
    return restored


def restore_runs() -> int:
    """Возвращает перемещённые папки из сташа + golden-answer."""
    if not STASH_RUNS.exists() and not STASH_GOLDEN.exists():
        print("Сташ прогонов пуст — нечего восстанавливать.")
        return 0

    restored = 0
    if STASH_RUNS.exists():
        for task_dir in sorted(STASH_RUNS.iterdir()):
            if not task_dir.is_dir():
                continue
            target_task = RUNS_DIR / task_dir.name
            target_task.mkdir(parents=True, exist_ok=True)
            for model_dir in sorted(task_dir.iterdir()):
                if not model_dir.is_dir():
                    continue
                dest = target_task / model_dir.name
                if dest.exists():
                    print(f"  ! {dest} уже существует, пропускаю", file=sys.stderr)
                    continue
                shutil.move(str(model_dir), str(dest))
                print(f"  восстановлен: {task_dir.name}/{model_dir.name} -> {dest}")
                restored += 1
            try:
                task_dir.rmdir()
            except OSError:
                pass

        try:
            STASH_RUNS.rmdir()
        except OSError:
            pass

    # Восстанавливаем golden-answer
    golden_restored = restore_golden_answers()

    print(f"Восстановление прогонов: возвращено {restored} папок + {golden_restored} golden-answer.")
    return 0


def hide_verdicts(task: str, except_judge: str) -> int:
    """Перемещает чужие вердикты в сташ.

    Структура: verdicts/<task-id>/<participant-anon-id>/<judge-id>.md
    Если task == 'all' — обрабатываем все задачи в verdicts/.
    """
    if task == "all":
        task_dirs = [d for d in sorted(VERDICTS_DIR.iterdir()) if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_")]
    else:
        task_dir = VERDICTS_DIR / task
        if not task_dir.exists():
            print(f"Папка {task_dir} не существует — нечего скрывать.", file=sys.stderr)
            return 0
        task_dirs = [task_dir]

    STASH_VERDICTS.mkdir(exist_ok=True)
    moved = 0
    for task_dir in task_dirs:
        stash_task = STASH_VERDICTS / task_dir.name
        stash_task.mkdir(exist_ok=True)
        for part_dir in sorted(task_dir.iterdir()):
            if not part_dir.is_dir():
                continue
            if part_dir.name.startswith(".") or part_dir.name.startswith("_"):
                continue
            stash_part = stash_task / part_dir.name
            stash_part.mkdir(exist_ok=True)
            for verdict_file in sorted(part_dir.iterdir()):
                if not verdict_file.is_file():
                    continue
                if verdict_file.stem == except_judge:
                    continue
                if verdict_file.name.startswith("_"):
                    continue
                dest = stash_part / verdict_file.name
                if dest.exists():
                    print(f"  ! {dest} уже существует, пропускаю", file=sys.stderr)
                    continue
                shutil.move(str(verdict_file), str(dest))
                print(f"  скрыт: {task_dir.name}/{part_dir.name}/{verdict_file.name} -> {dest}")
                moved += 1

    scope = "всех задачах" if task == "all" else f"задаче {task}"
    print(f"Изоляция вердиктов: скрыто {moved} файлов в {scope}. Виден только судья {except_judge}.")
    return 0


def restore_verdicts() -> int:
    """Возвращает перемещённые вердикты из сташа."""
    if not STASH_VERDICTS.exists():
        print("Сташ вердиктов пуст — нечего восстанавливать.")
        return 0

    restored = 0
    for task_dir in sorted(STASH_VERDICTS.iterdir()):
        if not task_dir.is_dir():
            continue
        target_task = VERDICTS_DIR / task_dir.name
        target_task.mkdir(parents=True, exist_ok=True)
        for part_dir in sorted(task_dir.iterdir()):
            if not part_dir.is_dir():
                continue
            target_part = target_task / part_dir.name
            target_part.mkdir(exist_ok=True)
            for verdict_file in sorted(part_dir.iterdir()):
                if not verdict_file.is_file():
                    continue
                dest = target_part / verdict_file.name
                if dest.exists():
                    print(f"  ! {dest} уже существует, пропускаю", file=sys.stderr)
                    continue
                shutil.move(str(verdict_file), str(dest))
                print(f"  восстановлен: {task_dir.name}/{part_dir.name}/{verdict_file.name}")
                restored += 1
            try:
                part_dir.rmdir()
            except OSError:
                pass
        try:
            task_dir.rmdir()
        except OSError:
            pass

    try:
        STASH_VERDICTS.rmdir()
    except OSError:
        pass

    print(f"Восстановление вердиктов: возвращено {restored} файлов.")
    return 0


def status() -> int:
    """Показывает состояние изоляции."""
    print("Состояние изоляции:")
    if STASH_RUNS.exists():
        count = sum(1 for _ in STASH_RUNS.rglob("*") if _.is_dir())
        print(f"  Прогоны в сташе: {STASH_RUNS} ({count} папок)")
    else:
        print("  Прогоны: не изолированы")
    if STASH_GOLDEN.exists():
        count = sum(1 for _ in STASH_GOLDEN.rglob("*") if _.is_dir())
        print(f"  Golden-answer в сташе: {STASH_GOLDEN} ({count} папок)")
    else:
        print("  Golden-answer: не изолированы")
    if STASH_VERDICTS.exists():
        count = sum(1 for _ in STASH_VERDICTS.rglob("*.md"))
        print(f"  Вердикты в сташе: {STASH_VERDICTS} ({count} файлов)")
    else:
        print("  Вердикты: не изолированы")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Изоляция прогонов и вердиктов")
    sub = parser.add_subparsers(dest="command", required=True)

    p_hide = sub.add_parser("hide", help="Скрыть чужие прогоны")
    p_hide.add_argument("--task", required=True, help="ID задачи или 'all'")
    p_hide.add_argument("--except", dest="except_model", required=True, help="model-id участника, которого не скрывать")

    sub.add_parser("restore", help="Вернуть спрятанные прогоны")

    p_hv = sub.add_parser("hide-verdicts", help="Скрыть чужие вердикты")
    p_hv.add_argument("--task", required=True, help="ID задачи или 'all'")
    p_hv.add_argument("--except", dest="except_judge", required=True, help="judge-id судьи, которого не скрывать")

    sub.add_parser("restore-verdicts", help="Вернуть спрятанные вердикты")

    sub.add_parser("status", help="Показать состояние изоляции")

    args = parser.parse_args()

    if args.command == "hide":
        return hide_runs(args.task, args.except_model)
    elif args.command == "restore":
        return restore_runs()
    elif args.command == "hide-verdicts":
        return hide_verdicts(args.task, args.except_judge)
    elif args.command == "restore-verdicts":
        return restore_verdicts()
    elif args.command == "status":
        return status()
    return 1


if __name__ == "__main__":
    sys.exit(main())
