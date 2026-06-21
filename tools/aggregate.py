#!/usr/bin/env python3
"""
aggregate.py — агрегатор вердиктов судей в leaderboard.md (кумулятивный).

Новая архитектура (без волн):
    verdicts/<task-id>/<participant-anon-id>/<judge-id>.md
    anonymization.yaml (в корне) — глобальная карта
    leaderboard.md — кумулятивный, обновляется при каждом запуске

Генерирует leaderboard.md с:
  - общим рейтингом моделей (средний нормализованный балл)
  - разбивкой по категориям (F/B/R/V)
  - разбивкой по задачам
  - качеством судей (согласованность)
  - картой назначений (задача × участник × судьи × оценки × медиана)
  - пометкой disputed (разброс > 2)

Зависимости: только стандартная библиотека Python.
Запуск: python tools/aggregate.py
"""

from __future__ import annotations

import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
VERDICTS_DIR = REPO_ROOT / "verdicts"
ANON_FILE = REPO_ROOT / "anonymization.yaml"
LEADERBOARD_PATH = REPO_ROOT / "leaderboard.md"

CATEGORY_PREFIX = {"F": "feature", "B": "bugfix", "R": "refactor", "V": "review"}
CATEGORY_LABEL = {"F": "Feature", "B": "Bugfix", "R": "Refactor", "V": "Review"}

SCORE_KEYS = [
    "score_correctness",
    "score_build_tests",
    "score_project_rules",
    "score_code_quality",
    "score_architecture",
    "score_completeness",
    "score_notes",
]
REVIEW_SCORE_KEYS = [
    "score_depth",
    "score_justification",
    "score_completeness_review",
    "score_specificity",
    "score_prioritization",
    "score_style",
]


@dataclass
class Verdict:
    task_id: str
    participant: str  # анонимизированный ("Участник A")
    judge_id: str
    date: str
    scores: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    max_score: float = 0.0
    normalized_score: float = 0.0
    patch_applied: str = ""
    tests_run_by_judge: str = ""
    path: Path = field(default_factory=lambda: Path())

    @property
    def category_prefix(self) -> str:
        m = re.match(r"^([FBRV])-", self.task_id)
        return m.group(1) if m else "?"

    @property
    def category_label(self) -> str:
        return CATEGORY_LABEL.get(self.category_prefix, "?")


def parse_front_matter(text: str) -> tuple[dict, str]:
    fm: dict = {}
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
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
            fm[key] = items
            continue
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


def load_verdict(path: Path) -> Optional[Verdict]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ! не удалось прочитать {path}: {e}", file=sys.stderr)
        return None
    fm, body = parse_front_matter(text)
    if not fm.get("task_id") or not fm.get("judge_id"):
        return None

    has_justification = bool(re.search(r"Обоснование:", body, re.IGNORECASE))
    if not has_justification:
        print(f"  ! вердикт без обоснования: {path} — исключён", file=sys.stderr)
        return None

    all_keys = SCORE_KEYS + REVIEW_SCORE_KEYS
    scores = {}
    for k in all_keys:
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

    return Verdict(
        task_id=str(fm.get("task_id", "")),
        participant=str(fm.get("participant", "")),
        judge_id=str(fm.get("judge_id", "")),
        date=str(fm.get("date", "")),
        scores=scores,
        total_score=total,
        max_score=mx,
        normalized_score=norm,
        patch_applied=str(fm.get("patch_applied", "")),
        tests_run_by_judge=str(fm.get("tests_run_by_judge", "")),
        path=path,
    )


def load_anonymization() -> dict[str, str]:
    """Возвращает {anon_id: model_id} (обратная карта для деанонимизации)."""
    if not ANON_FILE.exists():
        return {}
    text = ANON_FILE.read_text(encoding="utf-8")
    reverse = {}
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^(\S+):\s*"(.+)"', line)
        if m:
            reverse[m.group(2)] = m.group(1)  # anon -> model
    return reverse


