#!/usr/bin/env python3
"""
assign_judges.py — распределение судей по прогонам + анонимизация.

Новая архитектура (без волн):
    runs/<task-id>/<model-id>/run.md
    verdicts/<task-id>/<participant-anon-id>/<judge-id>.md
    judges.yaml (в корне) — глобальный pool судей
    anonymization.yaml (в корне) — глобальная карта анонимизации

Команды:
    --init
        Создаёт anonymization.yaml в корне из всех моделей в models.yaml.
        Назначает "Участник A", "Участник B", ... по порядку.

    --distribute
        Распределяет судей по всем прогонам (3 судьи на прогон).
        Проверяет конфликт интересов (судья ≠ участник).
        Создаёт анонимизированные копии прогонов для судей в .anon-copies/.

    --add-runs --participant <model-id>
        Инкрементальное назначение: назначает 3 судей для прогонов
        НОВОГО участника. Не перераспределяет существующие вердикты.
        Добавляет model-id в anonymization.yaml если его там нет.

Зависимости: только stdlib.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
VERDICTS_DIR = REPO_ROOT / "verdicts"
MODELS_FILE = REPO_ROOT / "models.yaml"
JUDGES_FILE = REPO_ROOT / "judges.yaml"
ANON_FILE = REPO_ROOT / "anonymization.yaml"


def parse_yaml_simple(path: Path) -> dict:
    """Простой YAML-парсер для плоских ключей и списков."""
    text = path.read_text(encoding="utf-8")
    result: dict = {}
    current_key = None
    for line in text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if line.lstrip().startswith("- ") and current_key:
            item = line.lstrip()[2:].strip()
            if not isinstance(result.get(current_key), list):
                result[current_key] = []
            result[current_key].append(item)
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            if val:
                result[key] = val
            else:
                result[key] = []
                current_key = key
    return result


def load_models() -> list[str]:
    """Загружает список model_id из models.yaml."""
    if not MODELS_FILE.exists():
        return []
    text = MODELS_FILE.read_text(encoding="utf-8")
    # Парсим - id: <slug>
    return re.findall(r"^\s*-\s+id:\s*(\S+)", text, re.MULTILINE)


def load_judges() -> list[str]:
    """Загружает список судей из judges.yaml (в корне)."""
    if not JUDGES_FILE.exists():
        return []
    data = parse_yaml_simple(JUDGES_FILE)
    return data.get("judges", [])


def load_anonymization() -> dict[str, str]:
    """Загружает карту {model_id: anon_id} из anonymization.yaml (в корне)."""
    if not ANON_FILE.exists():
        return {}
    mapping = {}
    text = ANON_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("mapping:") or line.startswith("- ") or not line or line.startswith("#"):
            continue
        m = re.match(r'^(\S+):\s*"(.+)"', line)
        if m:
            mapping[m.group(1)] = m.group(2)
    return mapping


def save_anonymization(mapping: dict[str, str]) -> None:
    """Записывает anonymization.yaml в корне."""
    lines = [
        "# Глобальная карта анонимизации",
        "# Создано assign_judges.py --init / --add-runs",
        "# ДОСТУПНО ТОЛЬКО aggregate.py. MUST NOT передаваться судьям.",
        "",
        "mapping:",
    ]
    for model_id, anon in mapping.items():
        lines.append(f'  {model_id}: "{anon}"')
    ANON_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def init_anonymization() -> int:
    """Создаёт anonymization.yaml из всех моделей в models.yaml."""
    models = load_models()
    if not models:
        print("В models.yaml нет моделей. Зарегистрируй через register_model.py.", file=sys.stderr)
        return 1

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    mapping = {}
    for i, model_id in enumerate(models):
        letter = letters[i] if i < len(letters) else str(i + 1)
        mapping[model_id] = f"Участник {letter}"

    save_anonymization(mapping)
    print(f"Карта анонимизации создана: {ANON_FILE}")
    for model_id, anon in mapping.items():
        print(f"  {model_id} -> {anon}")
    return 0


def add_to_anonymization(model_id: str) -> str | None:
    """Добавляет model_id в anonymization.yaml если его там нет.
    Возвращает anon_id или None если model_id не найден в models.yaml."""
    mapping = load_anonymization()
    if model_id in mapping:
        return mapping[model_id]

    models = load_models()
    if model_id not in models:
        print(f"Модель '{model_id}' не найдена в models.yaml.", file=sys.stderr)
        return None

    # Находим следующую свободную букву
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    used_letters = {anon.split()[-1] for anon in mapping.values()}
    for letter in letters:
        if letter not in used_letters:
            anon = f"Участник {letter}"
            mapping[model_id] = anon
            save_anonymization(mapping)
            print(f"Добавлен в anonymization.yaml: {model_id} -> {anon}")
            return anon
    print("Достигнут предел анонимизации (26 участников).", file=sys.stderr)
    return None


def anonymize_text(text: str, model_id: str, anon_id: str) -> str:
    """Заменяет model_id на anon_id в тексте прогона."""
    text = text.replace(f"model_id: {model_id}", f"model_id: {anon_id}")
    text = text.replace(model_id, anon_id)
    reflections = [
        r"(?i)как\s+\w*[Cc]laude\b",
        r"(?i)как\s+\w*GPT\b",
        r"(?i)как\s+\w*GLM\b",
        r"(?i)я\s+как\s+\w*[Cc]laude\b",
        r"(?i)я\s+как\s+\w*GPT\b",
    ]
    for pattern in reflections:
        text = re.sub(pattern, "как [модель]", text)
    return text


def collect_runs(participant_filter: str | None = None) -> list[dict]:
    """Собирает все прогоны из runs/<task-id>/<model-id>/run.md.

    Если participant_filter задан — только прогоны этого участника.
    """
    runs = []
    if not RUNS_DIR.exists():
        return runs
    for task_dir in sorted(RUNS_DIR.iterdir()):
        if not task_dir.is_dir() or task_dir.name.startswith(".") or task_dir.name.startswith("_"):
            continue
        for model_dir in sorted(task_dir.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith(".") or model_dir.name.startswith("_"):
                continue
            model_id = model_dir.name
            if participant_filter and model_id != participant_filter:
                continue
            run_file = model_dir / "run.md"
            if not run_file.exists():
                continue
            diff_file = model_dir / "diff.patch"
            runs.append({
                "task_id": task_dir.name,
                "model_id": model_id,
                "run_path": run_file,
                "diff_path": diff_file if diff_file.exists() else None,
            })
    return runs


def distribute_judges(participant_filter: str | None = None) -> int:
    """Распределяет судей по прогонам и создаёт анонимизированные копии.

    Если participant_filter задан — только для прогонов этого участника (инкремент).
    """
    judges = load_judges()
    if not judges:
        print(f"В {JUDGES_FILE} нет судей. Заполни judges.yaml.", file=sys.stderr)
        return 1

    anon_map = load_anonymization()
    if not anon_map:
        print(f"Файл {ANON_FILE} пуст. Запусти --init сначала.", file=sys.stderr)
        return 1

    runs = collect_runs(participant_filter)
    if not runs:
        scope = f"участника {participant_filter}" if participant_filter else "всех участников"
        print(f"Прогонов для {scope} не найдено.", file=sys.stderr)
        return 1

    # Назначаем судей
    assignments = []
    for run in runs:
        model_id = run["model_id"]
        anon_id = anon_map.get(model_id, model_id)
        available = [j for j in judges if j != model_id]
        assigned = available[:3]
        if len(assigned) < 2:
            print(
                f"  ! Недостаточно судей для {model_id}/{run['task_id']}: "
                f"доступно {len(assigned)}, нужно минимум 2",
                file=sys.stderr,
            )
        assignments.append({
            "model_id": model_id,
            "anon_id": anon_id,
            "task_id": run["task_id"],
            "judges": assigned,
            "run_path": run["run_path"],
            "diff_path": run["diff_path"],
        })

    # Создаём анонимизированные копии
    anon_dir = REPO_ROOT / ".anon-copies"
    if not participant_filter:
        # Полное распределение — очищаем старые копии
        if anon_dir.exists():
            shutil.rmtree(anon_dir)
    anon_dir.mkdir(parents=True, exist_ok=True)

    for a in assignments:
        task_anon_dir = anon_dir / a["task_id"] / a["anon_id"]
        task_anon_dir.mkdir(parents=True, exist_ok=True)

        # Анонимизированный run.md
        run_text = a["run_path"].read_text(encoding="utf-8")
        anon_text = anonymize_text(run_text, a["model_id"], a["anon_id"])
        (task_anon_dir / "run.md").write_text(anon_text, encoding="utf-8")

        # diff.patch копируем как есть (в нём нет model_id)
        if a["diff_path"]:
            shutil.copy2(str(a["diff_path"]), str(task_anon_dir / "diff.patch"))

        # Создаём папку для вердиктов
        verdict_dir = VERDICTS_DIR / a["task_id"] / a["anon_id"]
        verdict_dir.mkdir(parents=True, exist_ok=True)

    # Записываем карту назначений
    assignments_file = REPO_ROOT / "judge-assignments.yaml"
    lines = [
        "# Карта назначений судей по прогонам",
        "# Создано assign_judges.py --distribute / --add-runs",
        "",
        "assignments:",
    ]
    for a in assignments:
        judges_str = ", ".join(a["judges"])
        lines.append(f'  - task: {a["task_id"]}')
        lines.append(f'    participant: "{a["anon_id"]}"')
        lines.append(f'    model_id: {a["model_id"]}  # скрыто от судей')
        lines.append(f'    judges: [{judges_str}]')
    assignments_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    scope = f"участника {participant_filter}" if participant_filter else "всех участников"
    print(f"Распределение судей для {scope}: {len(assignments)} прогонов.")
    for a in assignments:
        print(f"  {a['task_id']} / {a['anon_id']}: {', '.join(a['judges'])}")
    print(f"Анонимизированные копии: {anon_dir}")
    print(f"Карта назначений: {assignments_file}")
    return 0


def add_judge(model_id: str) -> int:
    """Добавляет model-id в judges.yaml (pool судей).

    Если модель уже в pool — завершает успешно (exit 0).
    Если модель не в models.yaml — предупреждает, но добавляет.
    """
    if not JUDGES_FILE.exists():
        print(f"Файл {JUDGES_FILE} не найден.", file=sys.stderr)
        return 1

    text = JUDGES_FILE.read_text(encoding="utf-8")
    # Парсим список судей
    judges = re.findall(r"^\s*-\s+(\S+)", text, re.MULTILINE)
    # Фильтруем пустые/комментарии
    judges = [j for j in judges if j and not j.startswith("#")]

    if model_id in judges:
        print(f"Судья '{model_id}' уже в pool.")
        return 0

    # Предупреждение если модель не в models.yaml
    models = load_models()
    if model_id not in models:
        print(f"Внимание: модель '{model_id}' не найдена в models.yaml. Добавляю в pool судей.")

    # Добавляем в список
    judges.append(model_id)
    judges.sort()

    # Перегенерируем файл
    lines = [
        "# Глобальный pool судей",
        "#",
        "# Список model_id (из models.yaml), которые выступают в роли судей.",
        "# assign_judges.py назначает 3 судей из этого pool для каждого прогона.",
        "# Судья не может оценивать свой собственный прогон (конфликт интересов).",
        "#",
        "# Модели добавляются автоматически через assign_judges.py --add-judge <model-id>",
        "# или вручную.",
        "",
        "judges:",
    ]
    for j in judges:
        lines.append(f"  - {j}")
    JUDGES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Судья '{model_id}' добавлен в {JUDGES_FILE}.")
    print(f"Всего судей: {len(judges)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Распределение судей + анонимизация")
    parser.add_argument("--init", action="store_true", help="Создать anonymization.yaml из models.yaml")
    parser.add_argument("--distribute", action="store_true", help="Распределить судей по всем прогонам")
    parser.add_argument("--add-runs", action="store_true", help="Инкрементальное назначение для нового участника")
    parser.add_argument("--participant", default="", help="model-id нового участника (для --add-runs)")
    parser.add_argument("--add-judge", default="", help="model-id для добавления в judges.yaml (саморегистрация судьи)")
    args = parser.parse_args()

    if args.init:
        return init_anonymization()
    elif args.distribute:
        return distribute_judges()
    elif args.add_runs:
        if not args.participant:
            print("--add-runs требует --participant <model-id>", file=sys.stderr)
            return 1
        # Добавляем в anonymization если нужно
        add_to_anonymization(args.participant)
        return distribute_judges(participant_filter=args.participant)
    elif args.add_judge:
        return add_judge(args.add_judge)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
