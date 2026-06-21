#!/usr/bin/env python3
"""
generate_checklist.py — генерация markdown-файлов с готовыми промптами для копипаста.

Генерирует чеклисты для каждой фазы:
    --phase 1     Генерация задач (1 сессия с генератором)
    --phase 1.5   Resolve (1 сессия resolver для bugfix)
    --phase 2     Выполнение (по 1 сессии на участника, батч)
    --phase 3     Оценка (по 1-2 сессии на судью, батч)
    --participant <model-id>  Для инкремента: только новый участник

Читает: models.yaml, judges.yaml, tasks/, runs/, verdicts/
Создаёт: checklist-phase-<N>.md в корне репозитория.

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
TASKS_DIR = REPO_ROOT / "tasks"
RUNS_DIR = REPO_ROOT / "runs"
VERDICTS_DIR = REPO_ROOT / "verdicts"
MODELS_FILE = REPO_ROOT / "models.yaml"
JUDGES_FILE = REPO_ROOT / "judges.yaml"


def load_models() -> list[str]:
    if not MODELS_FILE.exists():
        return []
    text = MODELS_FILE.read_text(encoding="utf-8")
    return re.findall(r"^\s*-\s+id:\s*(\S+)", text, re.MULTILINE)


def load_judges() -> list[str]:
    if not JUDGES_FILE.exists():
        return []
    text = JUDGES_FILE.read_text(encoding="utf-8")
    return re.findall(r"^\s*-\s+(\S+)", text, re.MULTILINE)


def find_tasks() -> list[dict]:
    tasks = []
    if not TASKS_DIR.exists():
        return tasks
    for cat_dir in sorted(TASKS_DIR.iterdir()):
        if not cat_dir.is_dir() or cat_dir.name.startswith(".") or cat_dir.name.startswith("_"):
            continue
        for task_dir in sorted(cat_dir.iterdir()):
            if not task_dir.is_dir() or task_dir.name.startswith(".") or task_dir.name.startswith("_"):
                continue
            task_file = task_dir / "task.md"
            if task_file.exists():
                tasks.append({
                    "id": task_dir.name,
                    "category": cat_dir.name,
                    "path": str(task_file),
                    "dir": str(task_dir),
                })
    return tasks


def find_runs_for_model(model_id: str) -> list[str]:
    """Возвращает список task_id, для которых есть прогон model_id."""
    run_tasks = []
    if not RUNS_DIR.exists():
        return run_tasks
    for task_dir in sorted(RUNS_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name.startswith(".") or task_dir.name.startswith("_"):
            continue
        model_dir = task_dir / model_id
        if model_dir.exists() and (model_dir / "run.md").exists():
            run_tasks.append(task_dir.name)
    return run_tasks


def find_completed_runs() -> list[dict]:
    """Все прогоны с run.md. Возвращает [{task_id, model_id}]."""
    runs = []
    if not RUNS_DIR.exists():
        return runs
    for task_dir in sorted(RUNS_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name.startswith(".") or task_dir.name.startswith("_"):
            continue
        for model_dir in sorted(task_dir.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith(".") or model_dir.name.startswith("_"):
                continue
            if (model_dir / "run.md").exists():
                runs.append({"task_id": task_dir.name, "model_id": model_dir.name})
    return runs


def find_verdicts_for_judge(judge_id: str) -> list[str]:
    """Возвращает список task_id, для которых judge уже написал вердикт."""
    verdict_tasks = []
    if not VERDICTS_DIR.exists():
        return verdict_tasks
    for task_dir in sorted(VERDICTS_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name.startswith(".") or task_dir.name.startswith("_"):
            continue
        for part_dir in sorted(task_dir.iterdir()):
            if not part_dir.is_dir():
                continue
            if (part_dir / f"{judge_id}.md").exists():
                verdict_tasks.append(task_dir.name)
                break
    return verdict_tasks


def generate_phase_1() -> str:
    """Чеклист для генерации задач."""
    lines = [
        "# Phase 1: Генерация задач",
        "",
        "## Перед сессией",
        "1. Открой новый чат с моделью-генератором",
        "2. Вставь промпт ниже",
        "3. После: проверь созданные задачи в tasks/",
        "",
        "## Промпт для генератора",
        "",
        "```",
        "Ты — генератор задач для бенчмарка. Прочитай generators/_PROMPT.md.",
        "Создай 4 задачи (1 feature + 1 bugfix + 1 refactor + 1 review) для проекта <PROJECT>.",
        "",
        "Для каждой задачи:",
        "1. Определи baseline_commit: cd C:/projects/<PROJECT> && git rev-parse HEAD",
        "2. Создай файл tasks/<cat>/<ID>/task.md по шаблону tasks/_TEMPLATE.md",
        "3. Заполни front matter: id, title, category, difficulty, project, baseline_commit, tags",
        "4. Заполни секции: Контекст, Постановка, Критерии приёмки, Ограничения",
        "",
        "НЕ решай задачи. Для bugfix — НЕ перечисляй конкретные баги.",
        "```",
        "",
        "## После сессии",
        "- [ ] Проверь, что 4 файла созданы в tasks/feature/, tasks/bugfix/, tasks/refactor/, tasks/review/",
        "- [ ] Проверь, что в каждом есть baseline_commit",
        "- [ ] При необходимости — отредактируй задачи вручную",
    ]
    return "\n".join(lines)


def generate_phase_1_5() -> str:
    """Чеклист для resolve (golden answer только для bugfix)."""
    tasks = find_tasks()
    bugfix_tasks = [t for t in tasks if t["category"] == "bugfix"]

    lines = [
        "# Phase 1.5: Resolve (golden answer для bugfix)",
        "",
        "> Golden answer создаётся ТОЛЬКО для bugfix-задач.",
        "> Для feature/refactor/review — нет golden.",
        "",
    ]

    if not bugfix_tasks:
        lines.extend(["", "Bugfix-задач не найдено. Пропусти эту фазу.", ""])
        return "\n".join(lines)

    lines.extend([
        "## Перед каждой сессией resolver'а",
        "1. Resolver НЕ должен быть генератором этой задачи",
        "2. Открой новый чат с моделью-resolver",
        "3. Вставь промпт",
        "4. После: проверь golden-answer/answer.md + diff.patch",
        "",
    ])

    for t in bugfix_tasks:
        lines.extend([
            f"## {t['id']}",
            "",
            "```",
            f"Ты — resolver. Прочитай AGENTS.md → раздел Resolver.",
            f"Реши задачу {t['id']} в C:/projects/<PROJECT> на baseline_commit из tasks/bugfix/{t['id']}/task.md.",
            f"Сохрани golden-answer/answer.md + diff.patch в tasks/bugfix/{t['id']}/golden-answer/.",
            "Сообщи сложность (1-3) и время.",
            "```",
            "",
            f"- [ ] {t['id']}: resolver создал golden answer",
            "",
        ])
    return "\n".join(lines)


def generate_phase_2(participant: str | None = None) -> str:
    """Чеклист для выполнения (батч)."""
    models = load_models()
    tasks = find_tasks()

    if participant:
        models = [m for m in models if m == participant]

    if not models:
        return "# Phase 2: Выполнение\n\nМоделей не найдено. Зарегистрируй через register_model.py.\n"
    if not tasks:
        return "# Phase 2: Выполнение\n\nЗадач не найдено. Создай задачи через Phase 1.\n"

    task_ids = [t["id"] for t in tasks]
    task_paths = "\n".join(f"#    - {t['path']}" for t in tasks)

    lines = [
        "# Phase 2: Выполнение (батч)",
        "",
        f"> 1 сессия = все задачи участника. Всего: {len(models)} сессий.",
        "",
        "## Перед каждой сессией участника",
        "1. python tools/isolate.py hide --task all --except <model-id>",
        "2. Открой новый чат, вставь промпт",
        "3. После: git checkout . && git clean -fd в папке проекта",
        "4. python tools/isolate.py restore",
        "5. Отметь чекбокс",
        "",
    ]

    for model in models:
        existing_runs = find_runs_for_model(model)
        done_marker = " ✓ уже выполнено" if len(existing_runs) == len(tasks) else ""

        lines.extend([
            f"## {model}{done_marker}",
            "",
            "```",
            f"Выполни задачи: {', '.join(task_ids)}.",
            "Прочитай AGENTS.md.",
            "",
            "Для каждой задачи:",
            "1. Прочитай файл задачи (путь указан ниже)",
            "2. cd C:/projects/<PROJECT> && git checkout <baseline_commit из task.md>",
            "3. Выполни задачу",
            "4. Сохрани прогон: runs/<task-id>/" + model + "/run.md (по шаблону runs/_TEMPLATE.md)",
            "5. Сохрани diff: git diff > runs/<task-id>/" + model + "/diff.patch (для feature/bugfix/refactor)",
            "6. Очистка: git checkout . && git clean -fd",
            "7. Переходи к следующей задаче",
            "",
            "Файлы задач:",
            task_paths,
            "```",
            "",
            f"- [ ] {model}: все {len(tasks)} задач выполнены",
            "",
        ])
    return "\n".join(lines)


def generate_phase_3(participant: str | None = None) -> str:
    """Чеклист для оценки (батч)."""
    judges = load_judges()
    runs = find_completed_runs()

    if participant:
        runs = [r for r in runs if r["model_id"] == participant]

    if not judges:
        return "# Phase 3: Оценка\n\nСудей не найдено. Заполни judges.yaml.\n"
    if not runs:
        return "# Phase 3: Оценка\n\nПрогонов не найдено. Запусти Phase 2 сначала.\n"

    # Группируем прогоны по участникам
    by_model: dict[str, list[str]] = {}
    for r in runs:
        by_model.setdefault(r["model_id"], []).append(r["task_id"])

    models_list = sorted(by_model.keys())
    # Разбиваем на батчи по 2-3 участника
    batches = []
    for i in range(0, len(models_list), 3):
        batches.append(models_list[i:i+3])

    lines = [
        "# Phase 3: Оценка (батч)",
        "",
        f"> 1 сессия судьи = 2-3 участника × все задачи. Всего: {len(judges) * len(batches)} сессий.",
        "",
        "## Перед каждой сессией судьи",
        "1. python tools/isolate.py hide-verdicts --task all --except <judge-id>",
        "2. python tools/assign_judges.py --distribute (если ещё не запускал)",
        "3. Открой новый чат, вставь промпт",
        "4. После: python tools/isolate.py restore-verdicts",
        "5. Отметь чекбокс",
        "",
    ]

    for judge in judges:
        existing_verdicts = find_verdicts_for_judge(judge)
        lines.append(f"## Судья: {judge}\n")

        for batch_idx, batch in enumerate(batches, 1):
            batch_models = batch
            batch_runs = []
            for m in batch_models:
                for task_id in by_model[m]:
                    batch_runs.append((task_id, m))

            lines.extend([
                f"### Батч {batch_idx}: {', '.join(batch_models)} ({len(batch_runs)} прогонов)",
                "",
                "```",
                f"Ты — судья. Прочитай judges/_PROMPT.md и judges/_RUBRIC.md.",
                f"Оцени прогоны участников: {', '.join(batch_models)}",
                "",
                "Для каждого прогона:",
                "1. Прочитай задачу: tasks/<cat>/<task-id>/task.md",
                "2. Прочитай анонимизированный прогон: .anon-copies/<task-id>/<participant>/run.md",
                "3. Прочитай diff.patch (если есть)",
                "4. Для bugfix — прочитай golden-answer/ (если есть)",
                "5. Оцени по рубрикатору, каждый балл с обоснованием",
                f"6. Сохрани вердикт: verdicts/<task-id>/<participant-anon>/" + judge + ".md",
                "",
                f"Прогоны для оценки: {len(batch_runs)}",
                "```",
                "",
                f"- [ ] {judge} батч {batch_idx}: оценено {len(batch_runs)} прогонов",
                "",
            ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Генерация чеклистов с промптами")
    parser.add_argument("--phase", required=True, choices=["1", "1.5", "2", "3"], help="Фаза")
    parser.add_argument("--participant", default="", help="model-id для инкремента (Phase 2/3)")
    args = parser.parse_args()

    participant = args.participant if args.participant else None

    if args.phase == "1":
        content = generate_phase_1()
        filename = "checklist-phase-1.md"
    elif args.phase == "1.5":
        content = generate_phase_1_5()
        filename = "checklist-phase-1.5.md"
    elif args.phase == "2":
        content = generate_phase_2(participant)
        filename = "checklist-phase-2.md"
    elif args.phase == "3":
        content = generate_phase_3(participant)
        filename = "checklist-phase-3.md"
    else:
        print(f"Неизвестная фаза: {args.phase}", file=sys.stderr)
        return 1

    output_path = REPO_ROOT / filename
    output_path.write_text(content, encoding="utf-8")
    print(f"Чеклист создан: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
