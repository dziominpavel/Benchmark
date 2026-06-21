#!/usr/bin/env python3
"""
register_model.py — регистрация новой LLM-модели в models.yaml.

Использование:
    python tools/register_model.py --id <slug> --name "<полное имя>" \
        --provider <org> --version <строка> [--released <YYYY-MM-DD>] [--notes "<текст>"]

Проверяет уникальность id. Если модель с таким id уже есть — отказывается
(используй --force для перезаписи, но осторожно — история прогонов смешается).

Зависимости: только stdlib.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_PATH = REPO_ROOT / "models.yaml"


def parse_existing(text: str) -> tuple[list[dict], str]:
    """Парсит models.yaml. Возвращает (список моделей, преамбула до 'models:')."""
    # Разделяем на преамбулу (до 'models:') и тело
    # ВАЖНО: [ \t]* вместо \s* чтобы не пересекать newline
    m = re.search(r"^models:[ \t]*(.*)$", text, re.MULTILINE)
    if not m:
        # Нет ключа models — создаём
        return [], text.rstrip() + "\n\nmodels: []\n"

    preamble = text[: m.start()]
    body = text[m.end():]

    models = []
    # Парсим записи вида: - id: ... (многострочные до следующего - или конца)
    entries = re.findall(
        r"^\s*-\s+id:\s*(.+?)(?=^\s*-\s+id:|\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    for entry in entries:
        model = {}
        lines = entry.strip().splitlines()
        # Первая строка — значение id (захвачено regex после "id:\s*")
        if lines:
            first_line = lines[0].strip()
            if ":" not in first_line:
                # Это значение id без префикса "id:"
                model["id"] = first_line
                lines = lines[1:]
            else:
                # Строка содержит "id: value" — парсим как обычную
                pass
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (
                    val.startswith("'") and val.endswith("'")
                ):
                    val = val[1:-1]
                model[key] = val
        if model.get("id"):
            models.append(model)
    return models, preamble


def format_model(m: dict) -> str:
    """Форматирует модель в YAML-блок."""
    lines = [f"  - id: {m['id']}"]
    lines.append(f"    name: \"{m.get('name', '')}\"")
    lines.append(f"    provider: {m.get('provider', '')}")
    lines.append(f"    version: {m.get('version', '')}")
    if m.get("released"):
        lines.append(f"    released: {m['released']}")
    if m.get("notes"):
        lines.append(f"    notes: \"{m['notes']}\"")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Регистрация модели в models.yaml")
    parser.add_argument("--id", required=True, help="Уникальный slug модели")
    parser.add_argument("--name", required=True, help="Полное имя модели")
    parser.add_argument("--provider", default="", help="Провайдер (Anthropic, OpenAI, ...). Опционально при --auto.")
    parser.add_argument("--version", default="", help="Версия/релиз. Опционально при --auto.")
    parser.add_argument("--released", default="", help="Дата выхода YYYY-MM-DD")
    parser.add_argument("--notes", default="", help="Заметки")
    parser.add_argument("--force", action="store_true", help="Перезаписать если id существует")
    parser.add_argument("--auto", action="store_true", help="Авто-регистрация моделью самой себя. provider/version опциональны. Если модель уже есть — exit 0 (не ошибка).")
    args = parser.parse_args()

    if not MODELS_PATH.exists():
        print(f"Файл {MODELS_PATH} не найден.", file=sys.stderr)
        return 1

    # При --auto provider/version опциональны; при обычном режиме — обязательны
    if not args.auto:
        if not args.provider:
            print("--provider обязателен без --auto.", file=sys.stderr)
            return 1
        if not args.version:
            print("--version обязателен без --auto.", file=sys.stderr)
            return 1

    text = MODELS_PATH.read_text(encoding="utf-8")
    models, preamble = parse_existing(text)

    # Проверка уникальности
    existing_ids = [m["id"] for m in models]
    if args.id in existing_ids:
        if args.auto:
            # При --auto существующая модель — не ошибка, просто выходим
            print(f"Модель '{args.id}' уже зарегистрирована.")
            return 0
        if not args.force:
            print(
                f"Модель с id '{args.id}' уже существует. Используй --force для перезаписи.",
                file=sys.stderr,
            )
            return 1
        # Удаляем старую запись
        models = [m for m in models if m["id"] != args.id]
        print(f"Перезаписываю существующую запись '{args.id}'.")

    new_model = {
        "id": args.id,
        "name": args.name,
        "provider": args.provider,
        "version": args.version,
        "released": args.released,
        "notes": args.notes,
    }
    models.append(new_model)

    # Сортируем по id для стабильности
    models.sort(key=lambda m: m["id"])

    # Генерируем новый файл
    out = preamble.rstrip() + "\n\nmodels:\n"
    for m in models:
        out += format_model(m) + "\n"

    MODELS_PATH.write_text(out, encoding="utf-8")
    print(f"Модель '{args.id}' добавлена в {MODELS_PATH}.")
    print(f"Всего моделей: {len(models)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
