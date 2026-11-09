#!/usr/bin/env python3
"""
lookups.py — справочники харнессов, разработчиков и провайдеров
(data/lookups.yaml).

Файл хранит допустимые значения полей harness/developer/provider реестра
тремя списками простых строк: harnesses:, developers: и providers:.
Порядок значений в файле задаёт порядок их вывода в консоли; новые значения
добавляются в конец.

Парсер/сериализатор — stdlib, по образцу parse_existing/format_model
из register_model.py: шапка-комментарий сохраняется при перезаписи,
отсутствующий или пустой файл читается как пустые списки, без исключений.

Для обратной совместимости старые ключи agents:/providers: читаются как
harnesses:/developers:, если новых ключей нет.

API:
    LOOKUPS_PATH            — путь к data/lookups.yaml
    load_lookups()          — {"harnesses": [...], "developers": [...], "providers": [...]}
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
_KEY_BY_KIND = {
    "harness": "harnesses",
    "developer": "developers",
    "provider": "providers",
}
_KEYS = ("harnesses", "developers", "providers")

DEFAULT_HEADER = """\
# Справочники харнессов, разработчиков и провайдеров для бенчмарка
#
# Допустимые значения полей harness, developer и provider реестра data/models.yaml:
#   harnesses  — харнесс (Codex, Cursor, Devin, OpenCode): в чём гоняли модель;
#   developers — разработчик модели (Alibaba, Anthropic, ...): кто обучил;
#   providers  — провайдер доступа (OpenCode Go, OpenRouter, Vercel AI Gateway,
#                Kilo Code, встроенный доступ харнесса): через что шёл запрос.
# Порядок значений в файле задаёт порядок их вывода в консоли; новые
# значения добавляются в конец. Управление (добавить/переименовать/
# удалить) — секция «Справочники» страницы /settings, авто-добавление
# при регистрации модели — tools/register_model.py.
"""


def _empty_lists() -> dict[str, list[str]]:
    return {key: [] for key in _KEYS}


def parse_lookups(text: str) -> tuple[dict[str, list[str]], str]:
    """Парсит текст lookups.yaml.

    Возвращает ({"harnesses": [...], "developers": [...], "providers": [...]},
    шапка). Отсутствующий ключ даёт пустой список; дубликаты убираются
    (остаётся первое вхождение). Исключений не бросает.
    """
    lists = _empty_lists()
    first_key_pos: int | None = None

    # Старые имена ключей: agents → harnesses, providers → developers.
    # Если новый ключ присутствует, старый игнорируется.
    key_sources = {
        "harnesses": ("harnesses", "agents"),
        "developers": ("developers",),
        "providers": ("providers",),
    }
    # Старый providers: одновременно служил и разработчикам, и провайдерам.
    # При отсутствии developers: подхватываем providers: как разработчиков,
    # но только если нового providers-смысла ещё нет в файле.
    has_new_providers = re.search(r"^providers:[ \t]*(.*?)[ \t]*$", text, re.MULTILINE)
    legacy_providers_as_developers = (
        "developers:" not in text and has_new_providers is not None
    )

    for target, sources in key_sources.items():
        for key in sources:
            m = re.search(rf"^{key}:[ \t]*(.*?)[ \t]*$", text, re.MULTILINE)
            if not m or m.group(1) not in ("", "[]"):
                continue
            if first_key_pos is None or m.start() < first_key_pos:
                first_key_pos = m.start()

            parsed: list[str] = []
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
                if value and not value.startswith("#") and value not in parsed:
                    parsed.append(value)
            if parsed:
                lists[target] = parsed
                break

    # Совсем старый файл: только agents: и providers:, без новых ключей.
    # Если developers пуст, а providers заполнен, считаем его разработчиками.
    if not lists["developers"] and legacy_providers_as_developers:
        lists["developers"] = list(lists["providers"])
        lists["providers"] = []

    header = text[:first_key_pos] if first_key_pos is not None else text
    return lists, header


def _read() -> tuple[dict[str, list[str]], str]:
    """Читает файл: (значения, шапка). Отсутствие/ошибка чтения — пустые значения."""
    if not LOOKUPS_PATH.exists():
        return _empty_lists(), ""
    try:
        text = LOOKUPS_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return _empty_lists(), ""
    if not text.strip():
        return _empty_lists(), ""
    return parse_lookups(text)


def load_lookups() -> dict[str, list[str]]:
    """Текущие списки справочников; отсутствующий/пустой файл → пустые списки."""
    return _read()[0]


def save_lookups(data: dict[str, list[str]]) -> None:
    """Перезаписывает lookups.yaml, сохраняя шапку-комментарий."""
    _, header = _read()
    if not header.strip():
        header = DEFAULT_HEADER
    out = header.rstrip() + "\n\n"
    for key in _KEYS:
        out += f"{key}:\n"
        for value in data.get(key, []):
            out += f"  - {value}\n"
        out += "\n"
    LOOKUPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOOKUPS_PATH.write_text(out.rstrip() + "\n", encoding="utf-8")


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
