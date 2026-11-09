#!/usr/bin/env python3
"""
migrate_registry_v3.py — одноразовая миграция реестра к трём параметрам.

Было:  agent (харнесс) + provider (компания-разработчик).
Стало: developer (компания-разработчик) + provider (провайдер доступа)
       + harness (харнесс).

Миграция также убирает названия харнессов из поля name и пересобирает
data/lookups.yaml и data/index.json. ID моделей не меняются: на них
ссылаются журнал вердиктов и флаги ответов.

Запуск:
    python tools/migrate_registry_v3.py            # показать, что изменится
    python tools/migrate_registry_v3.py --write    # записать изменения
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import MODELS_PATH, generate_index, load_models_yaml, save_index  # noqa: E402
from lookups import LOOKUPS_PATH  # noqa: E402
from register_model import format_model  # noqa: E402

# id -> (name, developer, provider, harness)
MODEL_MAP: dict[str, tuple[str, str, str, str]] = {
    # Codex
    "codex-gpt-5-6-terra-09-2026": (
        "GPT-5.6-Terra High 09-2026", "OpenAI", "OpenAI", "Codex",
    ),
    # Cursor
    "cursor-composer-2-5": ("Composer 2.5", "SpaceXAI", "Cursor", "Cursor"),
    "cursor-fable-5-1-1m-max": (
        "Claude Fable 5.1 1M Max", "Anthropic", "Cursor", "Cursor",
    ),
    "cursor-gemini-3-8-flash-high": (
        "Gemini 3.8 Flash High", "Google", "Cursor", "Cursor",
    ),
    "cursor-grok-4-6": ("Grok 4.6 Extra High", "SpaceXAI", "Cursor", "Cursor"),
    "cursor-grok-4-6-low": ("Grok 4.6 Low", "SpaceXAI", "Cursor", "Cursor"),
    "cursor-kimi-k3-max": ("Kimi K3 Max", "Moonshot AI", "Cursor", "Cursor"),
    "cursor-sonnet-5-5-1m-max": (
        "Claude Sonnet 5.5 1M Max", "Anthropic", "Cursor", "Cursor",
    ),
    # Devin
    "devin-deepseek-v4-1-flash-max": (
        "DeepSeek V4.1 Flash Max", "DeepSeek", "Cognition", "Devin",
    ),
    "devin-deepseek-v4-pro-max": (
        "DeepSeek V4 Pro Max", "DeepSeek", "Cognition", "Devin",
    ),
    "devin-glm-5-2-high": ("GLM-5.2 High", "Z.ai", "Cognition", "Devin"),
    "devin-glm-5-3-flash-max": (
        "GLM-5.3 Flash Max", "Z.ai", "Cognition", "Devin",
    ),
    "devin-gpt-5-6-sol-max": (
        "GPT-5.6 Sol Max", "OpenAI", "Cognition", "Devin",
    ),
    "devin-gpt-6-astra-max": (
        "GPT-6 Astra Max", "OpenAI", "Cognition", "Devin",
    ),
    "devin-gpt-6-astra-max-2": (
        "GPT-6 Astra Low", "OpenAI", "Cognition", "Devin",
    ),
    "devin-kimi-k3-max": (
        "Kimi K3 Max", "Moonshot AI", "Cognition", "Devin",
    ),
    "devin-swe-1-7-max": ("SWE-1.7 Max", "Cognition", "Cognition", "Devin"),
    "devin-swe-2-max": ("SWE-2 Max", "Cognition", "Cognition", "Devin"),
    # OpenCode — OpenCode Go
    "opencode-beam-free-max": (
        "Beam Free Max", "Reflection AI", "OpenCode Go", "OpenCode",
    ),
    "opencode-big-pickle": ("Big Pickle", "Unknown", "OpenCode Go", "OpenCode"),
    "opencode-claude-haiku-5-5-max": (
        "Claude Haiku 5.5 Max", "Anthropic", "OpenCode Go", "OpenCode",
    ),
    "opencode-deepseek-v4-1-flash-1017-max": (
        "DeepSeek V4.1 Flash 1017 Max", "DeepSeek", "OpenCode Go", "OpenCode",
    ),
    "opencode-deepseek-v4-1-flash-free-max": (
        "DeepSeek V4.1 Flash Free Max", "DeepSeek", "OpenCode Go", "OpenCode",
    ),
    "opencode-flint-free": (
        "Flint Free", "Recursive", "OpenCode Go", "OpenCode",
    ),
    "opencode-free-model-router-20261024": (
        "Free Model Router 20261024", "Anomaly", "OpenCode Go", "OpenCode",
    ),
    "opencode-gemini-4-argon-high": (
        "Gemini 4 Argon High", "Google", "OpenCode Go", "OpenCode",
    ),
    "opencode-glm-5-3-flash-free": (
        "GLM-5.3 Flash Free", "Z.ai", "OpenCode Go", "OpenCode",
    ),
    "opencode-grok-4-7-xhigh": (
        "Grok 4.7 Xhigh", "SpaceXAI", "OpenCode Go", "OpenCode",
    ),
    "opencode-hy4-preview-high": (
        "Hy4 Preview High", "Tencent", "OpenCode Go", "OpenCode",
    ),
    "opencode-iceman-contributor-free": (
        "Iceman Contributor Free", "Microsoft", "OpenCode Go", "OpenCode",
    ),
    "opencode-kimi-k3-1-pro-max": (
        "Kimi K3.1 Pro Max", "Moonshot AI", "OpenCode Go", "OpenCode",
    ),
    "opencode-mimo-v2-5-free": (
        "MiMo V2.5 Free", "Xiaomi", "OpenCode Go", "OpenCode",
    ),
    "opencode-mimo-v2-6-flash-free": (
        "MiMo V2.6 Flash Free", "Xiaomi", "OpenCode Go", "OpenCode",
    ),
    "opencode-minimax-m3-1-flash-free-max": (
        "MiniMax M3.1 Flash Free Max", "MiniMax", "OpenCode Go", "OpenCode",
    ),
    "opencode-muse-spark-1-3-free-xhigh": (
        "Muse Spark 1.3 Free Xhigh", "Meta", "OpenCode Go", "OpenCode",
    ),
    "opencode-nemotron-3-5-super-vl-free-xhigh": (
        "Nemotron 3.5 Super VL Free Xhigh", "NVIDIA", "OpenCode Go", "OpenCode",
    ),
    "opencode-qwen3-8-max-xhigh": (
        "Qwen3.8 Max Xhigh", "Alibaba", "OpenCode Go", "OpenCode",
    ),
    "opencode-step-5-preview-free-high": (
        "Step 5 Preview Free High", "StepFun", "OpenCode Go", "OpenCode",
    ),
    # OpenCode — OpenRouter
    "nemotron-3-ultra-free-high": (
        "Nemotron 3 Ultra Free High", "NVIDIA", "OpenRouter", "OpenCode",
    ),
    "opencode-fledge-alpha-free": (
        "Fledge Alpha Free Max", "Unknown", "OpenRouter", "OpenCode",
    ),
    "opencode-inkling-free-max": (
        "Inkling Free Max", "Thinking Machines Lab", "OpenRouter", "OpenCode",
    ),
    "opencode-inkling-small-free-max": (
        "Inkling Small Free Max", "Thinking Machines Lab", "OpenRouter", "OpenCode",
    ),
    "opencode-laguna-s-2-1-free": (
        "Laguna S 2.1 Free", "Reflection AI", "OpenRouter", "OpenCode",
    ),
    "opencode-laguna-xs-2-1-free": (
        "Laguna XS 2.1 Free", "Reflection AI", "OpenRouter", "OpenCode",
    ),
    "opencode-ling-3-0-flash-fin-free": (
        "Ling 3.0 Flash Fin Free", "Ant Group", "OpenRouter", "OpenCode",
    ),
    "opencode-ling-3-1-flash-free": (
        "Ling 3.1 Flash Free", "Ant Group", "OpenRouter", "OpenCode",
    ),
    "opencode-longcat-2-5-preview-free": (
        "LongCat 2.5 Preview Free", "Meituan", "OpenRouter", "OpenCode",
    ),
    "opencode-north-mini-code-free-thinking": (
        "North Mini Code Free Thinking", "Cohere", "OpenRouter", "OpenCode",
    ),
    "opencode-space-bunny-free-max": (
        "Space Bunny Free Max", "MiniMax", "OpenRouter", "OpenCode",
    ),
    # OpenCode — Vercel AI Gateway
    "opencode-qwen3-8-max-0912-xhigh": (
        "Qwen3.8 Max 0912 Xhigh", "Alibaba", "Vercel AI Gateway", "OpenCode",
    ),
}

MODELS_HEADER = """\
# Реестр LLM-моделей для бенчмарка
#
# Формат записи:
#   - id: <slug>            # стабильный идентификатор; на него ссылаются journal и флаги
#     name: <имя>           # человекочитаемое имя модели без харнесса и компании
#     developer: <компания> # разработчик модели из справочника data/lookups.yaml (developers)
#     provider: <провайдер> # провайдер доступа из справочника data/lookups.yaml (providers)
#     harness: <харнесс>    # харнесс из справочника data/lookups.yaml (harnesses)
#     version: <строка>     # версия/релиз модели
#     released: <YYYY-MM-DD># дата выхода модели (если известна)
#     added: <YYYY-MM-DD>   # дата регистрации в реестре (ставится автоматически)
#     status: active        # active | archived (archived = заморожена, не участвует в новых парах)
#     notes: <строка>       # необязательные заметки
#
# Три классификационных параметра:
#   developer — кто обучил модель (Alibaba, Anthropic, OpenAI, ...);
#   provider  — через что шёл доступ (OpenCode Go, OpenRouter, Vercel AI Gateway,
#               Kilo Code, встроенный доступ харнесса: Cursor, Cognition, OpenAI);
#   harness   — в чём гоняли (Codex, Cursor, Devin, OpenCode).
#
# Допустимые значения — в справочнике data/lookups.yaml. Значения вне
# справочника не теряются: консоль помечает их «вне справочника» и позволяет
# внести одной кнопкой; --harness/--developer/--provider при регистрации
# автоматически пополняют справочник.
#
# Добавляй модели через tools/register_model.py:
#   python tools/register_model.py --id <slug> --name "<name>" --version <ver> \
#       [--harness <harness>] [--developer <компания>] [--provider <провайдер>] \
#       [--released <YYYY-MM-DD>] [--added <YYYY-MM-DD>]
# Или через саморегистрацию (--auto, --version не обязателен):
#   python tools/register_model.py --auto --id <slug> --name "<name>" \
#       [--harness <harness>] [--developer <компания>] [--provider <провайдер>]
#
# Архивация через tools/archive_model.py:
#   python tools/archive_model.py <slug>           # заархивировать
#   python tools/archive_model.py --restore <slug> # разархивировать
# Правила архивации (жёсткий блок в tools/archive_model.py):
#   - минимум 10 вердиктов (пока меньше — ELO в провизорной зоне K=40);
#   - только нижние 3 активных по ELO. Разархивация не ограничена.
#
# id должен быть уникальным и стабильным — на него ссылаются файлы в answers/ и matchups/.
# Если у модели выходит новая версия (например, claude-sonnet-4.5 → 4.6),
# создавай новый id, не перезаписывай старый — иначе история ответов смешается.
# Старую версию можно заархивировать (status: archived) — ELO сохранится, новые пары не предлагаются.
"""

LOOKUPS_HEADER = """\
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

