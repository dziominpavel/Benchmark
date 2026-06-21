#!/usr/bin/env python3
"""
aggregate.py — агрегатор результатов прогонов в leaderboard.md.

Читает YAML front matter из runs/**/*.md, группирует по модели/категории/волне,
считает средние баллы и перегенерирует leaderboard.md.

Зависимости: только стандартная библиотека Python (front matter парсится вручную,
без PyYAML — формат ограничен плоскими ключами и простыми значениями).

Запуск:
    python tools/aggregate.py
"""

from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# --- Константы ---

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
LEADERBOARD_PATH = REPO_ROOT / "leaderboard.md"

CATEGORY_PREFIX = {
    "F": "feature",
    "B": "bugfix",
    "R": "refactor",
    "V": "review",
}
CATEGORY_LABEL = {
    "F": "Feature",
    "B": "Bugfix",
    "R": "Refactor",
    "V": "Review",
}

SCORE_KEYS = [
    "score_correctness",
    "score_build_tests",
    "score_project_rules",
    "score_code_quality",
    "score_architecture",
    "score_completeness",
    "score_notes",
]


# --- Модель данных ---


@dataclass
class Run:
    task_id: str
    model_id: str
    wave: str
    date: str
    status: str
    build_pass: str
    tests_pass: str
    openspec_validate_pass: str
    scores: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    max_score: float = 0.0
    normalized_score: float = 0.0
    diff_ref: str = ""
    path: Path = field(default_factory=lambda: Path())

    @property
    def category_prefix(self) -> str:
        """F / B / R / V — первая часть task_id до дефиса."""
        m = re.match(r"^([FBRV])-", self.task_id)
        return m.group(1) if m else "?"

    @property
    def category_label(self) -> str:
        return CATEGORY_LABEL.get(self.category_prefix, "?")


