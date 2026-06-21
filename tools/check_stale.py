#!/usr/bin/env python3
"""
check_stale.py — проверка устаревания задач по baseline_commit vs HEAD проекта.

Для каждой задачи в tasks/<cat>/<id>/task.md:
  1. Читает baseline_commit и project из front matter.
  2. Считает количество коммитов с baseline до HEAD в C:/projects/<Project>.
  3. Если коммитов > порога (по умолчанию 10) — помечает stale.

Прогоны на устаревшей задаче остаются валидными (сравнение честное,
если все на одном commit). stale — сигнал пользователю создать новую задачу.

Зависимости: только stdlib (вызывает git через subprocess).
Запуск:
    python tools/check_stale.py
    python tools/check_stale.py --threshold 5
    python tools/check_stale.py --output stale-report.md
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = REPO_ROOT / "tasks"
PROJECTS_ROOT = Path("C:/projects")

DEFAULT_THRESHOLD = 10


def parse_front_matter(text: str) -> dict:
    fm: dict = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.DOTALL)
    if not m:
        return fm
    raw = m.group(1)
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        fm[key] = val
    return fm


def find_tasks() -> list[Path]:
    """Находит все task.md в tasks/<cat>/<id>/task.md."""
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
                tasks.append(task_file)
    return tasks


def count_commits_since(project_path: Path, baseline_commit: str) -> int | None:
    """Считает количество коммитов с baseline (exclusive) до HEAD."""
    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{baseline_commit}..HEAD"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return int(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return None


def check_stale(threshold: int) -> list[dict]:
    """Проверяет все задачи. Возвращает список отчётов."""
    reports = []
    for task_file in find_tasks():
        text = task_file.read_text(encoding="utf-8")
        fm = parse_front_matter(text)

        task_id = fm.get("id", task_file.parent.name)
        project = fm.get("project", "")
        baseline = fm.get("baseline_commit", "")

        report = {
            "task_id": task_id,
            "project": project,
            "baseline_commit": baseline,
            "commits_behind": None,
            "status": "unknown",
            "path": str(task_file),
        }

        if not baseline:
            report["status"] = "error"
            report["error"] = "no baseline_commit in front matter"
            reports.append(report)
            continue

        if not project:
            report["status"] = "error"
            report["error"] = "no project in front matter"
            reports.append(report)
            continue

        project_path = PROJECTS_ROOT / project.capitalize()
        if not project_path.exists():
            # Попробуем как есть
            project_path = PROJECTS_ROOT / project
            if not project_path.exists():
                report["status"] = "error"
                report["error"] = f"project not found at {PROJECTS_ROOT / project}"
                reports.append(report)
                continue

        count = count_commits_since(project_path, baseline)
        report["commits_behind"] = count

        if count is None:
            report["status"] = "error"
            report["error"] = "git rev-list failed (commit not found?)"
        elif count == 0:
            report["status"] = "fresh"
        elif count <= threshold:
            report["status"] = "fresh"
        else:
            report["status"] = "stale"

        reports.append(report)
    return reports


def render_report(reports: list[dict], threshold: int) -> str:
    lines = [
        "# Stale Report",
        "",
        f"> Порог: {threshold} коммитов. Прогоны на устаревших задачах валидны",
        f"> (сравнение честное, если все на одном commit).",
        "",
        "| Задача | Проект | Коммитов с baseline | Статус |",
        "|--------|--------|---------------------|--------|",
    ]
    for r in reports:
        count = r["commits_behind"]
        count_str = str(count) if count is not None else "?"
        status = r["status"]
        if status == "stale":
            status = f"⚠ stale ({count} > {threshold})"
        elif status == "error":
            status = f"❌ error: {r.get('error', '')}"
        elif status == "fresh":
            status = "✓ fresh"
        lines.append(f"| {r['task_id']} | {r['project']} | {count_str} | {status} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Проверка устаревания задач")
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help=f"Порог коммитов (по умолчанию {DEFAULT_THRESHOLD})")
    parser.add_argument("--output", default="", help="Сохранить отчёт в файл (по умолчанию только консоль)")
    args = parser.parse_args()

    reports = check_stale(args.threshold)

    if not reports:
        print("Задач не найдено. Создай задачи в tasks/<cat>/<id>/task.md.")
        return 0

    # Консольный вывод
    print(f"{'Задача':<25} {'Проект':<15} {'Коммитов':<10} {'Статус'}")
    print("-" * 70)
    for r in reports:
        count = r["commits_behind"]
        count_str = str(count) if count is not None else "?"
        status = r["status"]
        if status == "stale":
            status = f"⚠ stale ({count} > {args.threshold})"
        elif status == "error":
            status = f"❌ {r.get('error', '')}"
        elif status == "fresh":
            status = "✓ fresh"
        print(f"{r['task_id']:<25} {r['project']:<15} {count_str:<10} {status}")

    stale_count = sum(1 for r in reports if r["status"] == "stale")
    error_count = sum(1 for r in reports if r["status"] == "error")
    fresh_count = sum(1 for r in reports if r["status"] == "fresh")
    print(f"\nИтого: {fresh_count} fresh, {stale_count} stale, {error_count} error")

    if args.output:
        report_text = render_report(reports, args.threshold)
        Path(args.output).write_text(report_text, encoding="utf-8")
        print(f"Отчёт сохранён: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