def collect_verdicts() -> list[Verdict]:
    verdicts: list[Verdict] = []
    if not VERDICTS_DIR.exists():
        return verdicts
    for path in sorted(VERDICTS_DIR.rglob("*.md")):
        if path.name.startswith("_TEMPLATE") or path.name == "README.md":
            continue
        v = load_verdict(path)
        if v:
            verdicts.append(v)
    return verdicts


def median_or_none(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return round(statistics.median(values), 2)


def aggregate(verdicts: list[Verdict]) -> dict:
    anon_map = load_anonymization()

    # Группировка по (task_id, participant_anon)
    by_run: dict[tuple[str, str], list[Verdict]] = defaultdict(list)
    for v in verdicts:
        by_run[(v.task_id, v.participant)].append(v)

    runs_agg = []
    for (task_id, anon_part), vs in sorted(by_run.items()):
        model_id = anon_map.get(anon_part, anon_part)
        norm_scores = [v.normalized_score for v in vs if v.normalized_score > 0]
        median_norm = median_or_none(norm_scores) or 0.0

        if len(norm_scores) >= 2:
            spread = max(norm_scores) - min(norm_scores)
        else:
            spread = 0.0
        disputed = spread > 2.0

        judge_scores = []
        for v in vs:
            judge_scores.append(
                {"judge": v.judge_id, "score": v.normalized_score, "path": str(v.path)}
            )

        cat = re.match(r"^([FBRV])-", task_id)
        cat_prefix = cat.group(1) if cat else "?"

        runs_agg.append(
            {
                "task_id": task_id,
                "category": cat_prefix,
                "anon_participant": anon_part,
                "model_id": model_id,
                "median_score": median_norm,
                "spread": round(spread, 2),
                "disputed": disputed,
                "judges": judge_scores,
                "verdict_count": len(vs),
            }
        )

    # По моделям
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in runs_agg:
        by_model[r["model_id"]].append(r)

    models_agg = []
    for model_id, runs in sorted(by_model.items()):
        medians = [r["median_score"] for r in runs if r["median_score"] > 0]
        avg = round(statistics.mean(medians), 2) if medians else 0.0
        by_cat = defaultdict(list)
        for r in runs:
            by_cat[r["category"]].append(r["median_score"])
        cat_avgs = {}
        for cat, scores in by_cat.items():
            cat_avgs[cat] = round(statistics.mean(scores), 2) if scores else 0.0
        models_agg.append({
            "model_id": model_id,
            "runs": len(runs),
            "avg_score": avg,
            "cat_scores": cat_avgs,
        })
    models_agg.sort(key=lambda m: m["avg_score"], reverse=True)

    # По судьям (качество — согласованность)
    by_judge: dict[str, list[float]] = defaultdict(list)
    for r in runs_agg:
        for j in r["judges"]:
            by_judge[j["judge"]].append(j["score"])
    judges_agg = []
    for judge_id, scores in sorted(by_judge.items()):
        avg = round(statistics.mean(scores), 2) if scores else 0.0
        spread = round(max(scores) - min(scores), 2) if len(scores) >= 2 else 0.0
        judges_agg.append({
            "judge_id": judge_id,
            "verdicts": len(scores),
            "avg_given": avg,
            "spread": spread,
        })

    return {
        "runs": runs_agg,
        "models": models_agg,
        "judges": judges_agg,
    }


def render_leaderboard(data: dict) -> str:
    lines = [
        "# Leaderboard",
        "",
        "> Кумулятивный рейтинг моделей. Генерируется `aggregate.py`.",
        "> Не редактируй вручную — файл перезаписывается при каждом запуске.",
        "",
    ]

    models = data["models"]
    if not models:
        lines.extend([
            "## Общий рейтинг моделей",
            "",
            "Нет вердиктов. Запусти судей и `assign_judges.py --distribute`.",
            "",
        ])
        return "\n".join(lines)

    # Общий рейтинг
    lines.extend(["## Общий рейтинг моделей", ""])
    lines.append("| Модель | Прогонов | Средний балл | F | B | R | V |")
    lines.append("|--------|----------|--------------|---|---|---|---|")
    for m in models:
        cs = m["cat_scores"]
        lines.append(
            f"| {m['model_id']} | {m['runs']} | {m['avg_score']} | "
            f"{cs.get('F', '-')} | {cs.get('B', '-')} | {cs.get('R', '-')} | {cs.get('V', '-')} |"
        )
    lines.append("")

    # По категориям
    lines.extend(["## По категориям", ""])
    for cat in ["F", "B", "R", "V"]:
        cat_models = [m for m in models if cat in m["cat_scores"]]
        if not cat_models:
            continue
        cat_models.sort(key=lambda m: m["cat_scores"][cat], reverse=True)
        lines.append(f"### {CATEGORY_LABEL[cat]}")
        lines.append("")
        lines.append("| Модель | Балл |")
        lines.append("|--------|------|")
        for m in cat_models:
            lines.append(f"| {m['model_id']} | {m['cat_scores'][cat]} |")
        lines.append("")

    # По задачам
    lines.extend(["## По задачам", ""])
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in data["runs"]:
        by_task[r["task_id"]].append(r)
    for task_id, runs in sorted(by_task.items()):
        lines.append(f"### {task_id}")
        lines.append("")
        lines.append("| Участник | Медиана | Судьи | Disputed |")
        lines.append("|----------|---------|-------|----------|")
        for r in sorted(runs, key=lambda x: x["median_score"], reverse=True):
            judges_str = ", ".join(f"{j['judge']}:{j['score']}" for j in r["judges"])
            disputed = "⚠ disputed" if r["disputed"] else ""
            lines.append(f"| {r['model_id']} | {r['median_score']} | {judges_str} | {disputed} |")
        lines.append("")

    # Качество судей
    lines.extend(["## Качество судей", ""])
    if data["judges"]:
        lines.append("| Судья | Вердиктов | Средний балл | Разброс |")
        lines.append("|-------|-----------|--------------|---------|")
        for j in data["judges"]:
            lines.append(f"| {j['judge_id']} | {j['verdicts']} | {j['avg_given']} | {j['spread']} |")
        lines.append("")
    else:
        lines.append("Нет данных о судьях.")
        lines.append("")

    # Карта назначений
    lines.extend(["## Карта назначений", ""])
    if data["runs"]:
        lines.append("| Задача | Участник | Судья 1 | Судья 2 | Судья 3 | Медиана | Disputed |")
        lines.append("|--------|----------|---------|---------|---------|---------|----------|")
        for r in data["runs"]:
            js = r["judges"]
            j1 = js[0]["score"] if len(js) > 0 else "-"
            j2 = js[1]["score"] if len(js) > 1 else "-"
            j3 = js[2]["score"] if len(js) > 2 else "-"
            disputed = "⚠" if r["disputed"] else ""
            lines.append(
                f"| {r['task_id']} | {r['model_id']} | {j1} | {j2} | {j3} | {r['median_score']} | {disputed} |"
            )
        lines.append("")
    else:
        lines.append("Нет назначений.")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    verdicts = collect_verdicts()
    if not verdicts:
        print("Вердиктов не найдено. Leaderboard будет пустым.")
    else:
        print(f"Загружено {len(verdicts)} вердиктов.")

    data = aggregate(verdicts)
    output = render_leaderboard(data)
    LEADERBOARD_PATH.write_text(output, encoding="utf-8")
    print(f"Leaderboard записан: {LEADERBOARD_PATH}")
    if data["models"]:
        print(f"Моделей в рейтинге: {len(data['models'])}")
        for m in data["models"]:
            print(f"  {m['model_id']}: {m['avg_score']} ({m['runs']} прогонов)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