HARNESSES = ["Codex", "Cursor", "Devin", "OpenCode"]
DEVELOPERS = [
    "Alibaba", "Anomaly", "Ant Group", "Anthropic", "Cognition", "Cohere",
    "DeepSeek", "Google", "Meituan", "Meta", "Microsoft", "MiniMax",
    "Moonshot AI", "NVIDIA", "OpenAI", "Recursive", "Reflection AI",
    "SpaceXAI", "StepFun", "Tencent", "Thinking Machines Lab", "Unknown",
    "Xiaomi", "Z.ai",
]
PROVIDERS = [
    "Cognition", "Cursor", "Kilo Code", "OpenAI", "OpenCode Go", "OpenRouter",
    "Unknown", "Vercel AI Gateway",
]


def build_models_text(models: list[dict]) -> str:
    out = MODELS_HEADER.rstrip() + "\n\nmodels:\n"
    for model in models:
        out += format_model(model) + "\n"
    return out


def build_lookups_text() -> str:
    out = LOOKUPS_HEADER.rstrip() + "\n\n"
    for key, values in (
        ("harnesses", HARNESSES),
        ("developers", DEVELOPERS),
        ("providers", PROVIDERS),
    ):
        out += f"{key}:\n"
        for value in values:
            out += f"  - {value}\n"
        out += "\n"
    return out.rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Миграция реестра к developer/provider/harness")
    parser.add_argument("--write", action="store_true", help="записать изменения")
    args = parser.parse_args()

    models = load_models_yaml()
    ids = {m["id"] for m in models}
    missing = sorted(ids - MODEL_MAP.keys())
    extra = sorted(MODEL_MAP.keys() - ids)
    if missing or extra:
        if missing:
            print("Нет в MODEL_MAP: " + ", ".join(missing), file=sys.stderr)
        if extra:
            print("Лишние в MODEL_MAP: " + ", ".join(extra), file=sys.stderr)
        return 1

    for model in models:
        name, developer, provider, harness = MODEL_MAP[model["id"]]
        model["name"] = name
        model["developer"] = developer
        model["provider"] = provider
        model["harness"] = harness
        model.pop("agent", None)

    models.sort(key=lambda m: m["id"])

    print(f"Моделей: {len(models)}")
    for model in models:
        print(
            f"  {model['id']}: {model['developer']} / {model['provider']} / "
            f"{model['harness']} -> {model['name']}"
        )

    if not args.write:
        print("\nDry-run. Для записи добавьте --write.")
        return 0

    MODELS_PATH.write_text(build_models_text(models), encoding="utf-8")
    LOOKUPS_PATH.write_text(build_lookups_text(), encoding="utf-8")
    save_index(generate_index())
    print(f"\nЗаписано: {MODELS_PATH}")
    print(f"Записано: {LOOKUPS_PATH}")
    print("index.json пересобран.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
