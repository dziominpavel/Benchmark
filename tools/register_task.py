#!/usr/bin/env python3
"""
register_task.py — регистрация новой задачи бенчмарка.

Использование:
    python tools/register_task.py --title "Bug Hunt — NewModule" \
        [--slug new-module] [--project ProjectName] [--baseline <hash>]

Создаёт tasks/T-NNN-<slug>/task.md из _TEMPLATE.md, определяет следующий
номер T-NNN автоматически, активирует задачу в settings.yaml.

Зависимости: stdlib + elo.py.
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
    TASKS_DIR,
    TASK_ID_RE,
    generate_index,
    known_tasks,
    load_settings,
    save_index,
    save_settings,
)

TEMPLATE_PATH = TASKS_DIR / "_TEMPLATE.md"


def slugify(title: str) -> str:
    """Превращает название в slug: нижний регистр, не-буквы/цифры → дефис."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    if not slug:
        return "task"
    return slug


def next_task_id() -> str:
    """Следующий T-NNN: max(существующих T-NNN) + 1."""
    known = known_tasks()
    max_n = 0
    for t in known:
        m = TASK_ID_RE.match(t)
        if m:
            max_n = max(max_n, int(m.group(1)[2:]))  # "T-001" -> 1
    if not known:
        return "T-001"
    return f"T-{max_n + 1:03d}"


def unique_slug_dir(task_id: str, slug: str) -> Path:
    """Возвращает уникальный путь tasks/T-NNN-<slug>, избегая дубликатов."""
    base = TASKS_DIR / f"{task_id}-{slug}"
    if not base.exists():
        return base
    suffix = 2
    while True:
        candidate = TASKS_DIR / f"{task_id}-{slug}-{suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1


def fill_template(template: str, task_id: str, title: str, project: str, baseline: str) -> str:
    """Заполняет front matter шаблона."""
    def repl_front(m: re.Match) -> str:
        return m.group(1) + m.group(2)

    # Заменяем значения в front matter
    text = template
    text = re.sub(r'^(id:\s*)T-NNN', rf'\1{task_id}', text, flags=re.MULTILINE)
    text = re.sub(r'^(title:\s*)""', rf'\1"{title}"', text, flags=re.MULTILINE)
    text = re.sub(r'^(project:\s*)""', rf'\1"{project}"', text, flags=re.MULTILINE)
    text = re.sub(r'^(baseline_commit:\s*)""', rf'\1"{baseline}"', text, flags=re.MULTILINE)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="Регистрация задачи в бенчмарке")
    parser.add_argument("--title", required=True, help="Название задачи")
    parser.add_argument("--slug", default="", help="Slug для директории (опц.; по умолчанию из title)")
    parser.add_argument("--project", default="", help="Имя проекта-референса (опц.)")
    parser.add_argument("--baseline", default="", help="Хеш baseline коммита (опц.)")
    parser.add_argument("--auto", action="store_true", help="Авто-режим: project/baseline опциональны (по факту всегда опциональны)")
    args = parser.parse_args()

    if not TEMPLATE_PATH.exists():
        print(f"Шаблон {TEMPLATE_PATH} не найден.", file=sys.stderr)
        return 1

    task_id = next_task_id()
    slug = args.slug.strip() or slugify(args.title)
    task_dir = unique_slug_dir(task_id, slug)

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    filled = fill_template(template, task_id, args.title, args.project, args.baseline)

    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(filled, encoding="utf-8")

    settings = load_settings()
    settings["tasks"][task_id] = "active"
    settings["current_task"] = task_id
    save_settings(settings)

    index_data = generate_index()
    save_index(index_data)

    print(f"Задача '{task_id}' добавлена: {task_dir / 'task.md'}")
    print(f"Текущая таска: {task_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