# --- Парсинг front matter ---


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Парсит YAML front matter (--- ... ---) и возвращает (dict, body).

    Поддерживает только плоские ключи: key: value и key: [a, b, c].
    Без вложенных объектов и многострочных блокков (кроме summary: |).
    """
    fm = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return fm, body
    raw, body = m.group(1), m.group(2)

    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # strip inline comments after value (но не внутри строк)
        if "  #" in val:
            val = val.split("  #")[0].strip()
        # list: [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
            fm[key] = items
            continue
        # strip quotes
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        fm[key] = val
    return fm, body


def to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if s.upper() in ("N/A", "NA", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_run(path: Path) -> Optional[Run]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ! не удалось прочитать {path}: {e}", file=sys.stderr)
        return None
    fm, _ = parse_front_matter(text)
    if not fm.get("task_id") or not fm.get("model_id"):
        return None

    scores = {}
    for k in SCORE_KEYS:
        v = to_float(fm.get(k))
        if v is not None:
            scores[k] = v

    total = to_float(fm.get("total_score")) or 0.0
    mx = to_float(fm.get("max_score")) or 0.0
    norm = to_float(fm.get("normalized_score"))
    if norm is None and mx > 0:
        norm = round(total / mx * 5, 2)
    elif norm is None:
        norm = 0.0

    return Run(
        task_id=str(fm.get("task_id", "")),
        model_id=str(fm.get("model_id", "")),
        wave=str(fm.get("wave", "")),
        date=str(fm.get("date", "")),
        status=str(fm.get("status", "")),
        build_pass=str(fm.get("build_pass", "")),
        tests_pass=str(fm.get("tests_pass", "")),
        openspec_validate_pass=str(fm.get("openspec_validate_pass", "")),
        scores=scores,
        total_score=total,
        max_score=mx,
        normalized_score=norm,
        diff_ref=str(fm.get("diff_ref", "")),
        path=path,
    )


# --- Сбор прогонов ---


def collect_runs() -> list[Run]:
    runs: list[Run] = []
    if not RUNS_DIR.exists():
        return runs
    for path in sorted(RUNS_DIR.rglob("*.md")):
        if path.name.startswith("_TEMPLATE") or path.name == "README.md":
            continue
        run = load_run(path)
        if run:
            runs.append(run)
    return runs


# --- Агрегация ---


def avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def aggregate(runs: list[Run]) -> dict:
    """Возвращает структуру для рендеринга."""
    by_model: dict[str, list[Run]] = defaultdict(list)
    by_model_cat: dict[tuple[str, str], list[Run]] = defaultdict(list)
    by_wave_model: dict[tuple[str, str], list[Run]] = defaultdict(list)
    by_cat: dict[str, list[Run]] = defaultdict(list)

    for r in runs:
        by_model[r.model_id].append(r)
        by_model_cat[(r.model_id, r.category_prefix)].append(r)
        by_wave_model[(r.wave, r.model_id)].append(r)
        by_cat[r.category_prefix].append(r)

    waves = sorted({r.wave for r in runs})
    models = sorted(by_model.keys())

    # Общий рейтинг: средний normalized_score по всем прогонам модели
    overall = []
    for m in models:
        rs = by_model[m]
        norm_scores = [r.normalized_score for r in rs if r.normalized_score > 0]
        overall.append(
            {
                "model": m,
                "runs": len(rs),
                "avg": avg(norm_scores),
                "by_cat": {
                    p: avg([r.normalized_score for r in by_model_cat[(m, p)] if r.normalized_score > 0])
                    for p in CATEGORY_PREFIX
                    if by_model_cat.get((m, p))
                },
            }
        )
    overall.sort(key=lambda x: x["avg"], reverse=True)

    # По волнам
    per_wave = {}
    for w in waves:
        rows = []
        for m in models:
            rs = by_wave_model.get((w, m), [])
            if not rs:
                continue
            norm_scores = [r.normalized_score for r in rs if r.normalized_score > 0]
            rows.append(
                {
                    "model": m,
                    "runs": len(rs),
                    "avg": avg(norm_scores),
                }
            )
        rows.sort(key=lambda x: x["avg"], reverse=True)
        per_wave[w] = rows

    # По категориям
    per_cat = {}
    for p, label in CATEGORY_LABEL.items():
        rows = []
        for m in models:
            rs = by_model_cat.get((m, p), [])
            if not rs:
                continue
            norm_scores = [r.normalized_score for r in rs if r.normalized_score > 0]
            rows.append({"model": m, "runs": len(rs), "avg": avg(norm_scores)})
        rows.sort(key=lambda x: x["avg"], reverse=True)
        per_cat[p] = (label, rows)

    return {
        "overall": overall,
        "per_wave": per_wave,
        "per_cat": per_cat,
        "total_runs": len(runs),
        "waves": waves,
        "models": models,
    }


# --- Рендеринг ---


def fmt_score(v: float) -> str:
    return f"{v:.2f}" if v > 0 else "—"


def render(data: dict) -> str:
    lines: list[str] = []
    lines.append("# Leaderboard")
    lines.append("")
    lines.append(
        "> Автоматически генерируется скриптом `tools/aggregate.py`."
    )
    lines.append(
        "> Не редактируй вручную — изменения будут перезаписаны."
    )
    lines.append("> Запуск: `python tools/aggregate.py`")
    lines.append("")

    if data["total_runs"] == 0:
        lines.append("_Нет прогонов. После создания файлов в `runs/` запусти скрипт снова._")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"_Всего прогонов: {data['total_runs']}_  ")
    lines.append(f"_Моделей: {len(data['models'])}_  ")
    lines.append(f"_Волн: {len(data['waves'])}_")
    lines.append("")

    # Общий рейтинг
    lines.append("## Общий рейтинг моделей")
    lines.append("")
    lines.append("| Модель | Прогонов | Средний балл (0–5) | F | B | R | V |")
    lines.append("|--------|----------|--------------------|---|---|---|---|")
    for row in data["overall"]:
        bc = row["by_cat"]
        lines.append(
            f"| {row['model']} | {row['runs']} | {fmt_score(row['avg'])} | "
            f"{fmt_score(bc.get('F', 0))} | {fmt_score(bc.get('B', 0))} | "
            f"{fmt_score(bc.get('R', 0))} | {fmt_score(bc.get('V', 0))} |"
        )
    lines.append("")

    # По волнам
    if data["per_wave"]:
        lines.append("## По волнам")
        lines.append("")
        for w, rows in data["per_wave"].items():
            lines.append(f"### {w}")
            lines.append("")
            lines.append("| Модель | Прогонов | Средний балл |")
            lines.append("|--------|----------|--------------|")
            for row in rows:
                lines.append(
                    f"| {row['model']} | {row['runs']} | {fmt_score(row['avg'])} |"
                )
            lines.append("")

    # По категориям
    lines.append("## По категориям")
    lines.append("")
    for p, (label, rows) in data["per_cat"].items():
        lines.append(f"### {label} ({p})")
        lines.append("")
        if not rows:
            lines.append("_Нет прогонов._")
            lines.append("")
            continue
        lines.append("| Модель | Прогонов | Средний балл |")
        lines.append("|--------|----------|--------------|")
        for row in rows:
            lines.append(
                f"| {row['model']} | {row['runs']} | {fmt_score(row['avg'])} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_Последнее обновление: сгенерировано `tools/aggregate.py`_")
    return "\n".join(lines)


# --- Main ---


def main() -> int:
    if not RUNS_DIR.exists():
        print(f"Папка {RUNS_DIR} не существует — нет прогонов.", file=sys.stderr)
        # всё равно пишем пустой leaderboard
    runs = collect_runs()
    print(f"Найдено прогонов: {len(runs)}")
    data = aggregate(runs)
    out = render(data)
    LEADERBOARD_PATH.write_text(out, encoding="utf-8")
    print(f"Leaderboard записан: {LEADERBOARD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
