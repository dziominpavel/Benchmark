#!/usr/bin/env python3
"""
lookups.py — справочники агентов и компаний (data/lookups.yaml).

Файл хранит допустимые значения полей agent/provider реестра двумя
списками простых строк: agents: и providers:. Порядок значений в файле
задаёт порядок их вывода в консоли; новые значения добавляются в конец.

Парсер/сериализатор — stdlib, по образцу parse_existing/format_model
из register_model.py: шапка-комментарий сохраняется при перезаписи,
отсутствующий или пустой файл читается как пустые списки, без исключений.

API:
    LOOKUPS_PATH            — путь к data/lookups.yaml
    load_lookups()          — {"agents": [...], "providers": [...]}
    save_lookups(data)      — запись с сохранением шапки
    parse_lookups(text)     — текст → (списки, шапка)
    find_value(kind, value) — поиск без учёта регистра (написание файла)
    add_value(kind, value)  — добавить в конец; False при пустом/дубликате
    has_value(kind, value)  — точная проверка наличия

Зависимости: только stdlib.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

LOOKUPS_PATH = Path(__file__).resolve().parent.parent / "data" / "lookups.yaml"

# kind → ключ списка в файле
_KEY_BY_KIND = {"agent": "agents", "provider": "providers"}

DEFAULT_HEADER = """\
# Справочники агентов и компаний для бенчмарка
#
# Допустимые значения полей agent и provider реестра data/models.yaml.
# Порядок значений в файле задаёт порядок их вывода в консоли; новые
# значения добавляются в конец. Управление (добавить/переименовать/
# удалить) — секция «Справочники» страницы /settings, авто-добавление
# при регистрации модели — tools/register_model.py.
"""


def parse_lookups(text: str) -> tuple[dict[str, list[str]], str]:
    """Парсит текст lookups.yaml.

    Возвращает ({agents: [...], providers: [...]}, шапка). Отсутствующий
    ключ даёт пустой список; дубликаты убираются (остаётся первое
    вхождение). Исключений не бросает.
    """
    lists: dict[str, list[str]] = {"agents": [], "providers": []}
    first_key_pos: int | None = None

    for key in ("agents", "providers"):
        # Ключ с пустым телом или inline-пустым списком: agents: / agents: []
        m = re.search(rf"^{key}:[ \t]*(.*?)[ \t]*$", text, re.MULTILINE)
        if not m or m.group(1) not in ("", "[]"):
            continue
        if first_key_pos is None or m.start() < first_key_pos:
            first_key_pos = m.start()

        for line in text[m.end():].splitlines():
            if not line.strip():
                continue
            vm = re.match(r"^\s+-\s*(.*)$", line)
            if not vm:
                # Следующий ключ или текст — список закончился
                break
            value = vm.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].strip()
            if value and not value.startswith("#") and value not in lists[key]:
                lists[key].append(value)

    header = text[:first_key_pos] if first_key_pos is not None else text
    return lists, header


def _read() -> tuple[dict[str, list[str]], str]:
    """Читает файл: (значения, шапка). Отсутствие/ошибка чтения — пустые значения."""
    if not LOOKUPS_PATH.exists():
        return {"agents": [], "providers": []}, ""
    try:
        text = LOOKUPS_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"agents": [], "providers": []}, ""
    if not text.strip():
        return {"agents": [], "providers": []}, ""
    return parse_lookups(text)


def load_lookups() -> dict[str, list[str]]:
    """Текущие списки справочников; отсутствующий/пустой файл → пустые списки."""
    return _read()[0]


def save_lookups(data: dict[str, list[str]]) -> None:
    """Перезаписывает lookups.yaml, сохраняя шапку-комментарий."""
    _, header = _read()
    if not header.strip():
        header = DEFAULT_HEADER
    out = header.rstrip() + "\n\nagents:\n"
    for value in data.get("agents", []):
        out += f"  - {value}\n"
    out += "\nproviders:\n"
    for value in data.get("providers", []):
        out += f"  - {value}\n"
    LOOKUPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOOKUPS_PATH.write_text(out, encoding="utf-8")


def find_value(kind: str, value: str) -> str | None:
    """Ищет значение в списке без учёта регистра; возвращает написание файла."""
    needle = (value or "").strip().lower()
    if not needle:
        return None
    for existing in load_lookups()[_KEY_BY_KIND[kind]]:
        if existing.lower() == needle:
            return existing
    return None


def has_value(kind: str, value: str) -> bool:
    """Есть ли значение в справочнике (точное совпадение)."""
    return (value or "").strip() in load_lookups()[_KEY_BY_KIND[kind]]


def add_value(kind: str, value: str) -> bool:
    """Добавляет значение в конец списка справочника.

    Пустое значение или дубликат (в том числе в другом регистре) —
    False, файл не меняется. Значение добавлено — True.
    """
    value = (value or "").strip()
    if not value:
        return False
    key = _KEY_BY_KIND[kind]
    data = load_lookups()
    if any(v.lower() == value.lower() for v in data[key]):
        return False
    data[key].append(value)
    save_lookups(data)
    return True
