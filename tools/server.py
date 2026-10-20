#!/usr/bin/env python3
"""
server.py — локальный веб-сервер для бенчмарка LLM-моделей.

Предоставляет:
  - Leaderboard (таблица ELO-рейтинга)
  - Форму записи вердикта (попарное сравнение: A vs B → победитель, таск)
  - Страницу настроек /settings (модели, таски, ответы, справочники агентов и компаний)
  - Отдельную страницу добавления модели (название, агент и компания из справочника)
  - Историю изменений рейтинга

Запуск:
    python tools/server.py
    → http://localhost:5000

Зависимости: Flask, PyYAML (опц., для models.yaml).
"""

from __future__ import annotations

import csv
import heapq
import io
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Добавляем tools/ в path для импорта elo.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_cache

from elo import (
    generate_index, save_index, load_models_yaml, load_matchups,
    is_index_stale, record_verdict, void_matchup,
    load_settings, save_settings, known_tasks, active_tasks, is_task_active,
    resolve_current_task, get_coverage, is_valid_task_id,
    load_answer_flags, save_answer_flags, get_answer_matrix,
    DEFAULT_ELO,
    TASKS_DIR, INDEX_PATH, MODELS_PATH,
)

from register_task import (
    next_task_id, unique_slug_dir, fill_template, TEMPLATE_PATH, slugify as slugify_task,
)

from render_helpers import (
    format_elo_history, format_winrate, format_confidence, get_model_detail, build_elo_svg,
    build_elo_distribution_svg, compute_rank_trends, pagination_items,
    merge_history_feed, history_task_id, plural_ru,
    interval_groups, build_rating_intervals_svg,
    parse_lines_param, parse_period_param, default_line_ids,
    build_elo_series, build_elo_multiline_svg, ELO_LINE_COLORS,
    activity_by_day, build_activity_bars_svg,
    pair_matrix, build_pair_matrix_svg, group_summary,
    delta_leaders, stale_models, opposition_strength, winner_shares,
)

from register_model import parse_existing, format_model

from lookups import (
    load_lookups, save_lookups, has_value, find_value, add_value,
)

from flask import Flask, request, redirect, url_for, Response, abort

app = Flask(__name__)

# Режим «только просмотр»: включён в статическом слепке витрины (export_web).
# Роуты читают флаг из app.config, шаблоны — через функцию read_only(),
# поэтому экспорт переключает режим одной строкой до рендера страниц.
app.config["READ_ONLY"] = False


def read_only() -> bool:
    """Включён ли режим «только просмотр» (в шаблонах: `{% if read_only() %}`)."""
    return bool(app.config.get("READ_ONLY"))


app.jinja_env.globals["read_only"] = read_only


# ─── Версия и сборка консоли ────────────────────────────────────────
# Показываются в подвале (shell.html) и в разделе «О консоли» страницы
# настроек. Версия — тег последнего релиза: релиз фиксируется тегом
# `vX.Y.Z` (docs/versioning.md), промежуточных версий не существует,
# поэтому на коммитах после релиза UI честно показывает последний
# выпущенный релиз. Сборка — время коммита, из которого запущен код
# (у запуска из архива без git — время файла версии проекта); в UI оно
# показывается по минскому времени с меткой `МСК`.

APP_ROOT = Path(__file__).resolve().parent.parent  # корень репозитория

_RELEASE_TAG = re.compile(r"^v?(\d+\.\d+\.\d+)$")
_BUILD_TIME_FMT = "%d.%m.%Y %H:%M МСК"

# Беларусь живёт в UTC+3 круглый год (без перехода на летнее время
# с 2011 года), поэтому достаточно фиксированного смещения: zoneinfo
# на Windows без пакета tzdata недоступен.
MINSK_TZ = timezone(timedelta(hours=3), "MSK")

# git вызывается один раз при импорте модуля (резолв версии и сборки
# ниже); на Windows без консоли (launch.vbs) запуск не мигает окном.
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_git(root: Path, *args: str) -> str | None:
    """Вывод git-команды или None, если git/команда недоступны."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def _git_version(root: Path) -> str | None:
    """Тег ближайшего релиза (`git describe`) или None, если git/тега нет."""
    return _run_git(root, "describe", "--tags", "--abbrev=0")


def _file_version(root: Path) -> str | None:
    """Версия из файла версии проекта (pyproject.toml) или None."""
    try:
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else None


def resolve_app_version(root: Path = APP_ROOT) -> str:
    """Версия консоли для UI в форме релизного тега `vX.Y.Z`.

    Приоритет у тега ближайшего релиза (`git describe`); фолбэк — файл
    версии проекта (git недоступен: архив, клон без тегов — блок не
    должен пустовать). Оба источника нормализуются к `vX.Y.Z`; если
    версии нет вовсе, возвращается пустая строка (блок скрывается).
    """
    for raw in (_git_version(root), _file_version(root)):
        if raw and (tag := _RELEASE_TAG.match(raw.strip())):
            return f"v{tag.group(1)}"
    return ""


def _format_build_time(moment: datetime) -> str:
    """Момент в минской зоне как `ДД.ММ.ГГГГ ЧЧ:ММ МСК`."""
    return moment.astimezone(MINSK_TZ).strftime(_BUILD_TIME_FMT)


def _git_build_time(root: Path) -> str | None:
    """Время последнего коммита по Минску или None без git."""
    raw = _run_git(root, "show", "-s", "--format=%cI", "HEAD")
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return _format_build_time(moment)


def _file_build_time(root: Path) -> str | None:
    """Время файла версии проекта — фолбэк без git (архив, распаковка)."""
    try:
        mtime = (root / "pyproject.toml").stat().st_mtime
    except OSError:
        return None
    return _format_build_time(datetime.fromtimestamp(mtime, tz=MINSK_TZ))


def resolve_build_time(root: Path = APP_ROOT) -> str:
    """Дата и время сборки для UI (по Минску) или пустая строка.

    Приоритет у времени последнего коммита (`git show`); фолбэк — время
    файла версии проекта (git недоступен). Если нет и его, UI покажет
    только версию.
    """
    return _git_build_time(root) or _file_build_time(root) or ""


# Версия и сборка — константы процесса: git-вызовы происходят при
# импорте, а не в первом запросе (бюджеты холодной главной,
# tools/test_perf.py).
_APP_VERSION = resolve_app_version()
_APP_BUILD_TIME = resolve_build_time()


def app_version() -> str:
    """Версия консоли (в шаблонах: `{{ app_version() }}`)."""
    return _APP_VERSION


def app_build_time() -> str:
    """Дата и время сборки (в шаблонах: `{{ app_build_time() }}`)."""
    return _APP_BUILD_TIME


app.jinja_env.globals["app_version"] = app_version
app.jinja_env.globals["app_build_time"] = app_build_time


def _self_url(*, exclude: tuple[str, ...] = ()) -> str:
    """Путь текущей страницы с query, без указанных параметров (для `next`).

    Используется как цель возврата после аннулирования: сквозные сообщения
    (`success`/`error`) и уже применённые действия исключаются, чтобы
    пользователь вернулся к тому же состоянию страницы.
    """
    args = [
        (key, value)
        for key, value in request.args.items(multi=True)
        if key not in exclude
    ]
    query = urlencode(args)
    return request.path + (f"?{query}" if query else "")


def _is_local_path(path: str) -> bool:
    """Разрешён ли `next` как локальный путь (защита от open redirect)."""
    return (
        path.startswith("/")
        and not path.startswith("//")
        and not path.startswith("/\\")
    )


def _redirect_with_message(target: str, *, error: str = "", success: str = ""):
    """Redirect на локальный target с одним сообщением (error или success)."""
    message, key = (error, "error") if error else (success, "success")
    if not message:
        return redirect(target)
    sep = "&" if "?" in target else "?"
    return redirect(f"{target}{sep}{urlencode({key: message})}")


# ─── Helpers ────────────────────────────────────────────────────────


def _load_index() -> dict:
    """Читает index.json один раз; устаревший или битый — пересобирает.

    В режиме «только просмотр» устаревший кэш пересчитывается в памяти
    и не перезаписывается (слепок витрины не меняет данные репозитория).
    """
    idx = None
    if INDEX_PATH.exists():
        try:
            idx = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            idx = None
    if idx is None or is_index_stale(idx, digest=data_cache.data_key()[0]):
        idx = generate_index()
        if not read_only():
            save_index(idx)
    return idx


def ensure_index() -> dict:
    """Возвращает index.json (memo по дайджесту журнала и управляющих файлов)."""
    return data_cache.cached("index", _load_index)


def get_journal_events() -> list[dict]:
    """События журнала в порядке реплея (memo по дайджесту журнала)."""
    return data_cache.cached("journal_events", load_matchups)


def slugify(name: str, existing_ids: list[str]) -> str:
    """Превращает имя модели в slug. Если пусто — model-N. Если занят — суффикс."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        slug = f"model-{len(existing_ids) + 1}"
    base = slug
    suffix = 2
    while slug in existing_ids:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def memo_models() -> list[dict]:
    """Реестр моделей из models.yaml (memo, общий для производных)."""
    return data_cache.cached("models", load_models_yaml)


def get_model_name_map() -> dict[str, str]:
    """Возвращает {id: name} из models.yaml (memo)."""
    return data_cache.cached(
        "model_name_map",
        lambda: {m["id"]: m.get("name", m["id"]) for m in memo_models()},
    )


def get_pair_stats() -> dict[frozenset[str], dict]:
    """Статистика пар (memo): {frozenset{id_a, id_b}: {"games": int, "wins": {id: int}}}.

    Использует resolved ids (model_a_id/model_b_id) и пропускает
    tombstone- и аннулированные вердикты. `winner: "draw"` увеличивает
    только games, не меняя счёт побед.
    """
    return data_cache.cached("pair_scan", _build_pair_scan)[0]


def build_pair_hints_json() -> str:
    """Компактный JSON личных встреч для подсказки формы (memo).

    Ключ — `"<id_x>|<id_y>"` (ids отсортированы), значение — `{g, x, y}`:
    число игр, победы x, победы y. Пары без игр отсутствуют. `</`
    экранируется, чтобы JSON не оборвал script-блок.
    """
    payload: dict[str, dict] = {}
    for key, st in get_pair_stats().items():
        ids = sorted(key)
        if len(ids) != 2:
            continue
        x, y = ids
        payload[f"{x}|{y}"] = {
            "g": st.get("games", 0),
            "x": st.get("wins", {}).get(x, 0),
            "y": st.get("wins", {}).get(y, 0),
        }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).replace("</", "<\\/")


def _build_pair_scan() -> tuple[dict[frozenset[str], dict],
                                dict[frozenset[str], set[str]]]:
    """Один проход по журналу для pair_stats и pair_task_verdicts (memo).

    Резолв id и отсев tombstone/аннулированных событий общие для обеих
    структур, поэтому скан журнала выполняется один раз.
    """
    model_ids = {m["id"] for m in memo_models()}
    stats: dict[frozenset[str], dict] = {}
    verdicts: dict[frozenset[str], set[str]] = {}
    matchups = get_journal_events()
    voided = {mu["void_of"] for mu in matchups if mu.get("void_of")}
    for mu in matchups:
        if mu.get("void_of") or mu.get("_matchup_id") in voided:
            continue
        a = mu.get("model_a_id")
        if a:
            if a not in model_ids:
                a = None
        else:
            a = mu.get("model_a")
            if a not in model_ids:
                a = None
        b = mu.get("model_b_id")
        if b:
            if b not in model_ids:
                b = None
        else:
            b = mu.get("model_b")
            if b not in model_ids:
                b = None
        if not a or not b:
            continue
        key = frozenset({a, b})
        st = stats.get(key)
        if st is None:
            st = stats[key] = {"games": 0, "wins": {a: 0, b: 0}}
        st["games"] += 1
        winner = mu.get("winner")
        if winner == "a":
            st["wins"][a] += 1
        elif winner == "b":
            st["wins"][b] += 1
        task = mu.get("task")
        if not task:
            task = str(mu.get("_matchup_id", "")).split("/", 1)[0]
        if task:
            tasks_set = verdicts.get(key)
            if tasks_set is None:
                tasks_set = verdicts[key] = set()
            tasks_set.add(task)
    return stats, verdicts


def is_model_active(model: dict) -> bool:
    """Проверяет, что модель не заархивирована."""
    return model.get("status", "active") != "archived"


def valid_answer_filter(value: str | None) -> str:
    """Валидирует фильтр матрицы ответов; невалидное → 'active'."""
    v = (value or "active").strip().lower()
    return v if v in ("active", "all", "inactive") else "active"


def valid_filter_view(value: str | None) -> str:
    """Валидирует режим отображения блока «Фильтр»; невалидное → 'hide'."""
    v = (value or "hide").strip().lower()
    return v if v in ("hide", "highlight") else "hide"


def valid_chips_order(value: str | None) -> str:
    """Валидирует порядок чипов блока «Фильтр»; невалидное → 'alpha'."""
    v = (value or "alpha").strip().lower()
    return v if v in ("alpha", "elo") else "alpha"


QUEUE_PAGE_SIZE = 100


def valid_queue_page(value: str | None, pages: int) -> int:
    """Валидирует номер страницы очереди: 1..pages; невалидное → 1."""
    try:
        page = int((value or "").strip() or "1")
    except ValueError:
        return 1
    if page < 1:
        return 1
    if page > pages:
        return pages
    return page


# ─── Блок «Фильтр» ──────────────────────────────────────────────────

TAG_NONE = "none"


def _tag_values(models: dict, key: str) -> tuple[list[str], bool]:
    """Значения тега из реестра: (отсортированные непустые, есть ли пустые)."""
    values: set[str] = set()
    has_none = False
    for info in models.values():
        val = str(info.get(key) or "").strip()
        if val:
            values.add(val)
        else:
            has_none = True
    return sorted(values, key=str.lower), has_none


def _parse_tag_tokens(raw: str | None, known: list[str]) -> set[str]:
    """CSV токенов из запроса (собран `_tag_query_csv`) → выбранные теги.

    Токен `none` = пустое значение («без агента»/«без компании»), неизвестные
    и пустые токены отбрасываются; пустой CSV = пустой набор (без сужения).
    """
    known_set = set(known)
    selected: set[str] = set()
    for token in (raw or "").split(","):
        token = token.strip()
        if token == TAG_NONE:
            selected.add("")
        elif token in known_set:
            selected.add(token)
    return selected


def _tags_csv(selected: set[str]) -> str:
    """Выбранные теги → CSV для URL (сортировка case-insensitive)."""
    items = [TAG_NONE if val == "" else val for val in selected]
    return ",".join(sorted(items, key=str.lower))


def _tag_query_csv(source, name: str) -> str:
    """CSV тег-фильтра из запроса.

    Поддерживает оба транспорта: повторяющиеся параметры (чипы-чекбоксы шлют
    `agents=A&agents=B`) и одиночный CSV (ссылки и скрытые поля — `agents=A,B`).
    """
    return ",".join(value for value in source.getlist(name) if value)


def model_passes_tags(info: dict, agent_sel: set[str], provider_sel: set[str]) -> bool:
    """Проходит ли модель фильтр «Агент и компания».

    ИЛИ внутри группы, И между группами; пустая группа не сужает.
    """
    if agent_sel and str(info.get("agent") or "").strip() not in agent_sel:
        return False
    if provider_sel and str(info.get("provider") or "").strip() not in provider_sel:
        return False
    return True


def _sort_tags_by_elo(values: list[str], models: dict, key: str) -> list[str]:
    """Чипы «по ELO»: убывание максимального ELO группы; ничьи — алфавит.

    Учитывается полный реестр, включая архивные модели.
    """
    def max_elo(value: str) -> int:
        elos = [
            info.get("elo", DEFAULT_ELO)
            for info in models.values()
            if str(info.get(key) or "").strip() == value
        ]
        return max(elos, default=DEFAULT_ELO)

    return sorted(values, key=lambda v: (-max_elo(v), v.lower()))


def filter_panel_context(models: dict, action: str, reset_url: str,
                         hidden_fields: list[dict] | None = None,
                         reset_extra: bool = False) -> dict:
    """Контекст блока «Фильтр» + выборки агента и компании из URL запроса.

    hidden_fields — дополнительные параметры страницы для filter_hidden();
    к ним добавляются непустые CSV текущего выбора agents/providers, чтобы
    отдельные формы страницы не теряли фильтры.
    reset_extra — применён ли на странице собственный фильтр («Показывать»,
    модель, «только долги»): ссылка «Сбросить» показывается, только когда
    отфильтровано хоть что-то.
    Настройки отображения (`view`, `chips`) читаются из query и возвращаются
    как `filter_view`/`filter_chips`; в «Сбросить» и hidden-поля они попадают,
    только когда отличаются от значений по умолчанию.
    """
    filter_view = valid_filter_view(request.args.get("view"))
    filter_chips = valid_chips_order(request.args.get("chips"))
    agents, agents_none = _tag_values(models, "agent")
    providers, providers_none = _tag_values(models, "provider")
    if filter_chips == "elo":
        agents = _sort_tags_by_elo(agents, models, "agent")
        providers = _sort_tags_by_elo(providers, models, "provider")
    agent_sel = _parse_tag_tokens(_tag_query_csv(request.args, "agents"), agents)
    provider_sel = _parse_tag_tokens(_tag_query_csv(request.args, "providers"), providers)
    agents_csv = _tags_csv(agent_sel)
    providers_csv = _tags_csv(provider_sel)
    hidden = list(hidden_fields or [])
    if agents_csv:
        hidden.append({"name": "agents", "value": agents_csv})
    if providers_csv:
        hidden.append({"name": "providers", "value": providers_csv})
    if filter_view != "hide":
        hidden.append({"name": "view", "value": filter_view})
    if filter_chips != "alpha":
        hidden.append({"name": "chips", "value": filter_chips})
    reset = reset_url
    reset_extra_params = {}
    if filter_view != "hide":
        reset_extra_params["view"] = filter_view
    if filter_chips != "alpha":
        reset_extra_params["chips"] = filter_chips
    if reset_extra_params:
        reset = reset + ("&" if "?" in reset else "?") + urlencode(reset_extra_params)
    badge_parts = []
    if filter_view == "highlight":
        badge_parts.append("подсветка")
    if filter_chips == "elo":
        badge_parts.append("чипы по ELO")
    return {
        "filter_action": action,
        "filter_reset_url": reset,
        "filter_hidden_fields": hidden,
        "filter_active": bool(agent_sel or provider_sel),
        "filter_reset_visible": bool(agent_sel or provider_sel) or bool(reset_extra),
        "filter_agents": [
            {"value": v, "label": v, "checked": v in agent_sel} for v in agents
        ],
        "filter_agents_has_none": agents_none,
        "filter_agents_none_checked": "" in agent_sel,
        "filter_providers": [
            {"value": v, "label": v, "checked": v in provider_sel} for v in providers
        ],
        "filter_providers_has_none": providers_none,
        "filter_providers_none_checked": "" in provider_sel,
        "filter_agents_csv": agents_csv,
        "filter_providers_csv": providers_csv,
        "filter_agent_sel": agent_sel,
        "filter_provider_sel": provider_sel,
        "filter_view": filter_view,
        "filter_chips": filter_chips,
        "filter_settings_badge": " · ".join(badge_parts),
    }


def format_model_caption(info: dict) -> str:
    """Серая подпись «Компания · Агент»; пустые части не выводятся."""
    parts = []
    provider = str(info.get("provider") or "").strip()
    agent = str(info.get("agent") or "").strip()
    if provider:
        parts.append(provider)
    if agent:
        parts.append(agent)
    return " · ".join(parts)


def get_pair_task_verdicts() -> dict[frozenset[str], set[str]]:
    """Возвращает {frozenset{id_a, id_b}: set(task_id)} с тасками,
    в которых у пары есть неаннулированный вердикт (memo).

    Использует resolved ids (model_a_id/model_b_id) и пропускает
    tombstone- и аннулированные вердикты.
    """
    return data_cache.cached("pair_scan", _build_pair_scan)[1]


# ─── Memo-обёртки роутов ────────────────────────────────────────────
# Сборка под DataKey мемо-слоя (data_cache); переиспользуют разобранные
# события журнала, чтобы повторные запросы не перечитывали файлы.


def memo_coverage() -> dict:
    """Покрытие прогона (memo)."""
    return data_cache.cached(
        "coverage",
        lambda: get_coverage(
            matchups=get_journal_events(),
            models=memo_models(),
            verdicts=get_pair_task_verdicts(),
            tasks=memo_active_tasks(),
        ),
    )


def memo_answer_matrix() -> dict:
    """Матрица наличия ответов (memo)."""
    return data_cache.cached(
        "answer_matrix",
        lambda: get_answer_matrix(journal=get_journal_events(), models=memo_models()),
    )


def memo_current_task() -> str:
    """Текущая таска (memo)."""
    return data_cache.cached(
        "current_task",
        lambda: resolve_current_task(journal=get_journal_events()),
    )


def memo_known_tasks() -> list[str]:
    """Известные таски (memo)."""
    return data_cache.cached(
        "known_tasks",
        lambda: known_tasks(journal=get_journal_events()),
    )


def memo_active_tasks() -> list[str]:
    """Активные таски (memo)."""
    return data_cache.cached(
        "active_tasks",
        lambda: active_tasks(journal=get_journal_events()),
    )


def memo_task_model_games() -> dict[str, dict[str, int]]:
    """Применённые матчи по таскам и моделям (memo): {task: {model: games}}."""
    return data_cache.cached("task_model_games", _build_task_model_games)


def _build_task_model_games() -> dict[str, dict[str, int]]:
    """Один проход по elo_history: число матчей модели в каждом таске."""
    result: dict[str, dict[str, int]] = {}
    for item in ensure_index().get("elo_history", []):
        task = history_task_id(item)
        if not task:
            continue
        row = result.setdefault(task, {})
        for side in ("model_a_id", "model_b_id"):
            mid = str(item.get(side) or "")
            if mid:
                row[mid] = row.get(mid, 0) + 1
    return result


def get_task_progress(task_id: str) -> dict:
    """Прогресс задачи: вердикты, покрытие пар, модели, аннулированные (memo)."""
    return data_cache.cached(
        f"task_progress:{task_id}",
        lambda: _build_task_progress(task_id),
    )


def _build_task_progress(task_id: str) -> dict:
    """Считает прогресс задачи по index.json, флагам ответов и memo-парам.

    Пары — как в покрытии прогона: T — видимые пары активных моделей с
    флагами ответа на таск (C(k,2) без перечисления пар), F — из них пары
    с неаннулированным вердиктом по таску (карта pair_scan).
    """
    index_data = ensure_index()
    applied = [
        h for h in index_data.get("elo_history", [])
        if history_task_id(h) == task_id
    ]
    voided = [
        h for h in index_data.get("voided_history", [])
        if history_task_id(h) == task_id
    ]

    active_ids = {m.get("id", "") for m in memo_models() if is_model_active(m)}
    flags = data_cache.cached("answer_flags", load_answer_flags)
    task_flags = flags.get(task_id) or {}
    flagged = {mid for mid in active_ids if task_flags.get(mid)}
    k = len(flagged)

    filled = 0
    for pair, pair_tasks in get_pair_task_verdicts().items():
        if task_id not in pair_tasks:
            continue
        a, b = tuple(pair)
        if a in flagged and b in flagged:
            filled += 1

    participants = set()
    for h in applied:
        participants.add(h.get("model_a_id") or "")
        participants.add(h.get("model_b_id") or "")
    participants.discard("")

    return {
        "verdicts": len(applied),
        "filled": filled,
        "total": k * (k - 1) // 2,
        "models": len(participants),
        "voided": len(voided),
    }


def matchups_count_of(index_data: dict) -> int:
    """Число вердиктов журнала: агрегат matchups_summary с fallback."""
    summary = index_data.get("matchups_summary", {})
    if "total" in summary:
        return summary["total"]
    return len(index_data.get("matchups_index", []))


def memo_rematch_count() -> int:
    """Рематчи: вердикты сверх первых встреч пар (memo).

    R = вердикты − число уникальных пар по elo_history
    (model_a_id/model_b_id). Используется единой сводкой на главной
    и в /settings; кэш инвалидируется по дайджесту журнала.
    """
    def _build() -> int:
        index_data = ensure_index()
        pairs = {
            frozenset((e.get("model_a_id"), e.get("model_b_id")))
            for e in index_data.get("elo_history", [])
        }
        return matchups_count_of(index_data) - len(pairs)

    return data_cache.cached("rematch_count", _build)


def find_task_dir(task_id: str) -> Path | None:
    """Находит директорию tasks/T-NNN-<slug> по id."""
    if not TASKS_DIR.exists():
        return None
    for d in TASKS_DIR.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        if re.match(rf"^{re.escape(task_id)}(?:$|-)", d.name):
            return d
    return None


def parse_task_md(text: str) -> dict:
    """Парсит task.md на front matter и тело."""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {"title": "", "project": "", "baseline_commit": "", "body": text}
    front = parts[1]
    body = parts[2].strip()
    data = {}
    for raw in front.splitlines():
        # Убираем inline-комментарии и лишние пробелы
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        data[k] = v
    return {
        "title": data.get("title", ""),
        "project": data.get("project", ""),
        "baseline_commit": data.get("baseline_commit", ""),
        "body": body,
    }


def format_task_md(task_id: str, title: str, project: str, baseline: str, body: str) -> str:
    """Форматирует содержимое task.md."""
    return (
        f"---\n"
        f"id: {task_id}\n"
        f"title: \"{title}\"\n"
        f"project: \"{project}\"\n"
        f"baseline_commit: \"{baseline}\"\n"
        f"---\n\n"
        f"{body.strip()}\n"
    )


def get_task_info(task_id: str) -> dict | None:
    """Возвращает метаданные и тело task.md по id.

    Если директории/файла нет, возвращает stub на основе _TEMPLATE.md,
    чтобы можно было создать задачу через форму редактирования.
    """
    task_dir = find_task_dir(task_id)
    task_file = task_dir / "task.md" if task_dir else None
    if task_file and task_file.exists():
        info = parse_task_md(task_file.read_text(encoding="utf-8"))
        info["id"] = task_id
        info["dir"] = task_dir
        return info

    # Stub: таска есть в настройках, но ещё без task.md
    if not TEMPLATE_PATH.exists():
        return None
    info = parse_task_md(TEMPLATE_PATH.read_text(encoding="utf-8"))
    info["id"] = task_id
    info["missing"] = True
    info["title"] = ""
    return info


def create_task(title: str, slug: str = "", project: str = "", baseline: str = "") -> dict:
    """Создаёт новую задачу: папку, task.md, обновляет settings."""
    if not title:
        raise ValueError("Введите название задачи")
    if not TEMPLATE_PATH.exists():
        raise ValueError("Шаблон tasks/_TEMPLATE.md не найден")

    task_id = next_task_id()
    if not slug:
        slug = slugify_task(title)
    if not slug:
        slug = "task"

    task_dir = unique_slug_dir(task_id, slug)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    filled = fill_template(template, task_id, title, project, baseline)

    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "task.md").write_text(filled, encoding="utf-8")

    settings = load_settings()
    settings["tasks"][task_id] = "active"
    settings["current_task"] = task_id
    save_settings(settings)

    return {"id": task_id, "dir": task_dir}


def update_task(task_id: str, title: str, project: str, baseline: str, body: str) -> bool:
    """Обновляет task.md; если директории нет — создаёт её."""
    task_dir = find_task_dir(task_id)
    if not task_dir:
        slug = slugify_task(title) or "task"
        task_dir = unique_slug_dir(task_id, slug)
    task_dir.mkdir(parents=True, exist_ok=True)
    task_file = task_dir / "task.md"
    task_file.write_text(format_task_md(task_id, title, project, baseline, body), encoding="utf-8")
    return True


def toggle_task_status(task_id: str) -> bool:
    """Переключает статус задачи active/inactive."""
    if not is_valid_task_id(task_id):
        return False
    settings = load_settings()
    current = settings.get("tasks", {}).get(task_id, "active")
    new_status = "inactive" if current == "active" else "active"
    settings["tasks"][task_id] = new_status

    # Если деактивировали текущую — переключаем current на первую активную
    if new_status == "inactive" and settings.get("current_task") == task_id:
        active = [t for t in memo_known_tasks() if is_task_active(settings, t) and t != task_id]
        settings["current_task"] = active[0] if active else ""

    save_settings(settings)
    return True


def set_current_task(task_id: str) -> bool:
    """Назначает текущей задачей, если она активна."""
    if not is_valid_task_id(task_id):
        return False
    settings = load_settings()
    if not is_task_active(settings, task_id):
        return False
    settings["current_task"] = task_id
    save_settings(settings)
    return True


def update_model(model_id: str, name: str, status: str,
                 agent: str = "", provider: str = "") -> bool:
    """Редактирует name/status/agent/provider модели в models.yaml и пересчитывает index."""
    models_path = MODELS_PATH
    if not models_path.exists():
        return False

    text = models_path.read_text(encoding="utf-8")
    models, preamble = parse_existing(text)

    found = False
    for m in models:
        if m["id"] == model_id:
            m["name"] = name
            m["status"] = status
            m["agent"] = agent
            m["provider"] = provider
            found = True
            break

    if not found:
        return False

    models.sort(key=lambda m: m["id"])

    out = preamble.rstrip() + "\n\nmodels:\n"
    for m in models:
        out += format_model(m) + "\n"

    models_path.write_text(out, encoding="utf-8")

    index_data = generate_index()
    save_index(index_data)
    return True


def get_recommendations(index_data: dict, top_n: int = 1) -> list[dict]:
    """Рекомендует пару моделей для следующего прогона (топ-1).

    Обычный режим — только READY-ячейки `(таск, пара)`: активная пара +
    активный таск + оба флага ответа `true` в answer_flags.yaml + нет
    неаннулированного вердикта пары в этом таске. BLOCKED-ячейки
    (хотя бы одного ответа нет) невидимы.
    Сортировка лексикографическая:
    1. приоритет таска (лексикографический порядок T-NNN по возрастанию —
       T-001 выше любых ячеек T-002, пока в T-001 есть READY);
    2. pair_games пары по возрастанию (глобальное число вердиктов пары);
    3. тир калибровки (по min_games — числу игр менее
       игранной модели в паре):
       тир 0: min_games == 0 (новая модель, ещё не играла)
       тир 1: min_games < 3 (мало игр, нужна калибровка)
       тир 2: остальные;
    4. внутри тира по близости ELO (меньше elo_diff — выше).

    Режим рематчей (READY-ячеек нет): кандидаты — все пары активных
    моделей C(n,2) без учёта флагов ответов; сортировка: pair_games,
    затем тир, затем близость ELO; recommended_task — первый активный
    таск. Запись помечается is_rematch=True.

    Возвращает список dict: {model_a, model_b, name_a, name_b, elo_a,
    elo_b, elo_diff, pair_games, pair_wins_a, pair_wins_b, h2h_label,
    tier, score, recommended_task, is_rematch}
    """
    models = index_data.get("models", {})
    name_map = get_model_name_map()

    # Только active-модели с данными из index
    model_ids = sorted(
        mid for mid, info in models.items() if is_model_active(info)
    )
    if len(model_ids) < 2:
        return []

    # ELO и игры из index
    elo_map = {mid: models[mid].get("elo", DEFAULT_ELO) for mid in model_ids}
    games_map = {mid: models[mid].get("games", 0) for mid in model_ids}

    pair_stats = get_pair_stats()
    pair_task_verdicts = get_pair_task_verdicts()
    active_task_ids = active_tasks(load_settings(), get_journal_events())
    flags = load_answer_flags()

    # Ключи пар — канонические кортежи `(id_меньший, id_больший)`: перебор
    # идёт по позициям отсортированного model_ids, поэтому пара уже
    # каноническая и frozenset на каждый кандидат не нужен. ELO и игры —
    # плоскими списками по позициям, без словарных lookup по строке.
    stats_by_pair = {tuple(sorted(key)): st for key, st in pair_stats.items()}
    verdicts_by_pair = {
        tuple(sorted(key)): tasks for key, tasks in pair_task_verdicts.items()
    }
    elo_list = [elo_map[mid] for mid in model_ids]
    games_list = [games_map[mid] for mid in model_ids]

    def _build_rec(a: str, b: str, recommended_task: str,
                   is_rematch: bool) -> dict:
        st = stats_by_pair.get((a, b))
        pair_games = st["games"] if st is not None else 0
        pair_wins_a = st["wins"].get(a, 0) if st else 0
        pair_wins_b = st["wins"].get(b, 0) if st else 0

        elo_a = elo_map[a]
        elo_b = elo_map[b]
        elo_diff = abs(elo_a - elo_b)
        min_games = min(games_map[a], games_map[b])

        # Тир калибровки: новая модель всегда выше калибрующейся,
        # калибрующаяся — выше сыгранных. Внутри тира — близость ELO.
        if min_games == 0:
            tier = 0
        elif min_games < 3:
            tier = 1
        else:
            tier = 2

        # Строка личных встреч: число вердиктов пары и — при наличии —
        # ничьи. Счёт по победам печатается в строке-обосновании
        # (format_reason), чтобы не дублироваться.
        if pair_games > 0:
            h2h_label = f"личные встречи: {pair_games}"
            draws = pair_games - pair_wins_a - pair_wins_b
            if draws > 0:
                h2h_label += f" · ничьих {draws}"
        else:
            h2h_label = "личные встречи: не встречались"

        # score = близость ELO: монотонно убывает с ростом diff
        closeness = 1.0 / (1.0 + elo_diff / 100.0)

        return {
            "model_a": a,
            "model_b": b,
            "name_a": name_map.get(a, a),
            "name_b": name_map.get(b, b),
            "elo_a": elo_a,
            "elo_b": elo_b,
            "elo_diff": elo_diff,
            "pair_games": pair_games,
            "pair_wins_a": pair_wins_a,
            "pair_wins_b": pair_wins_b,
            "h2h_label": h2h_label,
            "tier": tier,
            "score": closeness,
            "recommended_task": recommended_task,
            "is_rematch": is_rematch,
        }

    # Обычный режим: READY-ячейки (оба ответа есть, вердикта в таске нет).
    # Перебор — только моделей с флагами ответов; ключ отбора — кортеж
    # (порядок таска, pair_games, тир, ΔELO): сортировка по ΔELO
    # эквивалентна сортировке по -closeness (монотонная замена), но
    # целочисленна. Хвост хвостового ключа (id A, id B, таск) повторяет
    # стабильный порядок перебора: пары идут лексикографически, таски —
    # по возрастанию id. top-K берётся heapq.nsmallest без key — самый
    # дешёвый путь для потока кортежей.
    def _ready_candidates():
        for order, task in enumerate(active_task_ids):
            task_flags = flags.get(task) or {}
            flagged = [i for i, mid in enumerate(model_ids) if task_flags.get(mid)]
            for ii in range(len(flagged)):
                i = flagged[ii]
                a = model_ids[i]
                elo_i = elo_list[i]
                games_i = games_list[i]
                for jj in range(ii + 1, len(flagged)):
                    j = flagged[jj]
                    b = model_ids[j]
                    verdicts = verdicts_by_pair.get((a, b))
                    if verdicts is not None and task in verdicts:
                        continue
                    st = stats_by_pair.get((a, b))
                    pair_games = st["games"] if st is not None else 0
                    elo_diff = elo_i - elo_list[j]
                    if elo_diff < 0:
                        elo_diff = -elo_diff
                    games_j = games_list[j]
                    min_games = games_i if games_i <= games_j else games_j
                    if min_games == 0:
                        tier = 0
                    elif min_games < 3:
                        tier = 1
                    else:
                        tier = 2
                    yield order, pair_games, tier, elo_diff, a, b, task

    ready = heapq.nsmallest(top_n, _ready_candidates())
    if ready:
        return [
            _build_rec(a, b, task, False)
            for (_order, _games, _tier, _diff, a, b, task) in ready
        ]

    # Режим рематчей: READY пуст — все активные пары без учёта флагов.
    # Те же ключи (pair_games, тир, ΔELO) при том же порядке перебора.
    default_task = active_task_ids[0] if active_task_ids else ""

    def _rematch_candidates():
        for i in range(len(model_ids)):
            a = model_ids[i]
            elo_i = elo_list[i]
            games_i = games_list[i]
            for j in range(i + 1, len(model_ids)):
                b = model_ids[j]
                st = stats_by_pair.get((a, b))
                pair_games = st["games"] if st is not None else 0
                elo_diff = elo_i - elo_list[j]
                if elo_diff < 0:
                    elo_diff = -elo_diff
                games_j = games_list[j]
                min_games = games_i if games_i <= games_j else games_j
                if min_games == 0:
                    tier = 0
                elif min_games < 3:
                    tier = 1
                else:
                    tier = 2
                yield pair_games, tier, elo_diff, a, b

    rematches = heapq.nsmallest(top_n, _rematch_candidates())
    return [
        _build_rec(a, b, default_task, True)
        for (_games, _tier, _diff, a, b) in rematches
    ]


def format_reason(rec: dict) -> str:
    """Строка-обоснование рекомендации (только отображение).

    Вычисляется из готовых полей рекомендации; вывод get_recommendations
    не меняется (поле reason в нём запрещено спекой pairing-algorithm).
    """
    games = rec.get("pair_games", 0)
    diff = rec.get("elo_diff", 0)
    if games == 0:
        text = f"не встречались · Δ={diff}"
        if rec.get("tier", 2) == 0:
            text += " · новая модель"
        return text
    return (
        f"счёт по победам {rec.get('pair_wins_a', 0)}:{rec.get('pair_wins_b', 0)}"
        f" · Δ={diff}"
    )


# ─── Селекции волны 3: рейтинг, история, экспорт ────────────────────
# (change console-wave3-data-scale)


RATING_SORT_KEYS = ("rank", "name", "elo", "games", "winrate", "trend")
RATING_SORT_DEFAULTS = {
    "rank": "asc", "name": "asc", "elo": "desc", "games": "desc",
    "winrate": "desc", "trend": "desc",
}


def parse_rating_sort(args) -> tuple[str, str]:
    """Разбирает `sort`/`dir` рейтинга; невалидные — как без сортировки."""
    sort = (args.get("sort") or "").strip().lower()
    if sort not in RATING_SORT_KEYS:
        return "", ""
    direction = (args.get("dir") or "").strip().lower()
    if direction not in ("asc", "desc"):
        direction = RATING_SORT_DEFAULTS[sort]
    return sort, direction


def rating_request_state(models: dict) -> dict:
    """Общие параметры главной из query: режим, чипы, поиск, сортировка.

    Один разбор для страницы и экспорта, чтобы выборки не расходились.
    """
    filter_mode = (request.args.get("filter") or "active").strip().lower()
    if filter_mode not in ("active", "all", "inactive"):
        filter_mode = "active"
    agents, _ = _tag_values(models, "agent")
    providers, _ = _tag_values(models, "provider")
    agent_sel = _parse_tag_tokens(_tag_query_csv(request.args, "agents"), agents)
    provider_sel = _parse_tag_tokens(_tag_query_csv(request.args, "providers"), providers)
    sort, direction = parse_rating_sort(request.args)
    return {
        "filter_mode": filter_mode,
        "highlight": valid_filter_view(request.args.get("view")) == "highlight",
        "agent_sel": agent_sel,
        "provider_sel": provider_sel,
        "query": (request.args.get("q") or "").strip(),
        "sort": sort,
        "direction": direction,
    }


def model_matches_query(info: dict, query: str) -> bool:
    """Поиск `q` рейтинга: регистронезависимая подстрока имени или id."""
    if not query:
        return True
    q = query.casefold()
    return (
        q in str(info.get("name", "")).casefold()
        or q in str(info.get("id", "")).casefold()
    )


def _rating_sort_value(m: dict, sort: str):
    """Ключ сортировки строки рейтинга; None — «нет значения» (в конец)."""
    if sort == "rank":
        return m.get("rank", 0)
    if sort == "name":
        return str(m.get("name", "")).casefold()
    if sort == "elo":
        return m.get("elo", DEFAULT_ELO)
    if sort == "games":
        return m.get("games", 0)
    if sort == "winrate":
        games = int(m.get("games", 0) or 0)
        return (int(m.get("wins", 0) or 0) / games) if games else None
    num = str(m.get("trend_num", "")).strip()
    if num == "=":
        return 0
    try:
        return int(num)
    except ValueError:
        return None


def sort_rating_rows(rows: list[dict], sort: str, direction: str) -> list[dict]:
    """Порядок строк для вывода: выбранный ключ, вторичный — место.

    «Нет значения» (винрейт без игр, тренд «–») — в конце при любом
    направлении; без `sort` сохраняется исходный порядок (место по ELO).
    """
    if not sort:
        return list(rows)
    ordered = sorted(rows, key=lambda m: m.get("rank", 0))
    with_value = [m for m in ordered if _rating_sort_value(m, sort) is not None]
    without = [m for m in ordered if _rating_sort_value(m, sort) is None]
    with_value.sort(
        key=lambda m: _rating_sort_value(m, sort), reverse=(direction == "desc")
    )
    return with_value + without


def rating_selection(index_data: dict, filter_mode: str, agent_sel: set,
                     provider_sel: set, highlight: bool, query: str) -> dict:
    """Пул и видимые строки рейтинга — общий конвейер страницы и экспорта.

    Места и индикаторы d5 считаются по статусному пулу (копии строк,
    мемо-index чистый); блок «Фильтр» и поиск только сужают состав:
    в «Скрывать лишние» — сам список, в «Подсвечивать» — список при
    сохранении разметки hit. Сортировка — вызывающей стороной через
    `sort_rating_rows` (тренды должны быть проставлены раньше).
    """
    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")

    if highlight:
        models_sorted = [dict(info) for info in models.values()]
    elif filter_mode == "active":
        models_sorted = [
            dict(info) for info in models.values() if is_model_active(info)
        ]
    elif filter_mode == "inactive":
        models_sorted = [
            dict(info) for info in models.values() if not is_model_active(info)
        ]
    else:
        models_sorted = [dict(info) for info in models.values()]
    models_sorted.sort(key=lambda m: (-m.get("elo", DEFAULT_ELO), m.get("id", "")))

    for rank, m in enumerate(models_sorted, start=1):
        m["rank"] = rank
        m["caption"] = format_model_caption(m)

    def status_matches(info: dict) -> bool:
        """Статусный критерий «Показывать» (в подсветке — критерий hit)."""
        if filter_mode == "active":
            return is_model_active(info)
        if filter_mode == "inactive":
            return not is_model_active(info)
        return True

    if highlight:
        for m in models_sorted:
            m["hit"] = status_matches(m) and model_passes_tags(m, agent_sel, provider_sel)
        models_visible = [m for m in models_sorted if model_matches_query(m, query)]
        highlight_hits = sum(1 for m in models_visible if m["hit"])
    else:
        models_visible = [
            m for m in models_sorted
            if model_passes_tags(m, agent_sel, provider_sel)
            and model_matches_query(m, query)
        ]
        highlight_hits = 0

    # Тренды d5: пул детерминирован парой (highlight, filter_mode).
    pool_ids = [m.get("id", "") for m in models_sorted]
    current_elo = {m.get("id", ""): m.get("elo", DEFAULT_ELO) for m in models_sorted}
    trends = data_cache.cached(
        f"trends:{'all' if highlight else filter_mode}",
        lambda: compute_rank_trends(
            index_data.get("elo_history", []), pool_ids, current_elo,
        ),
    )
    for m in models_sorted:
        t = trends.get(m.get("id", ""), {})
        m["trend_label"] = t.get("label", "–")
        m["trend_arrow"] = t.get("arrow", "")
        m["trend_num"] = t.get("num", "–")
        m["trend_class"] = t.get("css", "history-delta-neutral")
        m["trend_title"] = t.get("title", "")

    return {
        "models_sorted": models_sorted,
        "models_visible": models_visible,
        "highlight_hits": highlight_hits,
    }


def rating_sort_context() -> dict:
    """Контекст сортировки рейтинга: активный ключ и `sort_url(col)`.

    `sort_url` сохраняет прочие параметры страницы (фильтр, чипы, поиск) и
    переворачивает направление при повторном клике по активной колонке.
    """
    sort, direction = parse_rating_sort(request.args)
    base = {
        key: value for key, value in request.args.items()
        if key not in ("sort", "dir") and value
    }

    def sort_url(col: str) -> str:
        if sort == col:
            next_dir = "asc" if direction == "desc" else "desc"
        else:
            next_dir = RATING_SORT_DEFAULTS.get(col, "asc")
        return url_for("leaderboard", **base, sort=col, dir=next_dir)

    return {"sort": sort, "sort_dir": direction, "sort_url": sort_url}


def rating_export_urls() -> dict:
    """Ссылки экспорта рейтинга с текущими параметрами страницы."""
    base = {key: value for key, value in request.args.items() if value}
    return {
        "csv": url_for("export_rating_csv", **base),
        "json": url_for("export_rating_json", **base),
    }


def _valid_iso_date(value: str | None) -> str:
    """Валидная дата `YYYY-MM-DD`; иначе пусто (фильтр игнорируется)."""
    value = (value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return ""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return ""
    return value


def parse_history_search(models: dict) -> dict:
    """Поисковые фильтры истории из query; невалидные значения игнорируются.

    `pair` вида `idA:idB` с обоими id из реестра — точная пара; иначе —
    подстрока по id и именам обеих моделей записи. `active` — задан ли
    поисковый фильтр (для счётчика «найдено»), без чипа «только
    аннулированные»: он фильтрует ленту отдельно.
    """
    task = (request.args.get("task") or "").strip().split("/", 1)[0].strip()
    outcome = (request.args.get("outcome") or "").strip().lower()
    if outcome not in ("a", "b", "draw"):
        outcome = ""
    pair = (request.args.get("pair") or "").strip()
    pair_ids = None
    if pair.count(":") == 1:
        left, right = (part.strip() for part in pair.split(":", 1))
        if left and right and left != right and left in models and right in models:
            pair_ids = (left, right)
    from_value = _valid_iso_date(request.args.get("from"))
    to_value = _valid_iso_date(request.args.get("to"))
    return {
        "task": task,
        "from": from_value,
        "to": to_value,
        "outcome": outcome,
        "pair": "" if pair_ids else pair,
        "pair_ids": pair_ids,
        "only_voided": (request.args.get("only_voided") or "") == "1",
        "active": bool(task or from_value or to_value or outcome or pair),
    }


def history_date_of(item: dict) -> str:
    """Дата записи для фильтра: `date`, при отсутствии — `recorded_at`."""
    value = str(item.get("date") or "").strip()
    if value:
        return value[:10]
    return str(item.get("recorded_at") or "")[:10]


def history_matches_search(item: dict, search: dict, models: dict) -> bool:
    """Поисковые фильтры ленты: таск, диапазон дат, исход, поиск по паре."""
    if search["task"] and history_task_id(item) != search["task"]:
        return False
    date_value = history_date_of(item)
    if search["from"] and date_value < search["from"]:
        return False
    if search["to"] and date_value > search["to"]:
        return False
    if search["outcome"] and str(item.get("winner") or "") != search["outcome"]:
        return False
    pair_ids = search["pair_ids"]
    if pair_ids:
        pair = {str(item.get("model_a_id") or ""), str(item.get("model_b_id") or "")}
        if pair != set(pair_ids):
            return False
    elif search["pair"]:
        a_id = str(item.get("model_a_id") or "")
        b_id = str(item.get("model_b_id") or "")
        a_name = str((models.get(a_id) or {}).get("name") or a_id)
        b_name = str((models.get(b_id) or {}).get("name") or b_id)
        blob = f"{a_id} {b_id} {a_name} {b_name}".casefold()
        if search["pair"].casefold() not in blob:
            return False
    return True


def build_history_feed(index_data: dict, models: dict, search: dict, *,
                       model_id: str, agent_sel: set, provider_sel: set,
                       highlight: bool, include_voided: bool) -> dict:
    """Лента истории — общий конвейер страницы и экспорта.

    Объединение с аннулированными (`include_voided` или `only_voided`) →
    фильтры модель/чипы → «только аннулированные» → поисковые фильтры →
    счётчики. «Всего записей» — до поисковых фильтров, «найдено» — после;
    в «Подсвечивать» состав по модель/чипам не сужается, отобранные
    помечаются hit.
    """
    if include_voided or search["only_voided"]:
        records = merge_history_feed(
            index_data.get("elo_history", []),
            index_data.get("voided_history", []),
        )
    else:
        records = list(reversed(index_data.get("elo_history", [])))

    if highlight:
        for h in records:
            if model_id:
                h["hit"] = (
                    h.get("model_a_id") == model_id or h.get("model_b_id") == model_id
                )
            else:
                h["hit"] = (
                    model_passes_tags(models.get(h.get("model_a_id"), {}), agent_sel, provider_sel)
                    or model_passes_tags(models.get(h.get("model_b_id"), {}), agent_sel, provider_sel)
                )
    elif model_id:
        records = [
            h for h in records
            if h.get("model_a_id") == model_id or h.get("model_b_id") == model_id
        ]
    else:
        records = [
            h for h in records
            if model_passes_tags(models.get(h.get("model_a_id"), {}), agent_sel, provider_sel)
            or model_passes_tags(models.get(h.get("model_b_id"), {}), agent_sel, provider_sel)
        ]

    total = len(records)
    if search["only_voided"]:
        records = [h for h in records if h.get("voided")]
    if search["active"]:
        records = [h for h in records if history_matches_search(h, search, models)]
    hits = sum(1 for h in records if h.get("hit")) if highlight else 0
    return {
        "records": records,
        "total": total,
        "found": len(records),
        "voided": sum(1 for h in records if h.get("voided")),
        "hits": hits,
    }


def history_export_urls(history_params: dict) -> dict:
    """Ссылки экспорта истории с текущими параметрами страницы."""
    base = {key: value for key, value in history_params.items() if value}
    return {
        "csv": url_for("export_history_csv", **base),
        "json": url_for("export_history_json", **base),
    }


def _attachment(filename: str, content_type: str, body: str) -> Response:
    """Ответ-файл с Content-Disposition: attachment."""
    response = Response(body, content_type=content_type)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _csv_text(header: list[str], rows: list[list]) -> str:
    """CSV выборки: UTF-8 с BOM, разделитель `;`, переводы строк CRLF."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return "\ufeff" + buffer.getvalue()


# ─── HTML: Leaderboard page ─────────────────────────────────────────

INDEX_TEMPLATE = """{% extends "shell.html" %}
{% from "_tag_filter.html" import filter_panel with context %}
{% block title %}ELO Benchmark{% endblock %}
{% block content %}
  {% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
  {% if success %}
  <div class="alert alert-success" role="status">
    <span class="alert-text">{{ success }}</span>
    {% if not read_only() %}
    <span class="alert-actions">
      {% if saved_matchup_id %}
      <details class="void-form void-form-inline">
        <summary class="void-form-open">Отменить</summary>
        <form method="POST" action="/verdict/void" class="void-form-body">
          <input type="hidden" name="matchup_id" value="{{ saved_matchup_id }}">
          <input type="hidden" name="next" value="{{ void_next }}">
          <input type="text" name="reason" class="void-reason" placeholder="Причина аннулирования" required>
          <button type="submit" class="btn btn-danger btn-sm">Аннулировать вердикт</button>
        </form>
      </details>
      {% endif %}
      <button type="button" class="btn btn-secondary btn-sm" onclick="writeMore()">Записать ещё</button>
    </span>
    {% endif %}
  </div>
  {% endif %}

  <div class="progress-card{% if coverage_pct is none %} progress-card--empty{% elif coverage_done %} progress-card--done{% endif %}">
    {% if coverage_done %}
    <div class="progress-done-line">Прогресс прогона — 100% · все пары закрыты</div>
    {% else %}
    <div class="progress-head">
      <span class="progress-title">Прогресс прогона</span>
      <span class="progress-pct">{% if coverage_pct is none %}—{% else %}{{ coverage_pct }}%{% endif %}</span>
    </div>
    <div class="progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100"{% if coverage_pct is not none %} aria-valuenow="{{ coverage_pct }}"{% endif %} aria-label="Прогресс прогона">
      <div class="progress-fill" style="width: {{ coverage.percent or 0 }}%"></div>
    </div>
    <div class="progress-meta">
      {% if coverage_pct is none %}
      <span>Нет данных о покрытии</span>
      {% else %}
      <span>закрыто {{ coverage.filled }} из {{ coverage.total }}</span>
      <span>осталось {{ remaining }}</span>
      {% endif %}
    </div>
    {% endif %}
  </div>

  <div class="controls">
    <div class="stats stats-summary">
      {% if filter_view == 'highlight' %}Моделей: <a href="/settings#models">{{ models_count }}</a> · подсвечено {{ highlight_hits }}{% else %}Моделей: <a href="/settings#models">{{ filtered_count }}</a> из {{ models_count }}{% endif %} · Вердиктов: <a href="/history">{{ matchups_count }}</a>{% if rematch_count %} (рематчей: {{ rematch_count }}){% endif %} · Пары: <a href="/settings#recommendation-queue">{{ coverage.filled }}/{{ coverage.total }}</a> · Таски: <a href="/settings#tasks">{{ active_tasks_count }} из {{ known_tasks_count }}</a> · Обновлено: {{ updated }}
    </div>
    <div class="legend">Старт 1200 · K 40/32/24 · ничья 0.5 · ± = 400/√игр · прогрев &lt;10 игр · тренд ↑/↓ за 5 личных</div>
    {% call filter_panel() %}
      <span class="filter-label">Показывать</span>
      <div class="segmented" role="radiogroup" aria-label="Показывать">
        <label><input type="radio" name="filter" value="active" {% if filter == 'active' %}checked{% endif %} onchange="this.form.submit()"><span>Активные</span></label>
        <label><input type="radio" name="filter" value="all" {% if filter == 'all' %}checked{% endif %} onchange="this.form.submit()"><span>Все</span></label>
        <label><input type="radio" name="filter" value="inactive" {% if filter == 'inactive' %}checked{% endif %} onchange="this.form.submit()"><span>Неактивные</span></label>
      </div>
      {% if not read_only() %}
      <span class="filter-label">Поиск</span>
      <input type="search" name="q" value="{{ search_query }}" class="filter-search" placeholder="имя или id" aria-label="Поиск по имени или id" onchange="this.form.submit()">
      {% endif %}
    {% endcall %}
  </div>

  <div class="content-grid">
    <div class="main-column">
      <div class="card rating-card">
        <div class="card-head">
          <h2>Рейтинг</h2>
          {% if not read_only() and export_rating_urls %}
          <span class="export-links" aria-label="Экспорт выборки">
            <a class="btn btn-secondary btn-sm" href="{{ export_rating_urls.csv }}">Скачать CSV</a>
            <a class="btn btn-secondary btn-sm" href="{{ export_rating_urls.json }}">Скачать JSON</a>
          </span>
          {% endif %}
        </div>
        {% if models_visible %}
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col"{% if sort == 'rank' %} aria-sort="{{ 'ascending' if sort_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}#{% else %}<a class="sort-link" href="{{ sort_url('rank') }}" title="Сортировать по месту">#{% if sort == 'rank' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if sort_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
                <th scope="col"{% if sort == 'trend' %} aria-sort="{{ 'ascending' if sort_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}Тренд{% else %}<a class="sort-link" href="{{ sort_url('trend') }}" title="Сортировать по тренду d5">Тренд{% if sort == 'trend' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if sort_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
                <th scope="col"{% if sort == 'name' %} aria-sort="{{ 'ascending' if sort_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}Модель{% else %}<a class="sort-link" href="{{ sort_url('name') }}" title="Сортировать по имени">Модель{% if sort == 'name' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if sort_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
                <th scope="col"{% if sort == 'elo' %} aria-sort="{{ 'ascending' if sort_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}ELO{% else %}<a class="sort-link" href="{{ sort_url('elo') }}" title="Сортировать по ELO">ELO{% if sort == 'elo' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if sort_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
                <th scope="col">±</th>
                <th scope="col">Побед</th>
                <th scope="col">Поражений</th>
                <th scope="col">Ничьих</th>
                <th scope="col"{% if sort == 'games' %} aria-sort="{{ 'ascending' if sort_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}Всего{% else %}<a class="sort-link" href="{{ sort_url('games') }}" title="Сортировать по числу игр">Всего{% if sort == 'games' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if sort_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
                <th scope="col"{% if sort == 'winrate' %} aria-sort="{{ 'ascending' if sort_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}Винрейт, %{% else %}<a class="sort-link" href="{{ sort_url('winrate') }}" title="Сортировать по винрейту">Винрейт, %{% if sort == 'winrate' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if sort_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
              </tr>
            </thead>
            <tbody>
              {% for m in models_visible %}
              <tr class="{{ 'archived' if m.status == 'archived' }}{{ (' top-%d' % medals[m.id]) if m.id in medals and show_medals }}{% if filter_view == 'highlight' and highlight_hits %} {{ 'filter-hit' if m.hit else 'filter-miss' }}{% endif %}">
                <td class="rank">{% if m.id in medals and show_medals %}<span class="medal">{{ medal_icons[medals[m.id] - 1] }}</span>{% endif %}<span class="rank-num">{{ m.rank }}</span></td>
                <td class="trend-cell">{% if m.trend_arrow %}<span class="trend {{ m.trend_class }}" title="{{ m.trend_title }}"><span class="trend-arrow">{{ m.trend_arrow }}</span><span class="trend-num">{{ m.trend_num }}</span></span>{% endif %}</td>
                <td class="model-cell">
                  <div>
                    <a href="/model/{{ m.id }}" class="edit-link">{{ m.name }}</a>
                    {% if m.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>{% endif %}
                    {% if m.games < 10 %}<span class="status-pill status-warmup">прогрев</span>{% endif %}
                  </div>
                  {% if m.caption %}<div class="model-caption">{{ m.caption }}</div>{% endif %}
                </td>
                <td>{{ m.elo }}</td>
                <td class="confidence">{{ format_confidence(m.games) }}</td>
                <td class="wld w">{{ m.wins }}</td>
                <td class="wld l">{{ m.losses }}</td>
                <td class="wld d">{{ m.draws }}</td>
                <td>{{ m.games }}</td>
                <td class="winrate">{{ format_winrate(m.wins, m.games) }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        {% if filter_view == 'highlight' and not highlight_hits %}
        <div class="hint">Ничего не подсвечено — ни одна модель не проходит выбранные условия.</div>
        {% endif %}
        {% elif models_sorted %}
        <div class="empty-state">
          {% if search_query %}
          Ничего не найдено по запросу «{{ search_query }}».
          Сбросьте поиск, чтобы увидеть список.
          {% else %}
          Под выбранный фильтр не попала ни одна модель.
          Сбросьте фильтр, чтобы увидеть список.
          {% endif %}
        </div>
        {% else %}
        <div class="empty-state">
          {% if filter == 'active' %}
          Нет активных моделей. Переключите фильтр или добавьте новую модель.
          {% elif filter == 'inactive' %}
          Нет неактивных (архивных) моделей.
          {% else %}
          Нет моделей. Добавьте модель через «Настройки», чтобы начать.
          {% endif %}
        </div>
        {% endif %}
        {% if filter == 'active' and archived_list and filter_view == 'hide' %}
        <details class="archived-section">
          <summary>Архивные модели ({{ archived_list|length }})</summary>
          <ul>
            {% for a in archived_list %}
            <li>
              <span class="archived-name">
                <a href="{{ url_for('model_page', model_id=a.id, agents=filter_agents_csv or none, providers=filter_providers_csv or none) }}" class="edit-link">{{ a.name }}</a>
                {% if a.caption %}<span class="model-caption">{{ a.caption }}</span>{% endif %}
              </span>
              <span>{{ a.elo }}</span>
            </li>
            {% endfor %}
          </ul>
        </details>
        {% endif %}
      </div>


    </div>

    <div class="sidebar">
      {% if recommendations %}
      {% set rec_list = recommendations[:1] if read_only() else recommendations[:3] %}
      <div class="card">
        <div class="rec-header">
          <h2>Рекомендуемые модели к прогону</h2>
        </div>
        {% for rec in rec_list %}
        <div class="rec-item rec-variant"{% if not loop.first %} hidden{% endif %}>
          <div class="rec-info">
            <div class="rec-pair">
              <a href="/model/{{ rec.model_a }}" class="edit-link">{{ rec.name_a }}</a>
              <span class="rec-elo">{{ rec.elo_a }}</span>
              <span class="rec-vs">vs</span>
              <a href="/model/{{ rec.model_b }}" class="edit-link">{{ rec.name_b }}</a>
              <span class="rec-elo">{{ rec.elo_b }}</span>
            </div>
            <div class="rec-h2h">{{ rec.h2h_label }}</div>
            <div class="rec-reason">{{ rec.reason }}</div>
            {% if rec.is_rematch %}<div class="rec-rematch">доп. точность: рематч</div>{% endif %}
            <div class="rec-task">таск: <a href="{{ url_for('task_page', task_id=rec.recommended_task) }}" class="edit-link">{{ rec.recommended_task }}</a></div>
          </div>
          {% if read_only() %}
          <button class="rec-btn" type="button" disabled>Прогнать</button>
          {% else %}
          <button class="rec-btn" onclick="usePair('{{ rec.model_a }}', '{{ rec.model_b }}', '{{ rec.recommended_task }}')">Прогнать</button>
          {% endif %}
        </div>
        {% endfor %}
        {% if not read_only() and rec_list|length > 1 %}
        <div class="rec-actions">
          <button type="button" class="btn btn-secondary btn-sm" onclick="cycleRecommendation()">Другая пара</button>
        </div>
        {% endif %}
      </div>
      {% endif %}
      <div class="card">
        <h2>Записать результат</h2>
        {% if models_list|length >= 2 %}
        {% if read_only() %}<fieldset disabled>{% else %}<form method="POST" action="/verdict" id="verdictForm">{% endif %}
          <div class="verdict-row">
            <div class="form-group">
              <label>Модель A</label>
              <select name="model_a" id="modelA"{% if not read_only() %} data-combobox data-label="Модель A"{% endif %} onchange="validate()">
                <option value="">— выбрать —</option>
                {% for mid, mname, magent in models_list %}
                <option value="{{ mid }}" data-agent="{{ magent }}" {% if mid == pre_a %}selected{% endif %}>{{ mname }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="form-group">
              <label>Модель B</label>
              <select name="model_b" id="modelB"{% if not read_only() %} data-combobox data-label="Модель B"{% endif %} onchange="validate()">
                <option value="">— выбрать —</option>
                {% for mid, mname, magent in models_list %}
                <option value="{{ mid }}" data-agent="{{ magent }}" {% if mid == pre_b %}selected{% endif %}>{{ mname }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="form-group">
              <label for="taskField">Таск</label>
              <select name="task" id="taskField" onchange="validate()" required>
                <option value="">— выбрать —</option>
                {% for t in task_options %}
                <option value="{{ t }}" {% if t == (pre_task or current_task) %}selected{% endif %}>{{ t }}</option>
                {% endfor %}
              </select>
            </div>
            <div class="form-group">
              <label for="dateField">Дата</label>
              <input type="date" name="date" id="dateField" value="{{ pre_date or today }}">
            </div>
          </div>
          <div class="verdict-hint-row">
            <button type="button" class="btn btn-secondary btn-sm" id="swapBtn" onclick="swapModels()">Поменять A ↔ B</button>
            <span class="pair-hint" id="pairHint" aria-live="polite"></span>
          </div>
          <div class="verdict-actions">
            <button type="submit" name="winner" value="a" class="btn btn-win" id="btnA" disabled>Победила A</button>
            <button type="submit" name="winner" value="b" class="btn btn-lose" id="btnB" disabled>Победила B</button>
            <button type="submit" name="winner" value="draw" class="btn btn-draw" id="btnDraw" disabled>Ничья</button>
          </div>
        {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
        {% else %}
        <div class="empty-state">
          Нужно минимум 2 модели, чтобы записать результат.
        </div>
        {% endif %}
      </div>
    </div>
  </div>

<script type="application/json" id="pair-hints">{{ pair_hints_json|safe }}</script>

{% if not read_only() %}
<script>
const pairHints = (() => {
  const el = document.getElementById('pair-hints');
  if (!el) return {};
  try { return JSON.parse(el.textContent); } catch (e) { return {}; }
})();

function optionName(select, value) {
  for (const opt of select.options) {
    if (opt.value === value) return opt.textContent.trim();
  }
  return '';
}

function updateOutcomeLabels(a, b) {
  const named = a && b && a !== b;
  document.getElementById('btnA').textContent =
    named ? 'Победила ' + optionName(document.getElementById('modelA'), a) : 'Победила A';
  document.getElementById('btnB').textContent =
    named ? 'Победила ' + optionName(document.getElementById('modelB'), b) : 'Победила B';
}

function updatePairHint(a, b) {
  const el = document.getElementById('pairHint');
  if (!el) return;
  if (!a || !b || a === b) { el.textContent = ''; return; }
  const h = pairHints[[a, b].sort().join('|')];
  if (!h) { el.textContent = 'Личные встречи: не встречались'; return; }
  const winsA = (a <= b) ? h.x : h.y;
  const winsB = (b <= a) ? h.x : h.y;
  el.textContent = 'Личные встречи: ' + h.g + ' · счёт по победам ' + winsA + ':' + winsB +
    ' · ничьи: ' + (h.g - h.x - h.y);
}

function validate() {
  const a = document.getElementById('modelA').value;
  const b = document.getElementById('modelB').value;
  const t = document.getElementById('taskField').value.trim();
  const ok = a && b && a !== b && t;
  document.getElementById('btnA').disabled = !ok;
  document.getElementById('btnB').disabled = !ok;
  document.getElementById('btnDraw').disabled = !ok;
  updateOutcomeLabels(a, b);
  updatePairHint(a, b);
}

function swapModels() {
  const selA = document.getElementById('modelA');
  const selB = document.getElementById('modelB');
  const tmp = selA.value;
  selA.value = selB.value;
  selB.value = tmp;
  validate();
}

function usePair(a, b, task) {
  document.getElementById('modelA').value = a;
  document.getElementById('modelB').value = b;
  document.getElementById('taskField').value = task;
  validate();
  // Спека блока рекомендаций: кнопка подставляет пару и прокручивает к форме
  document.getElementById('modelA').scrollIntoView({ block: 'center', behavior: 'smooth' });
}

function cycleRecommendation() {
  const items = document.querySelectorAll('.rec-variant');
  if (items.length < 2) return;
  let current = 0;
  items.forEach((el, i) => { if (!el.hidden) current = i; });
  items[current].hidden = true;
  items[(current + 1) % items.length].hidden = false;
}

function writeMore() {
  const alert = document.querySelector('.alert-success');
  if (alert) alert.hidden = true;
  const b = document.getElementById('modelB');
  if (b) {
    const combo = b.closest('.combobox');
    const target = combo ? combo.querySelector('.combobox-input') : b;
    (target || b).focus();
    b.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
}

const modelAEl = document.getElementById('modelA');
if (modelAEl) {
  const combo = modelAEl.closest('.combobox');
  const target = combo ? combo.querySelector('.combobox-input') : modelAEl;
  if (target) target.focus();
  validate();
}
</script>
{% endif %}
{% endblock %}
"""


# ─── HTML: History page ─────────────────────────────────────────────

HISTORY_TEMPLATE = """{% extends "shell.html" %}
{% from "_tag_filter.html" import filter_panel, filter_hidden with context %}
{% from "_verdict_row.html" import verdict_row with context %}
{% from "_pagination.html" import pagination %}
{% block title %}История — {{ history_found_label }} — ELO Benchmark{% endblock %}
{% block content %}
  <div class="header">
    <h1>История ELO</h1>
  </div>

  {% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

  <div class="controls">
    <div class="stats">
      Всего записей: {{ history_total }}{% if include_voided or only_voided %} · аннулированных: {{ history_voided }}{% endif %}{% if history_search_active %} · найдено: {{ history_found }}{% endif %}{% if filter_view == 'highlight' %} · подсвечено: {{ history_hits }}{% elif model %} · Фильтр: {{ model_name }}{% endif %}
    </div>
    {% if not read_only() %}
    <div class="export-links" aria-label="Экспорт выборки">
      <a class="btn btn-secondary btn-sm" href="{{ history_export_urls.csv }}">Скачать CSV</a>
      <a class="btn btn-secondary btn-sm" href="{{ history_export_urls.json }}">Скачать JSON</a>
    </div>
    {% endif %}
    {% call filter_panel() %}
      <span class="filter-label">Модель</span>
      <select name="model" id="model"{% if not read_only() %} data-combobox data-label="Модель"{% endif %} onchange="this.form.submit()">
        {% for m in models_dropdown %}
        <option value="{{ m.id }}" data-agent="{{ m.agent }}" {% if m.selected %}selected{% endif %}>{{ m.name }}{% if m.archived %} (неактивна){% endif %}</option>
        {% endfor %}
      </select>
      {% if not read_only() %}
      <span class="filter-label">Таск</span>
      <select name="task" id="historyTask" onchange="this.form.submit()">
        <option value="">— все таски —</option>
        {% for t in history_tasks %}
        <option value="{{ t.id }}" {% if t.selected %}selected{% endif %}>{{ t.id }}</option>
        {% endfor %}
      </select>
      <span class="filter-label">Даты</span>
      <input type="date" name="from" value="{{ history_from }}" aria-label="Начало периода" onchange="this.form.submit()">
      <span class="filter-dash" aria-hidden="true">—</span>
      <input type="date" name="to" value="{{ history_to }}" aria-label="Конец периода" onchange="this.form.submit()">
      <span class="filter-presets" role="group" aria-label="Пресеты периода">
        <a class="filter-preset{% if history_preset_active == '7' %} is-active{% endif %}" href="{{ history_preset_urls['7'] }}">7 дней</a>
        <a class="filter-preset{% if history_preset_active == '30' %} is-active{% endif %}" href="{{ history_preset_urls['30'] }}">30 дней</a>
        <a class="filter-preset{% if history_preset_active == 'all' %} is-active{% endif %}" href="{{ history_preset_urls['all'] }}">всё</a>
      </span>
      <span class="filter-label">Исход</span>
      <div class="segmented" role="radiogroup" aria-label="Исход">
        <label><input type="radio" name="outcome" value="" {% if not history_outcome %}checked{% endif %} onchange="this.form.submit()"><span>Все</span></label>
        <label><input type="radio" name="outcome" value="a" {% if history_outcome == 'a' %}checked{% endif %} onchange="this.form.submit()"><span>Победила A</span></label>
        <label><input type="radio" name="outcome" value="b" {% if history_outcome == 'b' %}checked{% endif %} onchange="this.form.submit()"><span>Победила B</span></label>
        <label><input type="radio" name="outcome" value="draw" {% if history_outcome == 'draw' %}checked{% endif %} onchange="this.form.submit()"><span>Ничья</span></label>
      </div>
      <span class="filter-label">Пара</span>
      <input type="text" name="pair" value="{{ history_pair }}" class="filter-pair" placeholder="id или имя" aria-label="Поиск по паре моделей" onchange="this.form.submit()">
      {% endif %}
      <label class="chip">
        <input type="checkbox" name="include_inactive" value="1" {% if include_inactive %}checked{% endif %} onchange="this.form.submit()">
        <span>Включать неактивные</span>
      </label>
      <label class="chip">
        <input type="checkbox" name="include_voided" value="1" {% if include_voided %}checked{% endif %} onchange="this.form.submit()">
        <span>Показывать аннулированные</span>
      </label>
      {% if not read_only() %}
      <label class="chip">
        <input type="checkbox" name="only_voided" value="1" {% if only_voided %}checked{% endif %} onchange="this.form.submit()">
        <span>Только аннулированные</span>
      </label>
      {% endif %}
    {% endcall %}
  </div>

  <div class="card" id="history-list">
    <h2 class="hidden">История</h2>
    {% if history %}
    {% for item in history %}
    {{ verdict_row(item, True, ('filter-hit' if item.hit else 'filter-miss') if (filter_view == 'highlight' and history_hits) else '', void_next) }}
    {% endfor %}
    {% if filter_view == 'highlight' and not history_hits %}
    <div class="hint">Ничего не подсвечено — ни одна запись не проходит выбранные условия.</div>
    {% endif %}
    {% if history_pages > 1 %}
    <div class="history-pagination">
      {{ pagination(history_page, history_pages, history_items, history_page_url) }}
      {% if not read_only() %}
      <form method="GET" action="/history" class="page-jump">
        {{ filter_hidden() }}
        {% for h in history_hidden_fields %}<input type="hidden" name="{{ h.name }}" value="{{ h.value }}">{% endfor %}
        <label class="page-jump-label" for="historyPageInput">Страница</label>
        <input class="page-jump-input" type="number" id="historyPageInput" name="page" min="1" max="{{ history_pages }}" value="{{ history_page }}" inputmode="numeric">
        <button type="submit" class="btn btn-secondary btn-sm">Перейти</button>
        <a class="page-last" href="{{ history_page_url(history_pages) }}">в конец</a>
      </form>
      {% endif %}
    </div>
    {% endif %}
    {% else %}
    <div class="empty-state">
      {% if history_search_active and history_total %}
      По выбранным условиям записей не найдено.
      {% else %}
      Нет истории
      {% endif %}
    </div>
    {% endif %}
  </div>
{% endblock %}
"""


# ─── HTML: Model page ─────────────────────────────────────────────

MODEL_TEMPLATE = """{% extends "shell.html" %}
{% block title %}{{ detail.name }} — ELO Benchmark{% endblock %}
{% block content %}
  <div class="detail-header">
    <span class="detail-title">
      <h1>{{ detail.name }}</h1>
      {% if detail_caption %}<span class="model-caption">{{ detail_caption }}</span>{% endif %}
    </span>
    <span class="detail-elo">{{ detail.elo }}</span>
    {% if detail.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>{% endif %}
    {% if read_only() %}<span class="btn btn-secondary" aria-disabled="true">Изменить</span>{% else %}<a href="/edit/{{ detail.id }}" class="btn btn-secondary">Изменить</a>{% endif %}
  </div>

  {% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-value">{{ detail.elo }}</div><div class="stat-label">ELO</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.games }}</div><div class="stat-label">Матчей</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.wins }}</div><div class="stat-label">Побед</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.losses }}</div><div class="stat-label">Поражений</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.draws }}</div><div class="stat-label">Ничьих</div></div>
    <div class="stat-card"><div class="stat-value">{{ detail.winrate }}</div><div class="stat-label">Винрейт</div></div>
  </div>

  <div class="profile-grid">
    <div class="card" id="profile-rank">
      <h2>Место в рейтинге</h2>
      {% if rank %}
      <div class="profile-rank-row">
        <span class="profile-rank">Место {{ rank }} из {{ pool_size }}</span>
        {% if trend.arrow %}<span class="trend {{ trend.css }}" title="{{ trend.title }}"><span class="trend-arrow">{{ trend.arrow }}</span><span class="trend-num">{{ trend.num }}</span></span>{% endif %}
        {% if trend.title and not trend.arrow %}<span class="hint">{{ trend.title }}</span>{% endif %}
      </div>
      {% else %}
      <div class="hint">Вне активного рейтинга</div>
      {% endif %}
    </div>

    <div class="card" id="profile-last-match">
      <h2>Последний матч</h2>
      {% if detail.last_match %}
      <div class="last-match-row">
        <a href="/model/{{ detail.last_match.opp_id }}" class="edit-link">{{ detail.last_match.opp_name }}</a>
        <span class="last-match-date">{{ detail.last_match.date_str }}</span>
        <span class="last-match-outcome">{{ detail.last_match.outcome }}</span>
        <span class="{{ detail.last_match.delta_class }}">{{ detail.last_match.delta_str }}</span>
        <a href="{{ detail.last_match.url }}" class="edit-link" title="Постоянная ссылка на вердикт">вердикт №{{ detail.last_match.seq }}</a>
      </div>
      {% else %}
      <div class="empty-state">Матчей нет</div>
      {% endif %}
    </div>
  </div>

  <div class="card">
    <h2>Динамика ELO</h2>
    {{ chart_svg|safe }}
  </div>

  <div class="card" id="h2h">
    <h2>Личные встречи</h2>
    {% if not read_only() %}
    <form method="GET" action="/model/{{ detail.id }}" class="h2h-controls">
      <input class="h2h-input" type="search" name="h2h_q" value="{{ h2h_q }}" placeholder="Поиск соперника по имени или id" aria-label="Поиск соперника">
      <input type="hidden" name="h2h_sort" value="{{ h2h_sort }}">
      <input type="hidden" name="h2h_dir" value="{{ h2h_dir }}">
      <button type="submit" class="btn btn-secondary btn-sm">Найти</button>
      {% if h2h_q %}<a href="{{ h2h_reset_url }}" class="edit-link">сбросить</a>{% endif %}
    </form>
    {% endif %}
    {% if h2h_rows %}
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Соперник</th>
            <th scope="col"{% if not read_only() and h2h_sort == 'games' %} aria-sort="{{ 'ascending' if h2h_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}Встреч{% else %}<a class="sort-link" href="{{ h2h_sort_url('games') }}" title="Сортировать по числу встреч">Встреч{% if not read_only() and h2h_sort == 'games' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if h2h_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
            <th scope="col"{% if not read_only() and h2h_sort == 'w' %} aria-sort="{{ 'ascending' if h2h_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}W{% else %}<a class="sort-link" href="{{ h2h_sort_url('w') }}" title="Сортировать по победам">W{% if not read_only() and h2h_sort == 'w' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if h2h_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
            <th scope="col"{% if not read_only() and h2h_sort == 'l' %} aria-sort="{{ 'ascending' if h2h_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}L{% else %}<a class="sort-link" href="{{ h2h_sort_url('l') }}" title="Сортировать по поражениям">L{% if not read_only() and h2h_sort == 'l' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if h2h_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
            <th scope="col"{% if not read_only() and h2h_sort == 'd' %} aria-sort="{{ 'ascending' if h2h_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}D{% else %}<a class="sort-link" href="{{ h2h_sort_url('d') }}" title="Сортировать по ничьим">D{% if not read_only() and h2h_sort == 'd' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if h2h_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
            <th scope="col"{% if not read_only() and h2h_sort == 'winrate' %} aria-sort="{{ 'ascending' if h2h_dir == 'asc' else 'descending' }}"{% endif %}>{% if read_only() %}Винрейт{% else %}<a class="sort-link" href="{{ h2h_sort_url('winrate') }}" title="Сортировать по винрейту">Винрейт{% if not read_only() and h2h_sort == 'winrate' %}<span class="sort-arrow" aria-hidden="true">{{ '▲' if h2h_dir == 'asc' else '▼' }}</span>{% endif %}</a>{% endif %}</th>
          </tr>
        </thead>
        <tbody>
          {% for r in h2h_rows %}
          <tr>
            <td><a href="/model/{{ r.id }}" class="edit-link">{{ r.name }}</a></td>
            <td>{{ r.games }}</td>
            <td class="wld w">{{ r.w }}</td>
            <td class="wld l">{{ r.l }}</td>
            <td class="wld d">{{ r.d }}</td>
            <td class="winrate">{{ r.winrate }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="empty-state">{% if h2h_q %}Никого не найдено. <a href="{{ h2h_reset_url }}" class="edit-link">Сбросить поиск</a>{% else %}Пока нет встреч{% endif %}</div>
    {% endif %}
  </div>

  <div class="card" id="history">
    <h2>История матчей</h2>
    {% if detail.history %}
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th scope="col">Соперник</th><th scope="col">Дата</th><th scope="col">Исход</th><th scope="col">ELO до</th><th scope="col">Δ</th><th scope="col">ELO после</th></tr>
        </thead>
        <tbody>
          {% for h in detail.history %}
          <tr>
            <td><a href="/model/{{ h.opp_id }}" class="edit-link">{{ h.opp_name }}</a></td>
            <td><a href="{{ h.url }}" class="edit-link" title="Постоянная ссылка на вердикт №{{ h.seq }}">{{ h.date_str }}</a></td>
            <td>{{ h.outcome }}</td>
            <td>{{ h.before }}</td>
            <td class="{{ h.delta_class }}">{{ h.delta_str }}</td>
            <td>{{ h.after }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="empty-state">Пока нет матчей</div>
    {% endif %}
    <div class="card-actions">
      <a class="btn btn-secondary btn-sm" href="{{ url_for('history_page', model=detail.id) }}">Показать в истории</a>
    </div>
  </div>

  {% if task_coverage %}
  <div class="card" id="task-coverage">
    <h2>Покрытие по таскам</h2>
    <ul class="coverage-list">
      {% for t in task_coverage %}
      <li><a href="/task/{{ t.task }}" class="edit-link">{{ t.task }}</a> — {{ t.games if t.games else "—" }}</li>
      {% endfor %}
    </ul>
  </div>
  {% endif %}

  {% if detail.meta %}
  <div class="card" id="model-meta">
    <h2>Метаданные</h2>
    <dl class="meta-list">
      {% for field in detail.meta %}
      <div class="meta-row"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div>
      {% endfor %}
    </dl>
  </div>
  {% endif %}
{% endblock %}
"""


# ─── HTML: Task page ──────────────────────────────────────────────

TASK_TEMPLATE = """{% extends "shell.html" %}
{% from "_verdict_row.html" import verdict_row with context %}
{% from "_pagination.html" import pagination %}
{% block title %}{{ task.id }} — {{ task.title or 'Задача' }} — ELO Benchmark{% endblock %}
{% block content %}
  <div class="detail-header">
    <span class="detail-title">
      <h1>{{ task.title or task.id }}</h1>
      <span class="model-caption">{{ task.id }}</span>
      {% if task.project %}<span class="model-caption">Проект: {{ task.project }}</span>{% endif %}
      {% if task.baseline_commit %}<span class="model-caption">baseline: {{ task.baseline_commit }}</span>{% endif %}
    </span>
    {% if task_active %}<span class="status-pill status-active">активна</span>{% else %}<span class="status-pill status-archived">неактивна</span>{% endif %}
    {% if task_current %}<span class="status-pill status-active">текущая</span>{% endif %}
    {% if read_only() %}
    <span class="btn btn-primary" aria-disabled="true">Записать вердикт по таску</span>
    {% else %}
    <a class="btn btn-primary" href="{{ url_for('leaderboard', task=task.id) }}">Записать вердикт по таску</a>
    {% endif %}
    <a class="btn btn-secondary" href="{{ url_for('history_page', task=task.id) }}">История таска</a>
    {% if not read_only() %}<a class="btn btn-secondary" href="{{ task_md_url }}">task.md</a>{% endif %}
  </div>

  {% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

  <div class="stats-grid">
    <div class="stat-card"><div class="stat-value">{{ progress.verdicts }}</div><div class="stat-label">Вердиктов</div></div>
    <div class="stat-card"><div class="stat-value">{{ progress.filled }} из {{ progress.total }}</div><div class="stat-label">Пар закрыто</div></div>
    <div class="stat-card"><div class="stat-value">{{ progress.models }}</div><div class="stat-label">Моделей</div></div>
    <div class="stat-card"><div class="stat-value">{{ progress.voided }}</div><div class="stat-label">Аннулировано</div></div>
  </div>

  <div class="card" id="task-history">
    <h2>Вердикты таска</h2>
    {% if history %}
    {% for item in history %}
    {{ verdict_row(item, False, '', void_next) }}
    {% endfor %}
    {% if history_pages > 1 %}
    <div class="history-pagination">
      {{ pagination(history_page, history_pages, history_items, history_page_url) }}
      {% if not read_only() %}
      <form method="GET" action="{{ url_for('task_page', task_id=task.id) }}" class="page-jump">
        <label class="page-jump-label" for="taskPageInput">Страница</label>
        <input class="page-jump-input" type="number" id="taskPageInput" name="page" min="1" max="{{ history_pages }}" value="{{ history_page }}" inputmode="numeric">
        <button type="submit" class="btn btn-secondary btn-sm">Перейти</button>
        <a class="page-last" href="{{ history_page_url(history_pages) }}">в конец</a>
      </form>
      {% endif %}
    </div>
    {% endif %}
    {% else %}
    <div class="empty-state">У таска пока нет вердиктов</div>
    {% endif %}
  </div>
{% endblock %}
"""


# ─── HTML: Stats page ─────────────────────────────────────────────

STATS_TEMPLATE = """{% extends "shell.html" %}
{% from "_tag_filter.html" import filter_panel with context %}
{% block title %}Аналитика — ELO Benchmark{% endblock %}
{% block content %}
  <div class="header">
    <h1>Аналитика</h1>
  </div>

  <div class="card" id="rating-intervals">
    <h2>Интервалы рейтинга</h2>
    <div class="hint">Точка — Elo модели, полоса — интервал ±400/√игр; модели с перекрывающимися интервалами объединены в группы «место не определено». Блок не зависит от фильтров страницы.</div>
    {% if intervals_svg %}
    {{ intervals_svg|safe }}
    {% else %}
    <div class="empty-state">Нет активных моделей.</div>
    {% endif %}
  </div>

  <div class="card" id="elo-distribution">
    <h2>Распределение Elo</h2>
    <div class="stats">{{ summary }}</div>
    {% call filter_panel() %}
      <span class="filter-label">Показывать</span>
      <div class="segmented" role="radiogroup" aria-label="Показывать">
        <label><input type="radio" name="filter" value="active" {% if stats_filter == 'active' %}checked{% endif %} onchange="this.form.submit()"><span>Активные</span></label>
        <label><input type="radio" name="filter" value="all" {% if stats_filter == 'all' %}checked{% endif %} onchange="this.form.submit()"><span>Все</span></label>
      </div>
    {% endcall %}
    {% if pool_count %}
    {{ chart_svg|safe }}
    {% else %}
    <div class="empty-state">Под выбранный фильтр не попала ни одна модель.</div>
    {% endif %}
  </div>

  <div class="card" id="elo-dynamics">
    <h2>Динамика ELO</h2>
    <div class="hint">Матчи выбранных моделей в порядке записи; пунктирная линия — старт 1200.</div>
    {% if not read_only() %}
    <form method="GET" action="/stats" class="lines-form">
      {% for h in lines_hidden %}<input type="hidden" name="{{ h.name }}" value="{{ h.value }}">{% endfor %}
      <div class="lines-row">
        <span class="filter-label">Модели</span>
        <div class="lines-checkboxes">
          {% for m in lines_models %}
          <label class="lines-check"><input type="checkbox" name="lines" value="{{ m.id }}"{% if m.checked %} checked{% endif %}><span>{{ m.name }}</span></label>
          {% endfor %}
        </div>
      </div>
      <div class="lines-row">
        <span class="filter-label">Период</span>
        <div class="segmented" role="radiogroup" aria-label="Период">
          <label><input type="radio" name="period" value="30" {% if period_value == '30' %}checked{% endif %}><span>30 дней</span></label>
          <label><input type="radio" name="period" value="90" {% if period_value == '90' %}checked{% endif %}><span>90 дней</span></label>
          <label><input type="radio" name="period" value="all" {% if period_value == 'all' %}checked{% endif %}><span>Всё</span></label>
        </div>
      </div>
      <div class="card-actions">
        <button type="submit" class="btn btn-primary btn-sm">Показать</button>
        <span class="lines-presets">Пресеты: <a href="{{ top5_url }}" class="edit-link">Топ-5</a> · <a href="{{ top10_url }}" class="edit-link">Топ-10</a></span>
      </div>
    </form>
    {% endif %}
    {% if dynamics_svg %}
    {{ dynamics_svg|safe }}
    {% else %}
    <div class="empty-state">Нет матчей выбранных моделей в периоде.</div>
    {% endif %}
    {% if line_legend %}
    <div class="line-legend">
      {% for item in line_legend %}
      <span class="line-legend-item{% if not item.points %} line-legend-empty{% endif %}">
        <span class="line-swatch" style="background: {{ item.color }}"></span>
        <a href="/model/{{ item.id }}" class="line-legend-name">{{ item.name }}</a>
        <span class="line-legend-elo">ELO {{ item.elo }}</span>
        {% if not item.points %}<span class="line-legend-note">нет матчей в периоде</span>{% endif %}
      </span>
      {% endfor %}
    </div>
    {% endif %}
  </div>

  <div class="card" id="activity-by-day">
    <h2>Активность по дням</h2>
    {% if activity_svg %}
    <div class="stats">{{ activity_summary }}</div>
    {{ activity_svg|safe }}
    {% else %}
    <div class="empty-state">В истории нет вердиктов.</div>
    {% endif %}
  </div>

  <div class="card" id="pair-matrix">
    <h2>Матрица пар</h2>
    <div class="hint">Число применённых встреч пары по активному пулу; точка в углу ячейки — рематч.{% if not read_only() %} Клик по ячейке открывает историю пары.{% endif %}</div>
    {% if matrix_svg %}
    <div class="matrix-wrap">{{ matrix_svg|safe }}</div>
    {% else %}
    <div class="empty-state">Нет применённых встреч.</div>
    {% endif %}
  </div>

  <div class="card" id="agents-providers">
    <h2>Агенты и компании</h2>
    {% if agents_summary or providers_summary %}
    <h3 class="card-subtitle">Агенты</h3>
    <div class="table-wrap">
      <table class="analytics-table">
        <thead>
          <tr><th scope="col">Агент</th><th scope="col">Моделей</th><th scope="col">Медиана Elo</th><th scope="col">Среднее Elo</th><th scope="col">Игр</th><th scope="col">Винрейт</th></tr>
        </thead>
        <tbody>
          {% for g in agents_summary %}
          <tr><td>{{ g.name }}</td><td>{{ g.models }}</td><td>{{ g.median }}</td><td>{{ g.mean }}</td><td>{{ g.games }}</td><td>{{ g.winrate }}</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    <h3 class="card-subtitle">Компании</h3>
    <div class="table-wrap">
      <table class="analytics-table">
        <thead>
          <tr><th scope="col">Компания</th><th scope="col">Моделей</th><th scope="col">Медиана Elo</th><th scope="col">Среднее Elo</th><th scope="col">Игр</th><th scope="col">Винрейт</th></tr>
        </thead>
        <tbody>
          {% for g in providers_summary %}
          <tr><td>{{ g.name }}</td><td>{{ g.models }}</td><td>{{ g.median }}</td><td>{{ g.mean }}</td><td>{{ g.games }}</td><td>{{ g.winrate }}</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="empty-state">Нет активных моделей.</div>
    {% endif %}
  </div>

  <div class="card" id="delta-leaders">
    <h2>Взлёты и падения</h2>
    {% if delta_7.growth or delta_7.fall or delta_30.growth or delta_30.fall or stale %}
    <div class="hint">Сумма изменений рейтинга по личным матчам моделей активного пула за окно.</div>
    <div class="delta-grid">
      {% for window in (delta_7, delta_30) %}
      <div class="delta-col">
        <h3 class="card-subtitle">{{ window.days }} дней</h3>
        <h4 class="delta-label">Рост</h4>
        {% if window.growth %}
        <ul class="delta-list">
          {% for row in window.growth %}
          <li>
            <a href="/model/{{ row.id }}" class="delta-name">{{ row.name }}</a>
            <span class="delta-sum delta-up">+{{ row.sum }}</span>
            <span class="delta-games">игр: {{ row.games }}</span>
          </li>
          {% endfor %}
        </ul>
        {% else %}
        <div class="delta-empty">Нет роста</div>
        {% endif %}
        <h4 class="delta-label">Падение</h4>
        {% if window.fall %}
        <ul class="delta-list">
          {% for row in window.fall %}
          <li>
            <a href="/model/{{ row.id }}" class="delta-name">{{ row.name }}</a>
            <span class="delta-sum delta-down">{{ row.sum }}</span>
            <span class="delta-games">игр: {{ row.games }}</span>
          </li>
          {% endfor %}
        </ul>
        {% else %}
        <div class="delta-empty">Нет падения</div>
        {% endif %}
      </div>
      {% endfor %}
    </div>
    {% if stale %}
    <h3 class="card-subtitle">Остывшие</h3>
    <div class="hint">Без личных матчей в последних 30 вердиктах.</div>
    <ul class="delta-list delta-stale">
      {% for row in stale %}
      <li>
        <a href="/model/{{ row.id }}" class="delta-name">{{ row.name }}</a>
        <span class="delta-games">игр: {{ row.games }}</span>
      </li>
      {% endfor %}
    </ul>
    {% endif %}
    {% else %}
    <div class="empty-state">Нет применённых матчей.</div>
    {% endif %}
  </div>

  <div class="card" id="opposition">
    <h2>Сила оппозиции</h2>
    <div class="hint">Средний рейтинг соперников по матчам модели (перед матчем) и победы над моделями текущего топ-10.</div>
    {% if opposition %}
    <div class="table-wrap">
      <table class="analytics-table">
        <thead>
          <tr><th scope="col">Модель</th><th scope="col">Elo</th><th scope="col">Средний Elo соперников</th><th scope="col">Победы над топ-10</th><th scope="col">Игр</th></tr>
        </thead>
        <tbody>
          {% for row in opposition %}
          <tr>
            <td><a href="/model/{{ row.id }}">{{ row.name }}</a></td>
            <td>{{ row.elo }}</td>
            <td>{{ row.opp_avg if row.opp_avg is not none else "—" }}</td>
            <td>{{ row.upsets if row.upsets is not none else "—" }}</td>
            <td>{{ row.games }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% else %}
    <div class="empty-state">Нет активных моделей.</div>
    {% endif %}
  </div>

  <div class="card" id="outcomes">
    <h2>Исходы</h2>
    {% if shares.total %}
    <div class="outcome-rows">
      {% for row in shares.rows %}
      <div class="outcome-row">
        <span class="outcome-label">{{ row.label }}</span>
        <span class="outcome-bar"><span class="outcome-fill outcome-key-{{ row.key }}" style="width: {{ row.pct }}%"></span></span>
        <span class="outcome-n">{{ row.n }}</span>
        <span class="outcome-pct">{{ row.pct }}%</span>
      </div>
      {% endfor %}
    </div>
    <div class="stats">всего применённых вердиктов: {{ shares.total }}</div>
    {% if shares.by_task %}
    <h3 class="card-subtitle">По активным задачам</h3>
    <ul class="outcome-tasks">
      {% for group in shares.by_task %}
      <li>
        <a href="/task/{{ group.task }}" class="outcome-task-id">{{ group.task }}</a>
        <span class="outcome-task-total">вердиктов: {{ group.total }}</span>
        {% for row in group.rows %}<span class="outcome-task-row">{{ row.label }} · {{ row.pct }}% ({{ row.n }})</span>{% endfor %}
      </li>
      {% endfor %}
    </ul>
    {% endif %}
    {% else %}
    <div class="empty-state">Нет применённых вердиктов.</div>
    {% endif %}
  </div>
{% endblock %}
"""


# ─── HTML: Add model page ───────────────────────────────────────────

ADD_TEMPLATE = """{% extends "shell.html" %}
{% from "_tag_filter.html" import filter_panel with context %}
{% block title %}Добавить модель — ELO Benchmark{% endblock %}
{% block content %}
<div class="header">
  <h1>Добавить модель</h1>
</div>

{% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/add_model">
    <div class="form-group">
      <label>Название модели</label>
      <input type="text" name="name" required placeholder="Например: GPT-4o" autofocus>
    </div>
    <div class="form-group">
      <label>Агент</label>
      <select name="agent">
        <option value="">— не указано —</option>
        {% for a in agent_options %}<option value="{{ a }}">{{ a }}</option>{% endfor %}
      </select>
    </div>
    <div class="form-group">
      <label>Компания</label>
      <select name="provider">
        <option value="">— не указано —</option>
        {% for p in provider_options %}<option value="{{ p }}">{{ p }}</option>{% endfor %}
      </select>
    </div>
    <div class="hint">
      Значения — из справочника; новое значение можно добавить в разделе
      <a href="/settings#lookups" target="_blank" rel="noopener">Справочники</a> (откроется в новой вкладке).
    </div>
    <div class="hint">Стартовый ELO: {{ default_elo }}</div>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">Добавить</button>
    </div>
  </form>
</div>

{% call filter_panel() %}{% endcall %}

{% if models_list %}
<div class="card">
  <h2>Уже в списке ({{ models_list|length }})</h2>
  <table>
    <thead><tr><th scope="col">Модель</th><th scope="col">Статус</th><th scope="col">ELO</th><th scope="col">Игр</th><th scope="col"></th></tr></thead>
    <tbody>
      {% for m in models_list %}
      <tr class="{{ 'archived' if m.status == 'archived' }}{% if filter_view == 'highlight' and highlight_hits %} {{ 'filter-hit' if m.hit else 'filter-miss' }}{% endif %}">
        <td>
          <a href="/edit/{{ m.id }}" class="edit-link">{{ m.name }}</a>
          {% if m.caption %}<div class="model-caption">{{ m.caption }}</div>{% endif %}
        </td>
        <td>
          {% if m.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>
          {% else %}<span class="status-pill status-active">активна</span>{% endif %}
        </td>
        <td>{{ m.elo }}</td>
        <td>{{ m.games }}</td>
        <td><a href="/edit/{{ m.id }}" class="btn btn-secondary btn-sm">Изменить</a></td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% if filter_view == 'highlight' and not highlight_hits %}
  <div class="hint">Ничего не подсвечено — ни одна модель не проходит выбранные условия.</div>
  {% endif %}
</div>
{% elif filter_active %}
<div class="card">
  <div class="empty-state">Под выбранный фильтр не попала ни одна модель.</div>
</div>
{% endif %}
{% endblock %}
"""


# ─── HTML: Edit model page ──────────────────────────────────────────

EDIT_TEMPLATE = """{% extends "shell.html" %}
{% block title %}Редактировать модель — ELO Benchmark{% endblock %}
{% block content %}
<div class="header">
  <h1>Редактировать модель</h1>
</div>

{% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/edit/{{ model.id }}" data-status="{{ model.status }}" data-name="{{ model.name }}" onsubmit="return confirmModelStatus(this)">
    <div class="form-group">
      <label>ID модели</label>
      <input type="text" value="{{ model.id }}" disabled>
      <div class="hint">ID менять нельзя — он стабилен для истории.</div>
    </div>
    <div class="form-group">
      <label>Название модели</label>
      <input type="text" name="name" value="{{ model.name }}" required autofocus>
    </div>
    <div class="form-group">
      <label>Агент</label>
      <select name="agent">
        <option value="">— не указано —</option>
        {% for a in agent_options %}
        <option value="{{ a }}" {% if model.agent == a %}selected{% endif %}>{{ a }}</option>
        {% endfor %}
        {% if model.agent and model.agent not in agent_options %}
        <option value="{{ model.agent }}" selected>{{ model.agent }} (вне справочника)</option>
        {% endif %}
      </select>
    </div>
    <div class="form-group">
      <label>Компания</label>
      <select name="provider">
        <option value="">— не указано —</option>
        {% for p in provider_options %}
        <option value="{{ p }}" {% if model.provider == p %}selected{% endif %}>{{ p }}</option>
        {% endfor %}
        {% if model.provider and model.provider not in provider_options %}
        <option value="{{ model.provider }}" selected>{{ model.provider }} (вне справочника)</option>
        {% endif %}
      </select>
    </div>
    <div class="hint">
      Значения — из справочника; добавить новые можно в разделе
      <a href="/settings#lookups" target="_blank" rel="noopener">Справочники</a> (откроется в новой вкладке).
      Текущее значение вне справочника сохраняется как есть.
    </div>
    <div class="form-group">
      <label>Статус активности</label>
      <select name="status">
        <option value="active" {% if model.status == 'active' %}selected{% endif %}>Активна</option>
        <option value="archived" {% if model.status == 'archived' %}selected{% endif %}>Неактивна (архив)</option>
      </select>
    </div>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">Сохранить</button>
      <a href="/model/{{ model.id }}" class="btn btn-secondary ms-2">Отмена</a>
    </div>
  </form>
</div>

<script>
// Подтверждение только для перехода «не архив → архив»: обычное
// сохранение и разархивация диалога не вызывают.
function confirmModelStatus(form) {
  const sel = form.querySelector('select[name="status"]');
  if (form.dataset.status !== 'archived' && sel && sel.value === 'archived') {
    return confirm('Перевести модель «' + form.dataset.name + '» в архив (неактивна)?');
  }
  return true;
}
</script>
{% endblock %}
"""


# ─── HTML: Add task page ────────────────────────────────────────────

ADD_TASK_TEMPLATE = """{% extends "shell.html" %}
{% block title %}Добавить таску — ELO Benchmark{% endblock %}
{% block content %}
<div class="header">
  <h1>Добавить таску</h1>
</div>

{% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/add_task">
    <div class="form-group">
      <label>Название</label>
      <input type="text" name="title" required placeholder="Например: Bug Hunt — NewModule" autofocus>
    </div>
    <div class="form-group">
      <label>Slug (опц.)</label>
      <input type="text" name="slug" placeholder="new-module">
      <div class="hint">Если пусто, slug сгенерируется из названия.</div>
    </div>
    <div class="form-group">
      <label>Проект (опц.)</label>
      <input type="text" name="project" placeholder="Например: VoiceMind">
    </div>
    <div class="form-group">
      <label>Baseline commit (опц.)</label>
      <input type="text" name="baseline" placeholder="abc1234...">
    </div>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">Добавить</button>
      <a href="/settings" class="btn btn-secondary ms-2">Отмена</a>
    </div>
  </form>
</div>
{% endblock %}
"""


# ─── HTML: Edit task page ───────────────────────────────────────────

EDIT_TASK_TEMPLATE = """{% extends "shell.html" %}
{% block title %}Редактировать таску — ELO Benchmark{% endblock %}
{% block content %}
<div class="header">
  <h1>Редактировать таску {{ task.id }}</h1>
</div>

{% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

<div class="card add-form">
  <form method="POST" action="/edit_task/{{ task.id }}">
    <input type="hidden" name="id" value="{{ task.id }}">
    <div class="hint hint--mb">
      Обязательны только <strong>название</strong> и <strong>описание</strong>.
      Проект и baseline_commit — опциональны, нужны skills прогонов.
    </div>
    <div class="form-group">
      <label>Название</label>
      <input type="text" name="title" value="{{ task.title }}" required autofocus placeholder="Bug Hunt — NewModule">
    </div>
    <div class="form-group">
      <label>Описание и критерии (Markdown)</label>
      <textarea name="body" rows="12">{{ task.body }}</textarea>
    </div>
    <details class="card card--plain">
      <summary>Дополнительно: проект и baseline</summary>
      <div class="form-group form-group--mt">
        <label>Проект (опц.)</label>
        <input type="text" name="project" value="{{ task.project }}" placeholder="Например: VoiceMind">
      </div>
      <div class="form-group">
        <label>Baseline commit (опц.)</label>
        <input type="text" name="baseline" value="{{ task.baseline_commit }}" placeholder="abc1234...">
      </div>
    </details>
    <div class="form-actions">
      <button type="submit" class="btn btn-primary">Сохранить</button>
      <a href="/settings" class="btn btn-secondary ms-2">Отмена</a>
    </div>
  </form>
</div>
{% endblock %}
"""


# ─── HTML: Settings page ────────────────────────────────────────────

SETTINGS_TEMPLATE = """{% extends "shell.html" %}
{% from "_tag_filter.html" import filter_panel, filter_hidden with context %}
{% from "_pagination.html" import pagination %}
{% block title %}Настройки — ELO Benchmark{% endblock %}
{% block content %}
  <div class="header">
    <h1>Настройки</h1>
  </div>

  {% if error %}<div class="alert alert-error" role="alert">{{ error }}</div>{% endif %}
  {% if success %}<div class="alert alert-success" role="status">{{ success }}</div>{% endif %}

  <nav class="settings-nav" aria-label="Разделы настроек">
    <a href="#models">Модели</a>
    <a href="#tasks">Таски</a>
    <a href="#answer-coverage">Ответы</a>
    <a href="#recommendation-queue">Очередь</a>
    <a href="#lookups">Справочники</a>
    <a href="#about">О консоли</a>
  </nav>

  <div class="stats stats-summary">
    Моделей: <a href="#models">{{ active_models_total }} из {{ models_total }}</a> · Вердиктов: <a href="/history">{{ matchups_count }}</a>{% if rematch_count %} (рематчей: {{ rematch_count }}){% endif %} · Пары: <a href="#recommendation-queue">{{ queue_filled }}/{{ queue_total }}</a> · Таски: <a href="#tasks">{{ active_tasks_count }} из {{ known_tasks_count }}</a>
  </div>

  <div class="settings-grid">
    <div class="card" id="models">
      <h2>Модели</h2>
      {% call filter_panel() %}
        {% if answer_active_tasks %}
        <span class="filter-label">Показывать</span>
        <div class="segmented" role="radiogroup" aria-label="Показывать">
          <label><input type="radio" name="answer_filter" value="active" {% if answer_filter == 'active' %}checked{% endif %} onchange="this.form.submit()"><span>Активные</span></label>
          <label><input type="radio" name="answer_filter" value="all" {% if answer_filter == 'all' %}checked{% endif %} onchange="this.form.submit()"><span>Все</span></label>
          <label><input type="radio" name="answer_filter" value="inactive" {% if answer_filter == 'inactive' %}checked{% endif %} onchange="this.form.submit()"><span>Неактивные</span></label>
        </div>
        <label class="chip">
          <input type="checkbox" name="only_debts" value="1" {% if only_debts %}checked{% endif %} onchange="this.form.submit()">
          <span>Только долги</span>
        </label>
        {% endif %}
      {% endcall %}
      <div class="model-groups">
        <div class="model-row">
          <span>Всего в реестре</span>
          <span>{{ models_total }}</span>
        </div>
        <details class="model-row">
          <summary>
            <span class="mg-label">Активных</span>
            <span>{{ models_active }}</span>
          </summary>
          <ul class="model-list">
            {% for m in models_active_list %}
            <li>
              <span class="model-list-name">
                <a href="/model/{{ m.id }}" class="edit-link">{{ m.name }}</a>
                {% if m.caption %}<span class="model-caption">{{ m.caption }}</span>{% endif %}
              </span>
              <span>{{ m.elo }}</span>
            </li>
            {% else %}
            <li class="model-empty">Нет активных моделей</li>
            {% endfor %}
          </ul>
        </details>
        <details class="model-row">
          <summary>
            <span class="mg-label">Неактивных (архив)</span>
            <span>{{ models_archived }}</span>
          </summary>
          <ul class="model-list">
            {% for m in models_archived_list %}
            <li>
              <span class="model-list-name">
                <a href="/model/{{ m.id }}" class="edit-link">{{ m.name }}</a>
                {% if m.caption %}<span class="model-caption">{{ m.caption }}</span>{% endif %}
              </span>
              <span>{{ m.elo }}</span>
            </li>
            {% else %}
            <li class="model-empty">Нет неактивных моделей</li>
            {% endfor %}
          </ul>
        </details>
      </div>
      <div class="hint">
        Название обязательно; id генерируется автоматически. Агент и компания
        выбираются из справочника (ссылка «Справочники» внизу страницы или
        на странице добавления). Изменить или архивировать — по ссылке
        «Изменить» в списке моделей.
      </div>
      <div class="card-actions">
        {% if read_only() %}<span class="btn btn-primary" aria-disabled="true">+ Добавить модель</span>{% else %}<a href="/add" class="btn btn-primary">+ Добавить модель</a>{% endif %}
      </div>
    </div>

    <div class="card" id="tasks">
      <h2>Таски</h2>
      {% if tasks_list %}
      <div class="table-wrap">
      <table class="tasks-table">
        <thead>
          <tr><th scope="col" class="id-col">ID</th><th scope="col" class="title-col">Название</th><th scope="col" class="actions-col">Действия</th></tr>
        </thead>
        <tbody>
          {% for t in tasks_list %}
          <tr class="{{ 'archived' if not t.active }}">
            <td class="id-col"><a href="{{ url_for('task_page', task_id=t.id) }}" class="edit-link">{{ t.id }}</a></td>
            <td class="title-col">
              {{ t.title }}
              {% if t.active %}<span class="status-pill status-active">активна</span>
              {% else %}<span class="status-pill status-archived">неактивна</span>{% endif %}
              {% if t.current %}<span class="status-pill status-active">текущая</span>{% endif %}
            </td>
            <td class="actions-col">
              {% if read_only() %}<fieldset disabled class="form-inline">{% else %}<form method="POST" action="/task/{{ t.id }}/current" class="form-inline">{% endif %}
                {{ filter_hidden() }}
                <button type="submit" class="btn btn-secondary btn-sm" {% if not t.active or t.current %}disabled{% endif %}>Текущая</button>
              {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
              {% if read_only() %}<fieldset disabled class="form-inline ms-1">{% else %}<form method="POST" action="/task/{{ t.id }}/toggle" class="form-inline ms-1">{% endif %}
                {{ filter_hidden() }}
                <button type="submit" class="btn btn-secondary btn-sm">
                  {% if t.active %}Деактивировать{% else %}Активировать{% endif %}
                </button>
              {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
              {% if read_only() %}<span class="btn btn-secondary btn-sm ms-1" aria-disabled="true">Изменить</span>{% else %}<a href="/edit_task/{{ t.id }}" class="btn btn-secondary btn-sm ms-1">Изменить</a>{% endif %}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      </div>
      {% else %}
      <div class="empty-state">Тасков пока нет — добавьте первую.</div>
      {% endif %}
      <div class="hint">
        Активные таски участвуют в прогрессе и доступны в форме вердикта.
        Текущая таска подставляется по умолчанию. «Удаление» = деактивация,
        файлы задачи остаются.
      </div>
      <div class="card-actions">
        {% if read_only() %}<span class="btn btn-primary" aria-disabled="true">+ Добавить таску</span>{% else %}<a href="/add_task" class="btn btn-primary">+ Добавить таску</a>{% endif %}
      </div>
    </div>
  </div>

  <div class="card" id="answer-coverage">
    <h2>Наличие ответов</h2>
    {% if answer_has_active %}
    <div class="stats">ответы: закрыто {{ answer_filled }} из {{ answer_total }} · осталось {{ answer_remaining }}</div>
    {% else %}
    <div class="stats">ответы: — (нет активных моделей или активных тасков)</div>
    {% endif %}
    <div class="hint">
      Тексты ответов хранятся вне проекта; здесь только флаги «ответ получен».
      Новая модель и новый таск по умолчанию считаются долгом.
      Флаги моделей вне фильтра и неактивных тасков сохраняются без изменений.
    </div>
    {% if answer_active_tasks %}
    {% if answer_rows %}
    {% if read_only() %}<fieldset disabled id="flagsForm">{% else %}<form method="POST" action="/answer_flags" id="flagsForm">{% endif %}
      {{ filter_hidden() }}
      <div class="table-wrap">
        <table class="flags-table">
          <thead>
            <tr>
              <th scope="col">Модель</th>
              {% for t in answer_active_tasks %}
              <th scope="col">{{ t }}<br>
                <button type="button" class="btn btn-secondary col-btn" onclick="colSet('{{ t }}', true)">все</button>
                <button type="button" class="btn btn-secondary col-btn" onclick="colSet('{{ t }}', false)">сброс</button>
              </th>
              {% endfor %}
              <th scope="col">Долг</th>
              <th scope="col"></th>
            </tr>
          </thead>
          <tbody>
            {% for r in answer_rows %}
            <tr class="{{ 'archived' if r.status == 'archived' }}{% if filter_view == 'highlight' and answer_hits %} {{ 'filter-hit' if r.hit else 'filter-miss' }}{% endif %}">
              <td class="model-cell">
                <div>{{ r.name }}{% if r.status == 'archived' %}<span class="status-pill status-archived">неактивна</span>{% endif %}</div>
                {% if r.caption %}<div class="model-caption">{{ r.caption }}</div>{% endif %}
              </td>
              {% for t in answer_active_tasks %}
              <td><input type="checkbox" name="flag" value="{{ r.id }}||{{ t }}" data-col="{{ t }}" {% if r.cells[t] %}checked{% endif %}></td>
              {% endfor %}
              <td>{{ r.debt }}</td>
              <td><button type="button" class="btn btn-secondary col-btn" onclick="rowToggle(this)">строка</button></td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% if filter_view == 'highlight' and not answer_hits %}
      <div class="hint">Ничего не подсвечено — ни одна модель не проходит выбранные условия.</div>
      {% endif %}
      {% if answer_inactive_tasks %}
      <div class="hint">Неактивные таски скрыты: {{ answer_inactive_tasks|join(', ') }}. Их флаги сохраняются без изменений.</div>
      {% endif %}
      <div class="card-actions">
        <button type="submit" class="btn btn-primary">Сохранить</button>
      </div>
    {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
    {% else %}
    <div class="empty-state">
      {% if filter_active %}
      Под выбранный фильтр не попала ни одна модель.
      {% elif only_debts %}
      Долгов нет.
      {% elif answer_filter == 'inactive' %}
      Нет неактивных моделей для учёта.
      {% elif answer_filter == 'all' %}
      Нет моделей для учёта.
      {% else %}
      Нет активных моделей для учёта.
      {% endif %}
    </div>
    {% endif %}
    {% else %}
    <div class="empty-state">Нет активных моделей или активных тасков для учёта.</div>
    {% endif %}
  </div>

  <div class="card" id="recommendation-queue">
    <h2>Очередь рекомендаций</h2>
    {% if queue_has_coverage %}
    <div class="stats"{% if queue_breakdown_legend %} title="{{ queue_breakdown_legend }}"{% endif %}>открытых: {{ queue_remaining }}{% if queue_breakdown_str %} ({{ queue_breakdown_str }}){% endif %}{% if queue_rematch_count %} · рематчей: {{ queue_rematch_count }}{% endif %} · закрыто {{ queue_filled }} из {{ queue_total }}</div>
    {% if queue_breakdown_legend %}
    <div class="hint">в скобках — остаток по таскам: {{ queue_breakdown_legend }}</div>
    {% endif %}
    {% else %}
    <div class="stats">очередь: — (нет активных моделей, активных тасков или видимых ячеек)</div>
    {% endif %}
    <div class="hint">
      Порядок совпадает с кнопкой «Прогнать» на главной. Пары без обоих ответов скрыты.
    </div>
    {% if queue %}
    <div class="table-wrap queue-wrap">
      <table class="queue-table">
        <thead>
          <tr><th scope="col">№</th><th scope="col">Пара</th><th scope="col">Таск</th><th scope="col">Обоснование</th></tr>
        </thead>
        <tbody>
          {% for q in queue %}
          <tr>
            <td class="rank">{{ queue_page_start + loop.index }}</td>
            <td class="model-cell"><a href="/model/{{ q.model_a }}" class="edit-link">{{ q.name_a }}</a> vs <a href="/model/{{ q.model_b }}" class="edit-link">{{ q.name_b }}</a></td>
            <td>{% if q.recommended_task %}<a href="{{ url_for('task_page', task_id=q.recommended_task) }}" class="edit-link">{{ q.recommended_task }}</a>{% else %}—{% endif %}</td>
            <td class="queue-reason">{{ q.reason }}</td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
    {% if queue_pages > 1 %}
    {{ pagination(queue_page, queue_pages, queue_items, queue_page_url) }}
    {% endif %}
    {% else %}
    <div class="empty-state">{% if rematch %}Открытых пар нет. Ниже — матч для доп. точности (рематч).{% else %}Открытых пар нет.{% endif %}</div>
    {% if rematch %}
    {% set r = rematch[0] %}
    <div class="table-wrap">
      <table class="queue-table">
        <tbody>
          <tr>
            <td class="rank">1</td>
            <td class="model-cell"><a href="/model/{{ r.model_a }}" class="edit-link">{{ r.name_a }}</a> vs <a href="/model/{{ r.model_b }}" class="edit-link">{{ r.name_b }}</a></td>
            <td>{{ r.recommended_task if r.recommended_task else "—" }} <span class="rec-rematch">рематч</span></td>
            <td class="queue-reason">{{ r.reason }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    {% endif %}
    {% endif %}
  </div>

  <div class="card" id="lookups">
    <h2>Справочники</h2>
    <div class="hint">
      Допустимые значения полей «Агент» и «Компания» модели — порядок как в
      data/lookups.yaml. Переименование обновляет все модели реестра и
      пересчитывает index; удалить можно только значение, не используемое
      ни одной моделью. Значения реестра вне справочника помечены
      «вне справочника» — их можно внести одной кнопкой.
    </div>
    {% for section in lookup_sections %}
    <div class="lookup-section">
      <h3>{{ section.title }}</h3>
      {% if read_only() %}<fieldset disabled class="lookups-add">{% else %}<form method="POST" action="/lookups/add" class="lookups-add">{% endif %}
        <input type="hidden" name="kind" value="{{ section.kind }}">
        <input type="text" name="value" class="lookup-input" placeholder="Новое значение" aria-label="Новое значение — {{ section.title|lower }}">
        <button type="submit" class="btn btn-primary btn-sm">Добавить</button>
      {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
      <div class="table-wrap">
        <table class="lookups-table">
          <thead>
            <tr><th scope="col">Значение</th><th scope="col">Моделей</th><th scope="col" class="actions-col">Действия</th></tr>
          </thead>
          <tbody>
            {% for row in section.rows %}
            <tr>
              <td>
                {{ row.value }}
                {% if row.external %}<span class="status-pill status-archived">вне справочника</span>{% endif %}
              </td>
              <td>{{ row.count }}</td>
              <td class="actions-col">
                {% if row.external %}
                {% if read_only() %}<fieldset disabled class="form-inline">{% else %}<form method="POST" action="/lookups/promote" class="form-inline">{% endif %}
                  <input type="hidden" name="kind" value="{{ section.kind }}">
                  <input type="hidden" name="value" value="{{ row.value }}">
                  <button type="submit" class="btn btn-secondary btn-sm">внести в справочник</button>
                {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
                {% else %}
                {% if read_only() %}<fieldset disabled class="form-inline">{% else %}<form method="POST" action="/lookups/rename" class="form-inline">{% endif %}
                  <input type="hidden" name="kind" value="{{ section.kind }}">
                  <input type="hidden" name="old" value="{{ row.value }}">
                  <input type="text" name="new" value="{{ row.value }}" class="lookup-input" aria-label="Новое значение для «{{ row.value }}»">
                  <button type="submit" class="btn btn-secondary btn-sm">Переименовать</button>
                {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
                {% if read_only() %}<fieldset disabled class="form-inline ms-1">{% else %}<form method="POST" action="/lookups/delete" class="form-inline ms-1" data-value="{{ row.value }}" onsubmit="return confirmDelete(this)">{% endif %}
                  <input type="hidden" name="kind" value="{{ section.kind }}">
                  <input type="hidden" name="value" value="{{ row.value }}">
                  <button type="submit" class="btn btn-secondary btn-sm"{% if row.count %} disabled title="Значение используют {{ row.count }} моделей"{% endif %}>{% if row.count %}используется у {{ row.count }}{% else %}Удалить{% endif %}</button>
                {% if read_only() %}</fieldset>{% else %}</form>{% endif %}
                {% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    {% endfor %}
  </div>

  <div class="card" id="about">
    <h2>О консоли</h2>
    <dl class="about-meta">
      <div class="about-row"><dt>Версия</dt><dd>{{ app_version() or "—" }}</dd></div>
      <div class="about-row"><dt>Сборка</dt><dd>{{ app_build_time() or "—" }}</dd></div>
    </dl>
    <div class="hint">
      Версия — последний выпущенный релиз (git-тег). Сборка — дата и время
      коммита, из которого запущена консоль (по минскому времени); при запуске
      из архива без git — время файла версии проекта.
    </div>
  </div>

<script>
// Матрица наличия ответов: bulk по строке («строка») и столбцу («все»/«сброс»).
function rowToggle(btn) {
  const boxes = btn.closest('tr').querySelectorAll('input[name="flag"]');
  const target = Array.from(boxes).some((cb) => !cb.checked);
  boxes.forEach((cb) => { cb.checked = target; });
}
function colSet(task, val) {
  document.querySelectorAll('#flagsForm input[name="flag"][data-col="' + task + '"]').forEach((cb) => {
    cb.checked = val;
  });
}
// Значение передаётся через data-value, а не подстановкой в JS-строку.
function confirmDelete(form) {
  return confirm('Удалить значение «' + form.dataset.value + '» из справочника?');
}
</script>
{% endblock %}
"""


# ─── Прекомпиляция шаблонов ─────────────────────────────────────────
# Jinja парсит и компилирует шаблон один раз при импорте, рендер
# переиспользует скомпилированный код (прежний путь пересобирал
# шаблон на каждый запрос, ~21 мс).

INDEX_TEMPLATE = app.jinja_env.from_string(INDEX_TEMPLATE)
HISTORY_TEMPLATE = app.jinja_env.from_string(HISTORY_TEMPLATE)
MODEL_TEMPLATE = app.jinja_env.from_string(MODEL_TEMPLATE)
TASK_TEMPLATE = app.jinja_env.from_string(TASK_TEMPLATE)
STATS_TEMPLATE = app.jinja_env.from_string(STATS_TEMPLATE)
ADD_TEMPLATE = app.jinja_env.from_string(ADD_TEMPLATE)
EDIT_TEMPLATE = app.jinja_env.from_string(EDIT_TEMPLATE)
ADD_TASK_TEMPLATE = app.jinja_env.from_string(ADD_TASK_TEMPLATE)
EDIT_TASK_TEMPLATE = app.jinja_env.from_string(EDIT_TASK_TEMPLATE)
SETTINGS_TEMPLATE = app.jinja_env.from_string(SETTINGS_TEMPLATE)


# ─── Routes ─────────────────────────────────────────────────────────


@app.route("/history")
def history_page():
    index_data = ensure_index()

    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")

    model_id = request.args.get("model", "").strip()
    include_inactive = request.args.get("include_inactive", "") == "1"
    include_voided = request.args.get("include_voided", "") == "1"
    search = parse_history_search(models)
    history_pair_value = search["pair"] or (
        ":".join(search["pair_ids"]) if search["pair_ids"] else ""
    )

    filter_ctx = filter_panel_context(
        models,
        action="/history",
        reset_url=url_for("history_page"),
        reset_extra=(
            bool(model_id) or include_inactive or include_voided
            or search["active"] or search["only_voided"]
        ),
    )
    agent_sel, provider_sel = filter_ctx["filter_agent_sel"], filter_ctx["filter_provider_sel"]
    filter_view = filter_ctx["filter_view"]
    highlight = filter_view == "highlight"
    # Параметры для ссылок пагинации: все фильтры страницы и настройки отображения как были
    history_params = {
        "model": model_id or None,
        "include_inactive": "1" if include_inactive else None,
        "include_voided": "1" if include_voided else None,
        "task": search["task"] or None,
        "from": search["from"] or None,
        "to": search["to"] or None,
        "outcome": search["outcome"] or None,
        "pair": history_pair_value or None,
        "only_voided": "1" if search["only_voided"] else None,
        "agents": filter_ctx["filter_agents_csv"] or None,
        "providers": filter_ctx["filter_providers_csv"] or None,
        "view": filter_view if filter_view != "hide" else None,
        "chips": filter_ctx["filter_chips"] if filter_ctx["filter_chips"] != "alpha" else None,
    }

    # Выпадайка: активные + выбранная модель, плюс archived при чекбоксе;
    # состав дополнительно сужается блоком «Фильтр».
    all_models = sorted(models.values(), key=lambda m: m.get("name", "").lower())
    dropdown = [{"id": "", "name": "Все", "agent": "", "archived": False, "selected": not model_id}]
    for m in all_models:
        mid = m.get("id", "")
        status = m.get("status", "active")
        archived = status == "archived"
        if not include_inactive and archived and mid != model_id:
            continue
        if mid != model_id and not model_passes_tags(m, agent_sel, provider_sel):
            continue
        dropdown.append({
            "id": mid,
            "name": m.get("name", mid),
            "agent": str(m.get("agent") or "").strip(),
            "archived": archived,
            "selected": mid == model_id,
        })

    name_map = {mid: info.get("name", mid) for mid, info in models.items()}
    caption_map = {mid: format_model_caption(info) for mid, info in models.items()}
    feed = build_history_feed(
        index_data, models, search,
        model_id=model_id, agent_sel=agent_sel, provider_sel=provider_sel,
        highlight=highlight, include_voided=include_voided,
    )
    records = feed["records"]

    # Постоянная ссылка `?v=<seq>`: редирект на страницу с записью; если в
    # текущем составе её нет — ищем по полной ленте (с аннулированными) и
    # ведём туда, сбросив поисковые фильтры; неизвестный seq — предупреждение.
    page_size = 20
    v_value = (request.args.get("v") or "").strip()
    v_error = ""
    if v_value.isdigit() and v_value != "0":
        position = next(
            (i for i, h in enumerate(records) if str(h.get("seq") or "") == v_value),
            None,
        )
        if position is not None:
            page = position // page_size + 1
            target = (
                url_for("history_page", page=page, **history_params) if page > 1
                else url_for("history_page", **history_params)
            )
            return redirect(target + f"#v-{v_value}")
        full_feed = merge_history_feed(
            index_data.get("elo_history", []),
            index_data.get("voided_history", []),
        )
        position = next(
            (i for i, h in enumerate(full_feed) if str(h.get("seq") or "") == v_value),
            None,
        )
        if position is not None:
            page = position // page_size + 1
            target = (
                url_for("history_page", page=page, include_voided="1") if page > 1
                else url_for("history_page", include_voided="1")
            )
            return redirect(target + f"#v-{v_value}")
        v_error = f"Вердикт v={v_value} не найден — список записей не изменён."

    total_history = feed["total"]
    history_found = feed["found"]
    # Заголовок вкладки: число записей текущей выборки с правильной формой
    # слова («История — 602 записи — ELO Benchmark»).
    history_found_label = (
        f"{history_found} {plural_ru(history_found, 'запись', 'записи', 'записей')}"
    )
    history_voided = feed["voided"]
    history_hits = feed["hits"]
    history_pages = (history_found + page_size - 1) // page_size if history_found else 1
    history_page_num = request.args.get("page", "1").strip()
    try:
        history_page_num = int(history_page_num)
    except ValueError:
        history_page_num = 1
    history_page_num = max(1, min(history_page_num, history_pages))
    start = (history_page_num - 1) * page_size
    end = start + page_size
    history = format_elo_history(records[start:end], name_map, caption_map,
                                 highlight=highlight)

    model_name = name_map.get(model_id, model_id) if model_id else ""

    def _history_page_url(page: int) -> str:
        """Ссылка на страницу истории с сохранением фильтров и настроек отображения."""
        return url_for("history_page", page=page, **history_params)

    # Пресеты диапазона дат: «7 дней» / «30 дней» / «всё» — ссылки с
    # сохранением прочих фильтров; активный пресет вычисляется по from/to.
    today_iso = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    month_ago = (date.today() - timedelta(days=30)).isoformat()

    def _preset_url(from_value: str, to_value: str) -> str:
        params = {
            key: value for key, value in history_params.items()
            if key not in ("from", "to") and value
        }
        if from_value:
            params["from"] = from_value
        if to_value:
            params["to"] = to_value
        return url_for("history_page", **params)

    history_preset_urls = {
        "7": _preset_url(week_ago, today_iso),
        "30": _preset_url(month_ago, today_iso),
        "all": _preset_url("", ""),
    }
    history_preset_active = ""
    if search["from"] == week_ago and search["to"] == today_iso:
        history_preset_active = "7"
    elif search["from"] == month_ago and search["to"] == today_iso:
        history_preset_active = "30"
    elif not search["from"] and not search["to"]:
        history_preset_active = "all"

    # Скрытые параметры формы «страница №»: всё состояние фильтров страницы
    # (agents/providers/view/chips добавляет filter_hidden()).
    history_hidden_fields = [
        {"name": name, "value": value}
        for name, value in (
            ("model", model_id),
            ("include_inactive", "1" if include_inactive else ""),
            ("include_voided", "1" if include_voided else ""),
            ("task", search["task"]),
            ("from", search["from"]),
            ("to", search["to"]),
            ("outcome", search["outcome"]),
            ("pair", history_pair_value),
            ("only_voided", "1" if search["only_voided"] else ""),
        ) if value
    ]

    # Выпадайка «Таск»: таски записей ленты (применённые + аннулированные),
    # плюс выбранный из URL, даже если записей по нему нет.
    task_ids = {history_task_id(h) for h in index_data.get("elo_history", [])}
    task_ids |= {history_task_id(h) for h in index_data.get("voided_history", [])}
    if search["task"]:
        task_ids.add(search["task"])
    history_tasks = [
        {"id": t, "selected": t == search["task"]} for t in sorted(task_ids) if t
    ]

    return HISTORY_TEMPLATE.render(
        history=history,
        history_page=history_page_num,
        history_pages=history_pages,
        history_total=total_history,
        history_found=history_found,
        history_found_label=history_found_label,
        history_search_active=search["active"],
        history_voided=history_voided,
        history_hits=history_hits,
        history_items=pagination_items(history_page_num, history_pages),
        history_page_url=_history_page_url,
        history_hidden_fields=history_hidden_fields,
        history_tasks=history_tasks,
        history_task=search["task"],
        history_from=search["from"],
        history_to=search["to"],
        history_outcome=search["outcome"],
        history_pair=history_pair_value,
        only_voided=search["only_voided"],
        history_preset_urls=history_preset_urls,
        history_preset_active=history_preset_active,
        history_export_urls=history_export_urls(history_params),
        models_dropdown=dropdown,
        model=model_id,
        model_name=model_name,
        include_inactive=include_inactive,
        include_voided=include_voided,
        void_next=_self_url(exclude=("success", "error")),
        error=request.args.get("error", "") or v_error,
        success=request.args.get("success", ""),
        **filter_ctx,
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": "История"},
        ],
    )


@app.route("/task/<task_id>")
def task_page(task_id: str):
    index_data = ensure_index()
    if find_task_dir(task_id) is None and task_id not in memo_known_tasks():
        abort(404)
    task = get_task_info(task_id) or {
        "id": task_id, "title": "", "project": "", "baseline_commit": "",
    }

    models = index_data.get("models", {})
    name_map = {mid: info.get("name", mid) for mid, info in models.items()}
    caption_map = {mid: format_model_caption(info) for mid, info in models.items()}
    records = [
        h for h in merge_history_feed(
            index_data.get("elo_history", []),
            index_data.get("voided_history", []),
        )
        if history_task_id(h) == task_id
    ]

    page_size = 20
    pages = max(1, (len(records) + page_size - 1) // page_size)
    try:
        page = int(request.args.get("page", "1").strip() or "1")
    except ValueError:
        page = 1
    page = max(1, min(page, pages))
    start = (page - 1) * page_size
    history = format_elo_history(
        records[start:start + page_size], name_map, caption_map,
    )

    def _page_url(p: int) -> str:
        if p > 1:
            return url_for("task_page", task_id=task_id, page=p)
        return url_for("task_page", task_id=task_id)

    settings = load_settings()
    return TASK_TEMPLATE.render(
        task=task,
        task_active=is_task_active(settings, task_id),
        task_current=memo_current_task() == task_id,
        progress=get_task_progress(task_id),
        history=history,
        history_page=page,
        history_pages=pages,
        history_items=pagination_items(page, pages),
        history_page_url=_page_url,
        task_md_url=url_for("task_md", task_id=task_id),
        void_next=_self_url(exclude=("success", "error")),
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": "Настройки", "href": "/settings"},
            {"label": task_id},
        ],
    )


@app.route("/task/<task_id>/md")
def task_md(task_id: str):
    task_dir = find_task_dir(task_id)
    task_file = task_dir / "task.md" if task_dir else None
    if not task_file or not task_file.exists():
        abort(404)
    return Response(
        task_file.read_text(encoding="utf-8"),
        content_type="text/plain; charset=utf-8",
    )


@app.route("/model/<model_id>")
def model_page(model_id: str):
    index_data = ensure_index()
    registry = {m["id"]: m for m in memo_models() if m.get("id")}
    detail = get_model_detail(index_data, model_id, registry=registry)
    if detail is None:
        return (
            "<h1>404</h1><p>Модель не найдена</p>"
            '<p><a href="/">Назад к рейтингу</a></p>'
        ), 404

    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")

    # Место и тренд — по активному пулу (как в таблице рейтинга), отдельный
    # memo-ключ: пул профиля не зависит от фильтров главной.
    pool_rows = [
        {"id": mid, "elo": info.get("elo", DEFAULT_ELO)}
        for mid, info in models.items() if is_model_active(info)
    ]
    pool_rows.sort(key=lambda m: (-m["elo"], m["id"]))
    pool_ids = [m["id"] for m in pool_rows]
    current_elo = {m["id"]: m["elo"] for m in pool_rows}
    trends = data_cache.cached(
        "trends:profile",
        lambda: compute_rank_trends(
            index_data.get("elo_history", []), pool_ids, current_elo,
        ),
    )
    rank = pool_ids.index(model_id) + 1 if model_id in pool_ids else None
    trend = trends.get(model_id, {})

    # Покрытие по таскам: применённые матчи модели в каждом активном таске.
    task_games = memo_task_model_games()
    task_coverage = [
        {"task": tid, "games": task_games.get(tid, {}).get(model_id, 0)}
        for tid in memo_active_tasks()
    ]

    # «Личные встречи»: поиск по имени/id и сортировка по столбцам.
    h2h_q = request.args.get("h2h_q", "").strip()
    h2h_sort = request.args.get("h2h_sort", "games").strip().lower()
    if h2h_sort not in ("games", "w", "l", "d", "winrate"):
        h2h_sort = "games"
    h2h_dir = request.args.get("h2h_dir", "desc").strip().lower()
    if h2h_dir not in ("asc", "desc"):
        h2h_dir = "desc"

    h2h_rows = list(detail["h2h"])
    if h2h_q:
        needle = h2h_q.lower()
        h2h_rows = [
            r for r in h2h_rows
            if needle in r["name"].lower() or needle in r["id"].lower()
        ]

    def _h2h_value(row: dict):
        if h2h_sort == "winrate":
            return (row["w"] / row["games"]) if row["games"] else None
        return row.get(h2h_sort)

    sign = -1 if h2h_dir == "desc" else 1
    valued = [r for r in h2h_rows if _h2h_value(r) is not None]
    nones = [r for r in h2h_rows if _h2h_value(r) is None]
    valued.sort(key=lambda r: (sign * _h2h_value(r), r["name"].lower(), r["id"]))
    nones.sort(key=lambda r: (r["name"].lower(), r["id"]))
    h2h_rows = valued + nones

    def h2h_sort_url(key: str) -> str:
        """Ссылка заголовка: повторный клик по активному столбцу меняет порядок."""
        direction = "desc"
        if h2h_sort == key and h2h_dir == "desc":
            direction = "asc"
        args = {"h2h_sort": key, "h2h_dir": direction}
        if h2h_q:
            args["h2h_q"] = h2h_q
        return url_for("model_page", model_id=model_id, **args)

    h2h_reset_url = url_for(
        "model_page", model_id=model_id, h2h_sort=h2h_sort, h2h_dir=h2h_dir,
    )

    return MODEL_TEMPLATE.render(
        detail=detail,
        detail_caption=format_model_caption(detail),
        chart_svg=build_elo_svg(
            detail["points"],
            dates=(detail["date_first"], detail["date_last"])
            if detail["date_first"] and detail["date_last"] else None,
            links=detail.get("point_links"),
        ),
        rank=rank,
        pool_size=len(pool_ids),
        trend=trend,
        task_coverage=task_coverage,
        h2h_rows=h2h_rows,
        h2h_q=h2h_q,
        h2h_sort=h2h_sort,
        h2h_dir=h2h_dir,
        h2h_sort_url=h2h_sort_url,
        h2h_reset_url=h2h_reset_url,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": detail["name"]},
        ],
    )


@app.route("/stats")
def stats_page():
    index_data = ensure_index()

    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")

    stats_filter = request.args.get("filter", "active").strip().lower()
    if stats_filter not in ("active", "all"):
        stats_filter = "active"

    filter_ctx = filter_panel_context(
        models,
        action="/stats",
        reset_url=url_for("stats_page"),
        reset_extra=stats_filter != "active",
    )
    agent_sel, provider_sel = filter_ctx["filter_agent_sel"], filter_ctx["filter_provider_sel"]
    filter_view = filter_ctx["filter_view"]
    highlight = filter_view == "highlight"

    if highlight:
        # «Подсвечивать»: пул — весь реестр; статус и чипы — критерии подсветки.
        pool = list(models.values())
    elif stats_filter == "active":
        pool = [info for info in models.values() if is_model_active(info)]
    else:
        pool = list(models.values())
    if not highlight:
        pool = [info for info in pool if model_passes_tags(info, agent_sel, provider_sel)]

    entries = []
    for m in pool:
        entry = {
            "id": m.get("id", ""),
            "elo": m.get("elo", DEFAULT_ELO),
            "name": m.get("name", m.get("id", "")),
            "games": m.get("games", 0),
            "caption": format_model_caption(m),
        }
        if highlight:
            entry["hit"] = (
                (stats_filter == "all" or is_model_active(m))
                and model_passes_tags(m, agent_sel, provider_sel)
            )
        entries.append(entry)

    if entries:
        elos = sorted(e["elo"] for e in entries)
        n = len(elos)
        mean = sum(elos) / n
        below = sum(1 for v in elos if v < DEFAULT_ELO)
        summary = (
            f"моделей: {n} · ниже 1200: {below} · "
            f"выше/равно 1200: {n - below} · "
            f"среднее: {mean:.0f}"
        )
        if highlight:
            summary += f" · подсветчено: {sum(1 for e in entries if e['hit'])}"
    else:
        summary = "моделей: 0"

    # A1 «Интервалы рейтинга»: всегда по активному пулу, фильтры не влияют.
    active_rows = [
        {
            "id": mid,
            "name": info.get("name", mid),
            "elo": info.get("elo", DEFAULT_ELO),
            "games": info.get("games", 0),
            "caption": format_model_caption(info),
        }
        for mid, info in models.items()
        if is_model_active(info)
    ]
    intervals = interval_groups(active_rows)

    # A2 «Динамика ELO»: выбор из URL, иначе топ-5 активных; период 30/90/all.
    lines_raw = ",".join(request.args.getlist("lines"))
    selected = parse_lines_param(lines_raw, models) or default_line_ids(models)
    period = parse_period_param(request.args.get("period"))
    period_value = "all" if period is None else str(period)
    series_data = build_elo_series(
        index_data.get("elo_history", []), selected, period,
    )
    line_series = []
    line_legend = []
    for index, mid in enumerate(selected):
        info = models.get(mid, {})
        item = {
            "id": mid,
            "name": info.get("name", mid),
            "color": ELO_LINE_COLORS[index % len(ELO_LINE_COLORS)],
            "points": series_data["series"].get(mid, []),
        }
        line_series.append(item)
        line_legend.append({
            **item,
            "elo": info.get("elo", DEFAULT_ELO),
        })

    # A3 «Активность по дням»: дни от первого до последнего в истории.
    activity = activity_by_day(index_data.get("elo_history", []))
    activity_summary = ""
    if activity:
        activity_summary = (
            f"дней: {len(activity)} · "
            f"вердиктов: {sum(d['count'] for d in activity)} · "
            f"максимум: {max(d['count'] for d in activity)}"
        )

    # A4 «Матрица пар»: активный пул по ELO, встречи из memo pair_scan.
    active_ids = [row["id"] for row in intervals["rows"]]
    matrix = pair_matrix(
        active_ids,
        {key: st.get("games", 0) for key, st in get_pair_stats().items()},
    )
    model_names = {mid: info.get("name", mid) for mid, info in models.items()}

    # A5 «Агенты и компании»: сводки по активному пулу.
    active_models = {
        mid: info for mid, info in models.items() if is_model_active(info)
    }

    # A6 «Взлёты и падения»: окна 7 и 30 дней, «остывшие» — последние 30 вердиктов.
    elo_history = index_data.get("elo_history", [])
    delta_7 = delta_leaders(elo_history, active_models, 7)
    delta_30 = delta_leaders(elo_history, active_models, 30)
    stale = stale_models(elo_history, active_models)

    # A7 «Сила оппозиции»: активный пул в порядке рейтинга, апсеты против топ-10.
    opposition = opposition_strength(elo_history, active_ids, models)

    # A8 «Исходы»: разбивка по таскам только при двух и более активных.
    active_task_ids = memo_active_tasks()
    shares = winner_shares(
        elo_history, active_task_ids if len(active_task_ids) >= 2 else None,
    )

    selected_set = set(selected)

    def _stats_link(lines_ids: list[str], period_out: str) -> str:
        args: dict = {}
        for name in ("filter", "agents", "providers", "view", "chips"):
            values = request.args.getlist(name)
            if values:
                args[name] = values
        args["lines"] = ",".join(lines_ids)
        args["period"] = period_out
        return url_for("stats_page", **args)

    return STATS_TEMPLATE.render(
        summary=summary,
        stats_filter=stats_filter,
        pool_count=len(entries),
        chart_svg=build_elo_distribution_svg(entries, highlight=highlight),
        intervals_svg=build_rating_intervals_svg(intervals["rows"]),
        lines_models=[
            {
                "id": mid,
                "name": info.get("name", mid),
                "checked": mid in selected_set,
            }
            for mid, info in sorted(
                models.items(),
                key=lambda pair: (
                    -int(pair[1].get("elo", DEFAULT_ELO)), pair[0],
                ),
            )
            if is_model_active(info)
        ],
        lines_hidden=[{"name": "filter", "value": stats_filter}]
        + filter_ctx["filter_hidden_fields"],
        period_value=period_value,
        top5_url=_stats_link(default_line_ids(models, 5), period_value),
        top10_url=_stats_link(default_line_ids(models, 10), period_value),
        dynamics_svg=build_elo_multiline_svg(
            line_series, series_data["x_count"], series_data["dates"],
        ),
        line_legend=line_legend,
        activity_summary=activity_summary,
        activity_svg=build_activity_bars_svg(activity, links=not read_only()),
        matrix_svg=build_pair_matrix_svg(
            matrix, model_names, links=not read_only(),
        ),
        agents_summary=group_summary(active_models, "agent"),
        providers_summary=group_summary(active_models, "provider"),
        delta_7=delta_7,
        delta_30=delta_30,
        stale=stale,
        opposition=opposition,
        shares=shares,
        **filter_ctx,
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": "Аналитика"},
        ],
    )


@app.route("/")
def leaderboard():
    index_data = ensure_index()

    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")

    # Общие параметры страницы и экспорта: режим, чипы, поиск, сортировка
    state = rating_request_state(models)
    filter_mode = state["filter_mode"]
    query = state["query"]

    filter_ctx = filter_panel_context(
        models,
        action="/",
        reset_url=url_for("leaderboard"),
        reset_extra=filter_mode != "active" or bool(query),
    )
    agent_sel, provider_sel = state["agent_sel"], state["provider_sel"]
    filter_view = filter_ctx["filter_view"]
    highlight = state["highlight"]

    # Пул, места/медали/d5 и видимые строки — общий конвейер с экспортом
    # (rating_selection); сортировка по клику только переупорядочивает
    # вывод, места и медали не пересчитываются.
    selection = rating_selection(
        index_data, filter_mode, agent_sel, provider_sel, highlight, query,
    )
    models_sorted = selection["models_sorted"]
    models_visible = sort_rating_rows(
        selection["models_visible"], state["sort"], state["direction"],
    )
    highlight_hits = selection["highlight_hits"]

    # Для формы вердикта — только активные модели (id, имя, агент)
    active_models = {
        mid: info for mid, info in models.items() if is_model_active(info)
    }
    models_list = sorted(
        (
            (mid, info.get("name", mid), str(info.get("agent") or "").strip())
            for mid, info in active_models.items()
        ),
        key=lambda x: x[1].lower(),
    )

    # Настройки нужны раньше — для валидации предзаполнения.
    task_options = memo_active_tasks()
    current_task = memo_current_task()

    # Предзаполнение формы вердикта из query (?model_a=&model_b=&task=,
    # короткие алиасы ?a=&b=). Невалидные id/таск игнорируются.
    pre_a = (request.args.get("model_a") or request.args.get("a") or "").strip()
    pre_b = (request.args.get("model_b") or request.args.get("b") or "").strip()
    pre_task = (request.args.get("task") or "").strip()
    if pre_a not in active_models:
        pre_a = ""
    if pre_b not in active_models:
        pre_b = ""
    if pre_a and pre_a == pre_b:
        pre_a, pre_b = "", ""
    if pre_task not in task_options:
        pre_task = ""

    # Дата вердикта: валидная из URL, иначе сегодня; `today` — значение по умолчанию.
    today = date.today().isoformat()
    pre_date = (request.args.get("date") or "").strip()
    if pre_date:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", pre_date):
                raise ValueError
            datetime.strptime(pre_date, "%Y-%m-%d")
        except ValueError:
            pre_date = ""
    pre_date = pre_date or today

    # Идентификатор только что записанного вердикта — для действия «Отменить».
    saved_matchup_id = (request.args.get("matchup_id") or "").strip()
    if not re.fullmatch(r"T-\d{3,}/\d{3,}", saved_matchup_id):
        saved_matchup_id = ""
    # Рекомендации пар (+ строка-обоснование для отображения).
    # top-3: карточка показывает первый вариант, «Другая пара» листает
    # остальные без перезагрузки (карусель и URL-состояние запрещены).
    recommendations = data_cache.cached(
        "recommendations:3", lambda: get_recommendations(index_data, top_n=3)
    )
    for rec in recommendations:
        rec["reason"] = format_reason(rec)

    # Топ-3 активных по ELO — для медалей; архивные — для секции
    top_active = sorted(
        (i for i in models.values() if is_model_active(i)),
        key=lambda m: (-m.get("elo", DEFAULT_ELO), m.get("id", "")),
    )
    medals = {info["id"]: rank for rank, info in enumerate(top_active[:3], start=1)}
    show_medals = filter_mode != "inactive" or highlight
    archived_list = sorted(
        (info for info in models.values() if not is_model_active(info)),
        key=lambda m: m.get("elo", DEFAULT_ELO),
        reverse=True,
    )
    archived_list = [
        info for info in archived_list
        if model_passes_tags(info, agent_sel, provider_sel)
    ]
    for info in archived_list:
        info["caption"] = format_model_caption(info)

    # Тренды позиций d5 (пул детерминирован парой highlight/filter_mode)
    # проставлены rating_selection; здесь только представление.

    # Настройки: прогресс покрытия (memo; task_options/current_task уже выше)
    coverage = memo_coverage()
    coverage_pct = None
    coverage_done = False
    if coverage["percent"] is not None:
        coverage_done = coverage["filled"] >= coverage["total"]
        # Незавершённый прогресс не округляем до «100%» — показываем 99
        coverage_pct = 100 if coverage_done else min(99, round(coverage["percent"]))
    remaining = coverage["total"] - coverage["filled"]

    # Единая сводка: вердикты журнала и рематчи (memo по дайджесту)
    matchups_count = matchups_count_of(index_data)
    rematch_count = memo_rematch_count()

    return INDEX_TEMPLATE.render(
        models_sorted=models_sorted,
        models_visible=models_visible,
        models_count=len(models),
        filtered_count=len(models_visible),
        highlight_hits=highlight_hits,
        show_medals=show_medals,
        matchups_count=matchups_count,
        rematch_count=rematch_count,
        active_tasks_count=len(task_options),
        known_tasks_count=len(memo_known_tasks()),
        updated=index_data.get("updated", ""),
        models_list=models_list,
        recommendations=recommendations,
        medals=medals,
        medal_icons=["🥇", "🥈", "🥉"],
        archived_list=archived_list,
        current_task=current_task,
        pre_a=pre_a,
        pre_b=pre_b,
        pre_task=pre_task,
        pre_date=pre_date,
        today=today,
        saved_matchup_id=saved_matchup_id,
        void_next=_self_url(exclude=("success", "error", "matchup_id")),
        pair_hints_json=data_cache.cached("pair_hints_json", build_pair_hints_json),
        task_options=task_options,
        coverage=coverage,
        coverage_pct=coverage_pct,
        coverage_done=coverage_done,
        remaining=remaining,
        filter=filter_mode,
        **filter_ctx,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        search_query=query,
        **rating_sort_context(),
        export_rating_urls=rating_export_urls(),
        format_winrate=format_winrate,
        format_confidence=format_confidence,
    )


# ─── Экспорт выборок (change console-wave3-data-scale) ──────────────


@app.route("/export/rating.csv")
def export_rating_csv():
    return _rating_export("csv")


@app.route("/export/rating.json")
def export_rating_json():
    return _rating_export("json")


def _rating_export(fmt: str):
    """Экспорт текущей выборки рейтинга: фильтры, поиск и порядок строк —
    как в таблице страницы (общий конвейер rating_selection)."""
    index_data = ensure_index()
    models = index_data.get("models", {})
    state = rating_request_state(models)
    selection = rating_selection(
        index_data, state["filter_mode"], state["agent_sel"], state["provider_sel"],
        state["highlight"], state["query"],
    )
    rows = sort_rating_rows(
        selection["models_visible"], state["sort"], state["direction"],
    )
    data = [
        {
            "place": m.get("rank", ""),
            "id": m.get("id", ""),
            "name": m.get("name", ""),
            "provider": str(m.get("provider") or "").strip(),
            "agent": str(m.get("agent") or "").strip(),
            "elo": m.get("elo", DEFAULT_ELO),
            "confidence": format_confidence(m.get("games", 0)),
            "games": m.get("games", 0),
            "wins": m.get("wins", 0),
            "losses": m.get("losses", 0),
            "draws": m.get("draws", 0),
            "winrate": format_winrate(m.get("wins", 0), m.get("games", 0)),
        }
        for m in rows
    ]
    today = date.today().isoformat()
    if fmt == "csv":
        header = ["Место", "id", "Имя", "Компания", "Агент", "ELO", "±", "Игры",
                  "Победы", "Поражения", "Ничьи", "Винрейт, %"]
        return _attachment(
            f"rating-{today}.csv", "text/csv; charset=utf-8",
            _csv_text(header, [list(row.values()) for row in data]),
        )
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "filters": {
            "filter": state["filter_mode"],
            "agents": sorted(state["agent_sel"]),
            "providers": sorted(state["provider_sel"]),
            "q": state["query"],
        },
        "sort": state["sort"] or "rank",
        "dir": state["direction"] or "asc",
        "count": len(data),
        "rows": data,
    }
    return _attachment(
        f"rating-{today}.json", "application/json; charset=utf-8",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


@app.route("/export/history.csv")
def export_history_csv():
    return _history_export("csv")


@app.route("/export/history.json")
def export_history_json():
    return _history_export("json")


def _history_export(fmt: str):
    """Экспорт текущей выборки истории: поисковые фильтры и аннулированные —
    как в ленте страницы (общий конвейер build_history_feed)."""
    index_data = ensure_index()
    models = index_data.get("models", {})
    for mid, info in models.items():
        info.setdefault("id", mid)
        info.setdefault("status", "active")
    model_id = (request.args.get("model") or "").strip()
    include_voided = request.args.get("include_voided", "") == "1"
    search = parse_history_search(models)
    agents, _ = _tag_values(models, "agent")
    providers, _ = _tag_values(models, "provider")
    agent_sel = _parse_tag_tokens(_tag_query_csv(request.args, "agents"), agents)
    provider_sel = _parse_tag_tokens(_tag_query_csv(request.args, "providers"), providers)
    highlight = valid_filter_view(request.args.get("view")) == "highlight"
    feed = build_history_feed(
        index_data, models, search,
        model_id=model_id, agent_sel=agent_sel, provider_sel=provider_sel,
        highlight=highlight, include_voided=include_voided,
    )
    name_map = {mid: info.get("name", mid) for mid, info in models.items()}
    data = []
    for rec in feed["records"]:
        a_id = str(rec.get("model_a_id") or "")
        b_id = str(rec.get("model_b_id") or "")
        elo_a = rec.get("elo_a") or {}
        elo_b = rec.get("elo_b") or {}
        void = rec.get("void") or {}
        data.append({
            "seq": rec.get("seq", ""),
            "matchup": rec.get("matchup", ""),
            "task": history_task_id(rec),
            "date": str(rec.get("date") or ""),
            "recorded_at": str(rec.get("recorded_at") or ""),
            "model_a_id": a_id,
            "model_a_name": name_map.get(a_id, a_id),
            "model_b_id": b_id,
            "model_b_name": name_map.get(b_id, b_id),
            "winner": str(rec.get("winner") or ""),
            "elo_a_before": elo_a.get("before", DEFAULT_ELO),
            "elo_a_after": elo_a.get("after", DEFAULT_ELO),
            "delta_a": elo_a.get("delta", 0),
            "elo_b_before": elo_b.get("before", DEFAULT_ELO),
            "elo_b_after": elo_b.get("after", DEFAULT_ELO),
            "delta_b": elo_b.get("delta", 0),
            "voided": "1" if rec.get("voided") else "0",
            "void_date": str(void.get("date") or void.get("recorded_at") or ""),
            "void_reason": str(void.get("reason") or ""),
        })
    today = date.today().isoformat()
    if fmt == "csv":
        header = ["seq", "matchup", "task", "date", "recorded_at", "model_a_id",
                  "model_a_name", "model_b_id", "model_b_name", "winner",
                  "elo_a_before", "elo_a_after", "delta_a", "elo_b_before",
                  "elo_b_after", "delta_b", "voided", "void_date", "void_reason"]
        return _attachment(
            f"history-{today}.csv", "text/csv; charset=utf-8",
            _csv_text(header, [list(row.values()) for row in data]),
        )
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "filters": {
            "model": model_id,
            "include_voided": include_voided,
            "task": search["task"],
            "from": search["from"],
            "to": search["to"],
            "outcome": search["outcome"],
            "pair": search["pair"],
            "pair_ids": list(search["pair_ids"]) if search["pair_ids"] else [],
            "only_voided": search["only_voided"],
        },
        "count": len(data),
        "rows": data,
    }
    return _attachment(
        f"history-{today}.json", "application/json; charset=utf-8",
        json.dumps(payload, ensure_ascii=False, indent=2),
    )


@app.route("/add")
def add_page():
    index_data = ensure_index()
    models_data = index_data.get("models", {})

    # Модели «Уже в списке»: актуальный ELO из index.json, с подписями
    models_list = []
    for mid, info in models_data.items():
        models_list.append({
            "id": mid,
            "name": info.get("name", mid),
            "elo": info.get("elo", DEFAULT_ELO),
            "games": info.get("games", 0),
            "status": info.get("status", "active"),
            "agent": info.get("agent", ""),
            "provider": info.get("provider", ""),
            "caption": format_model_caption(info),
        })
    models_list.sort(key=lambda m: m["name"].lower())

    filter_ctx = filter_panel_context(
        models_data,
        action="/add",
        reset_url=url_for("add_page"),
    )
    agent_sel, provider_sel = filter_ctx["filter_agent_sel"], filter_ctx["filter_provider_sel"]
    filter_view = filter_ctx["filter_view"]
    highlight = filter_view == "highlight"
    if highlight:
        # «Подсвечивать»: список не сужается, отобранные строки помечаются.
        for m in models_list:
            m["hit"] = model_passes_tags(m, agent_sel, provider_sel)
        highlight_hits = sum(1 for m in models_list if m["hit"])
    else:
        models_list = [m for m in models_list if model_passes_tags(m, agent_sel, provider_sel)]
        highlight_hits = 0

    # Агент и компания — выпадающие списки только из справочника
    lookup_data = load_lookups()

    return ADD_TEMPLATE.render(
        models_list=models_list,
        highlight_hits=highlight_hits,
        agent_options=lookup_data["agents"],
        provider_options=lookup_data["providers"],
        default_elo=DEFAULT_ELO,
        **filter_ctx,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": "Настройки", "href": "/settings"},
            {"label": "Добавить модель"},
        ],
    )


@app.route("/add_model", methods=["POST"])
def add_model():
    name = request.form.get("name", "").strip()
    agent = request.form.get("agent", "").strip()
    provider = request.form.get("provider", "").strip()

    if not name:
        return redirect(url_for("add_page", error="Введите название модели"))

    models_path = MODELS_PATH
    if not models_path.exists():
        return redirect(url_for("add_page", error="models.yaml не найден"))

    # Агент и компания — только пустое значение или значение из справочника
    if agent and not has_value("agent", agent):
        return redirect(url_for(
            "add_page",
            error=f"Агент «{agent}» отсутствует в справочнике: добавьте значение в разделе «Справочники».",
        ))
    if provider and not has_value("provider", provider):
        return redirect(url_for(
            "add_page",
            error=f"Компания «{provider}» отсутствует в справочнике: добавьте значение в разделе «Справочники».",
        ))

    text = models_path.read_text(encoding="utf-8")
    models, preamble = parse_existing(text)

    existing_ids = [m["id"] for m in models]
    model_id = slugify(name, existing_ids)

    new_model = {
        "id": model_id,
        "name": name,
        "agent": agent,
        "provider": provider,
        "version": "",
        "released": "",
        "added": date.today().isoformat(),
        "status": "active",
        "notes": "",
    }
    models.append(new_model)
    models.sort(key=lambda m: m["id"])

    out = preamble.rstrip() + "\n\nmodels:\n"
    for m in models:
        out += format_model(m) + "\n"

    models_path.write_text(out, encoding="utf-8")

    index_data = generate_index()
    save_index(index_data)

    return redirect(url_for("add_page", success=f"Модель «{name}» добавлена. Стартовый ELO: {DEFAULT_ELO}"))


@app.route("/verdict", methods=["POST"])
def record_verdict_route():
    model_a = request.form.get("model_a", "").strip()
    model_b = request.form.get("model_b", "").strip()
    winner = request.form.get("winner", "").strip()
    task = request.form.get("task", "").strip()
    verdict_date = request.form.get("date", "").strip()

    if not model_a or not model_b or not winner:
        return redirect(url_for("leaderboard", error="Выберите обе модели и победителя"))

    if model_a == model_b:
        return redirect(url_for("leaderboard", error="Модели должны различаться"))

    if winner not in ("a", "b", "draw"):
        return redirect(url_for("leaderboard", error="Неверный победитель"))

    if not task:
        return redirect(url_for("leaderboard", error="Укажите таск"))

    try:
        result = record_verdict(
            task=task,
            model_a=model_a,
            model_b=model_b,
            winner=winner,
            verdict_date=verdict_date or None,
        )
    except ValueError as e:
        return redirect(url_for("leaderboard", error=str(e)))

    name_map = get_model_name_map()
    name_a = name_map.get(model_a, model_a)
    name_b = name_map.get(model_b, model_b)
    winner_label = {"a": name_a, "b": name_b, "draw": "Ничья"}[winner]

    # Контекст формы после записи: победитель — в поле A (при ничьей — прежняя A),
    # поле B очищается; таск и дата сохраняются; matchup_id — для «Отменить».
    keep_a = model_b if winner == "b" else model_a
    context = {"model_a": keep_a, "task": task, "matchup_id": result["matchup_id"]}
    if verdict_date:
        context["date"] = verdict_date

    return redirect(url_for(
        "leaderboard",
        success=f"Записано: {name_a} vs {name_b} → {winner_label}",
        **context,
    ))


@app.route("/verdict/void", methods=["POST"])
def void_verdict_route():
    matchup_id = request.form.get("matchup_id", "").strip()
    reason = request.form.get("reason", "").strip()
    next_path = request.form.get("next", "").strip()
    target = next_path if _is_local_path(next_path) else "/history"

    if not matchup_id:
        return _redirect_with_message(target, error="Не указан вердикт для аннулирования")

    if not reason:
        return _redirect_with_message(target, error="Укажите причину аннулирования")

    try:
        void_matchup(matchup_id, reason=reason)
    except ValueError as e:
        return _redirect_with_message(target, error=str(e))

    return _redirect_with_message(target, success=f"Вердикт {matchup_id} аннулирован")


@app.route("/settings")
def settings_page():
    settings = load_settings()
    current = memo_current_task()
    tasks_list = []
    for t in memo_known_tasks():
        info = get_task_info(t)
        if info:
            title = info.get("title", "")
            if not title and info.get("missing"):
                title = "(не заполнено — нажмите Изменить)"
        else:
            title = "(файл не найден)"
        tasks_list.append({
            "id": t,
            "title": title,
            "active": is_task_active(settings, t),
            "current": t == current,
        })
    index_data = ensure_index()
    models = index_data.get("models", {})

    # Фильтр строк матрицы: active / all / inactive (по умолчанию active);
    # only_debts — «только долги» (URL-параметр блока «Фильтр»).
    answer_filter = valid_answer_filter(request.args.get("answer_filter"))
    only_debts = request.args.get("only_debts", "").strip() == "1"
    hidden_fields = [{"name": "answer_filter", "value": answer_filter}]
    if only_debts:
        hidden_fields.append({"name": "only_debts", "value": "1"})
    filter_ctx = filter_panel_context(
        models,
        action="/settings",
        reset_url=url_for("settings_page"),
        hidden_fields=hidden_fields,
        reset_extra=answer_filter != "active" or only_debts,
    )
    agent_sel, provider_sel = filter_ctx["filter_agent_sel"], filter_ctx["filter_provider_sel"]
    filter_view = filter_ctx["filter_view"]
    highlight = filter_view == "highlight"

    models_active_list, models_archived_list = [], []
    for mid, info in models.items():
        entry = {
            "id": mid,
            "name": info.get("name", mid),
            "elo": info.get("elo", DEFAULT_ELO),
            "agent": info.get("agent", ""),
            "provider": info.get("provider", ""),
            "caption": format_model_caption(info),
        }
        # В «Подсвечивать» фильтр не сужает раскрытые списки и счётчики.
        if not highlight and not model_passes_tags(entry, agent_sel, provider_sel):
            continue
        if is_model_active(info):
            models_active_list.append(entry)
        else:
            models_archived_list.append(entry)
    models_active_list.sort(key=lambda m: m["elo"], reverse=True)
    models_archived_list.sort(key=lambda m: m["elo"], reverse=True)

    matrix = memo_answer_matrix()
    # Копии строк: рендер аннотирует hit/caption — мемо-значение остаётся чистым.
    answer_rows = [dict(r) for r in matrix["rows"]]
    if highlight:
        # «Подсвечивать»: матрица не сужается; «Показывать», чипы и «Только
        # долги» — критерии подсветки строк.
        for r in answer_rows:
            status_ok = (
                answer_filter == "all"
                or (answer_filter == "active" and r["status"] != "archived")
                or (answer_filter == "inactive" and r["status"] == "archived")
            )
            r["hit"] = (
                status_ok
                and model_passes_tags(models.get(r["id"], {}), agent_sel, provider_sel)
                and (not only_debts or r.get("debt", 0) > 0)
            )
        answer_hits = sum(1 for r in answer_rows if r["hit"])
    else:
        if answer_filter == "active":
            answer_rows = [r for r in answer_rows if r["status"] != "archived"]
        elif answer_filter == "inactive":
            answer_rows = [r for r in answer_rows if r["status"] == "archived"]
        answer_rows = [
            r for r in answer_rows
            if model_passes_tags(models.get(r["id"], {}), agent_sel, provider_sel)
        ]
        if only_debts:
            answer_rows = [r for r in answer_rows if r.get("debt", 0) > 0]
        answer_hits = 0
    for r in answer_rows:
        r["caption"] = format_model_caption(models.get(r["id"], {}))
    answer_inactive = [t for t in matrix["tasks"] if t not in matrix["active_tasks"]]
    coverage = memo_coverage()
    active_task_ids = memo_active_tasks()
    n_active_models = sum(1 for info in models.values() if is_model_active(info))
    n_active_tasks = len(active_task_ids)
    queue_bound = n_active_tasks * n_active_models * (n_active_models - 1) // 2
    queue_open = coverage.get("total", 0) - coverage.get("filled", 0)
    queue_pages = max(1, (queue_open + QUEUE_PAGE_SIZE - 1) // QUEUE_PAGE_SIZE)
    queue_page = valid_queue_page(request.args.get("queue_page"), queue_pages)
    queue_page_start = (queue_page - 1) * QUEUE_PAGE_SIZE
    if queue_bound > 0:
        # Для страницы P достаточно первых (offset + размер страницы)
        # рекомендаций. Пустая очередь запрашивает top-1 — сработает
        # fallback рематча.
        needed = (
            min(queue_page_start + QUEUE_PAGE_SIZE, queue_open)
            if queue_open > 0
            else 1
        )
        full_recs = data_cache.cached(
            f"recommendations:{needed}",
            lambda: get_recommendations(index_data, top_n=needed),
        )
    else:
        full_recs = []
    if full_recs and full_recs[0].get("is_rematch"):
        queue = []
        rematch = full_recs[:1]
    else:
        queue = full_recs[queue_page_start:queue_page_start + QUEUE_PAGE_SIZE]
        rematch = []

    # Строка-обоснование — та же функция, что на главной (не дублируется)
    for rec in queue + rematch:
        rec["reason"] = format_reason(rec)

    def _queue_page_url(page: int) -> str:
        """Ссылка на страницу очереди с сохранением остальных параметров."""
        args = request.args.to_dict(flat=False)
        args["queue_page"] = [str(page)]
        return url_for("settings_page", **args) + "#recommendation-queue"

    # Разбивка остатка очереди по таскам в порядке приоритета очереди
    # (порядок активных тасков T-NNN по возрастанию). Первое число в
    # скобках — первый активный таск, второе — второй и т.д. Счёт ведётся
    # по флагам и вердиктам (C(k,2) минус закрытые ячейки), без
    # материализации полного списка очереди.
    queue_breakdown: list = []
    queue_breakdown_str = ""
    queue_breakdown_legend = ""
    if len(active_task_ids) > 1 and queue_open > 0:
        flags_all = load_answer_flags()
        active_set = {mid for mid, info in models.items() if is_model_active(info)}
        closed: dict = {t: 0 for t in active_task_ids}
        for pair, pair_tasks in get_pair_task_verdicts().items():
            a, b = tuple(pair)
            if a not in active_set or b not in active_set:
                continue
            for t in pair_tasks:
                if t in closed:
                    task_flags = flags_all.get(t) or {}
                    if task_flags.get(a) and task_flags.get(b):
                        closed[t] += 1
        counts: dict = {}
        for t in active_task_ids:
            task_flags = flags_all.get(t) or {}
            k = sum(1 for mid in active_set if task_flags.get(mid))
            counts[t] = k * (k - 1) // 2 - closed[t]
        ordered = [t for t in active_task_ids if t in counts]
        ordered += [t for t in counts if t not in active_task_ids]
        queue_breakdown = [{"task": t, "count": counts[t]} for t in ordered]
        queue_breakdown_str = "+".join(str(counts[t]) for t in ordered)
        queue_breakdown_legend = " + ".join(f"{t}: {counts[t]}" for t in ordered)
    queue_has_coverage = coverage.get("percent") is not None

    # Единая сводка: вердикты журнала и рематчи (memo по дайджесту)
    matchups_count = matchups_count_of(index_data)
    rematch_count = memo_rematch_count()

    # Секция «Справочники»: значения справочника + счётчики моделей;
    # значения реестра вне справочника — отдельными строками в конце.
    lookup_data = load_lookups()
    lookup_sections = []
    for kind, title in (("agent", "Агенты"), ("provider", "Компании")):
        values = lookup_data["agents" if kind == "agent" else "providers"]
        counts: dict[str, int] = {}
        for info in models.values():
            val = str(info.get(kind) or "").strip()
            if val:
                counts[val] = counts.get(val, 0) + 1
        rows = [
            {"value": v, "count": counts.get(v, 0), "external": False}
            for v in values
        ]
        known = set(values)
        rows += [
            {"value": v, "count": counts[v], "external": True}
            for v in sorted((c for c in counts if c not in known), key=str.lower)
        ]
        lookup_sections.append({"kind": kind, "title": title, "rows": rows})

    return SETTINGS_TEMPLATE.render(
        tasks_list=tasks_list,
        models_total=len(models),
        models_active=len(models_active_list),
        models_archived=len(models_archived_list),
        models_active_list=models_active_list,
        models_archived_list=models_archived_list,
        answer_rows=answer_rows,
        answer_hits=answer_hits,
        answer_filter=answer_filter,
        answer_active_tasks=matrix["active_tasks"],
        answer_inactive_tasks=answer_inactive,
        answer_filled=matrix["filled"],
        answer_total=matrix["total"],
        answer_remaining=matrix["remaining"],
        answer_has_active=matrix["has_active"],
        queue=queue,
        rematch=rematch,
        queue_page=queue_page,
        queue_pages=queue_pages,
        queue_page_start=queue_page_start,
        queue_items=pagination_items(queue_page, queue_pages),
        queue_page_url=_queue_page_url,
        queue_filled=coverage.get("filled", 0),
        queue_total=coverage.get("total", 0),
        queue_remaining=coverage.get("total", 0) - coverage.get("filled", 0),
        queue_breakdown=queue_breakdown,
        queue_breakdown_str=queue_breakdown_str,
        queue_breakdown_legend=queue_breakdown_legend,
        queue_has_coverage=queue_has_coverage,
        queue_rematch_count=len(rematch),
        matchups_count=matchups_count,
        rematch_count=rematch_count,
        active_models_total=n_active_models,
        active_tasks_count=len(active_task_ids),
        known_tasks_count=len(memo_known_tasks()),
        only_debts=only_debts,
        lookup_sections=lookup_sections,
        **filter_ctx,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": "Настройки"},
        ],
    )


@app.route("/settings", methods=["POST"])
def settings_save():
    # Управление тасками теперь через отдельные POST-роуты /task/<id>/toggle и /current.
    return redirect(url_for("settings_page"))


# ─── Справочники: CRUD (секция #lookups страницы /settings) ─────────

# kind → название списка для сообщений пользователю
LOOKUP_KIND_TITLES = {"agent": "агентов", "provider": "компаний"}


def _settings_redirect(error: str = "", success: str = ""):
    """Redirect на /settings с одним сообщением (error или success)."""
    params: dict = {}
    if error:
        params["error"] = error
    elif success:
        params["success"] = success
    return redirect(url_for("settings_page", **params))


def _settings_filter_params(models: dict) -> dict:
    """Параметры блока «Фильтр» /settings из формы/query — для redirect.

    Возвращает answer_filter и непустые agents/providers/only_debts и
    не-дефолтные настройки отображения view/chips, чтобы POST-действия
    страницы не теряли состояние фильтров и режим.
    """
    params: dict = {
        "answer_filter": valid_answer_filter(request.values.get("answer_filter")),
    }
    agents_csv = _tags_csv(_parse_tag_tokens(
        _tag_query_csv(request.values, "agents"), _tag_values(models, "agent")[0],
    ))
    providers_csv = _tags_csv(_parse_tag_tokens(
        _tag_query_csv(request.values, "providers"), _tag_values(models, "provider")[0],
    ))
    if agents_csv:
        params["agents"] = agents_csv
    if providers_csv:
        params["providers"] = providers_csv
    if (request.values.get("only_debts") or "").strip() == "1":
        params["only_debts"] = "1"
    view = valid_filter_view(request.values.get("view"))
    if view != "hide":
        params["view"] = view
    chips = valid_chips_order(request.values.get("chips"))
    if chips != "alpha":
        params["chips"] = chips
    return params


@app.route("/lookups/add", methods=["POST"])
def lookup_add():
    kind = request.form.get("kind", "").strip()
    value = request.form.get("value", "").strip()
    if kind not in LOOKUP_KIND_TITLES:
        return _settings_redirect(error="Неизвестный справочник")
    if not value:
        return _settings_redirect(error="Введите значение")
    existing = find_value(kind, value)
    if existing:
        return _settings_redirect(error=f"Значение уже есть в справочнике: {existing}")
    if not add_value(kind, value):
        return _settings_redirect(error=f"Не удалось добавить значение: {value}")
    return _settings_redirect(
        success=f"В справочник {LOOKUP_KIND_TITLES[kind]} добавлено значение: {value}",
    )


@app.route("/lookups/promote", methods=["POST"])
def lookup_promote():
    kind = request.form.get("kind", "").strip()
    value = request.form.get("value", "").strip()
    if kind not in LOOKUP_KIND_TITLES:
        return _settings_redirect(error="Неизвестный справочник")
    if not value:
        return _settings_redirect(error="Введите значение")
    existing = find_value(kind, value)
    if existing:
        return _settings_redirect(error=f"Значение уже есть в справочнике: {existing}")
    if not add_value(kind, value):
        return _settings_redirect(error=f"Не удалось внести значение: {value}")
    return _settings_redirect(
        success=f"Значение «{value}» внесено в справочник {LOOKUP_KIND_TITLES[kind]}",
    )


@app.route("/lookups/rename", methods=["POST"])
def lookup_rename():
    kind = request.form.get("kind", "").strip()
    old = request.form.get("old", "").strip()
    new = request.form.get("new", "").strip()
    if kind not in LOOKUP_KIND_TITLES:
        return _settings_redirect(error="Неизвестный справочник")
    if not new:
        return _settings_redirect(error="Введите новое значение")
    if new == old:
        return _settings_redirect(error="Новое значение совпадает с текущим")
    existing = find_value(kind, new)
    if existing and existing != old:
        return _settings_redirect(error=f"Значение уже есть в справочнике: {existing}")

    lookup_data = load_lookups()
    values = lookup_data["agents" if kind == "agent" else "providers"]
    if old not in values:
        return _settings_redirect(error=f"Значение «{old}» не найдено в справочнике")

    models_path = MODELS_PATH
    if not models_path.exists():
        return _settings_redirect(error="data/models.yaml не найден")
    text = models_path.read_text(encoding="utf-8")
    models, preamble = parse_existing(text)

    # Справочник: переименование с сохранением позиции в списке
    values[values.index(old)] = new
    save_lookups(lookup_data)

    # Реестр: каскад по всем моделям со старым значением
    updated = 0
    for m in models:
        if str(m.get(kind) or "").strip() == old:
            m[kind] = new
            updated += 1
    models.sort(key=lambda m: m["id"])
    out = preamble.rstrip() + "\n\nmodels:\n"
    for m in models:
        out += format_model(m) + "\n"
    models_path.write_text(out, encoding="utf-8")

    index_data = generate_index()
    save_index(index_data)
    return _settings_redirect(
        success=f"Значение «{old}» переименовано в «{new}»: обновлено моделей — {updated}.",
    )


@app.route("/lookups/delete", methods=["POST"])
def lookup_delete():
    kind = request.form.get("kind", "").strip()
    value = request.form.get("value", "").strip()
    if kind not in LOOKUP_KIND_TITLES:
        return _settings_redirect(error="Неизвестный справочник")
    if not value:
        return _settings_redirect(error="Введите значение")

    lookup_data = load_lookups()
    values = lookup_data["agents" if kind == "agent" else "providers"]
    if value not in values:
        return _settings_redirect(error=f"Значение «{value}» не найдено в справочнике")

    index_data = ensure_index()
    count = sum(
        1 for info in index_data.get("models", {}).values()
        if str(info.get(kind) or "").strip() == value
    )
    if count:
        return _settings_redirect(
            error=f"Значение «{value}» используется у {count} моделей — удаление запрещено",
        )
    values.remove(value)
    save_lookups(lookup_data)
    return _settings_redirect(success=f"Значение «{value}» удалено из справочника")


@app.route("/answer_flags", methods=["POST"])
def save_answer_flags_route():
    """Сохраняет ручной учёт наличия ответов (матрица из /settings)."""
    index_data = ensure_index()
    models = index_data.get("models", {})
    model_ids = set(models)

    tasks_all = memo_known_tasks()
    active_set = set(memo_active_tasks())

    # Модели вне текущих фильтров в форме скрыты — сохраняем как было;
    # в режиме «Подсвечивать» отрисованы все строки реестра, поэтому видимы все.
    answer_filter = valid_answer_filter(
        request.args.get("answer_filter") or request.form.get("answer_filter")
    )
    only_debts = (
        request.args.get("only_debts") or request.form.get("only_debts") or ""
    ).strip() == "1"
    filter_view = valid_filter_view(
        request.args.get("view") or request.form.get("view")
    )
    chips_order = valid_chips_order(
        request.args.get("chips") or request.form.get("chips")
    )
    agent_sel = _parse_tag_tokens(
        _tag_query_csv(request.args, "agents") or _tag_query_csv(request.form, "agents"),
        _tag_values(models, "agent")[0],
    )
    provider_sel = _parse_tag_tokens(
        _tag_query_csv(request.args, "providers") or _tag_query_csv(request.form, "providers"),
        _tag_values(models, "provider")[0],
    )
    if filter_view == "highlight":
        visible = set(model_ids)
    else:
        visible = set()
        for mid, info in models.items():
            status = info.get("status", "active")
            if answer_filter == "active" and status == "archived":
                continue
            if answer_filter == "inactive" and status != "archived":
                continue
            if not model_passes_tags(info, agent_sel, provider_sel):
                continue
            visible.add(mid)
        if only_debts:
            # Строки без долгов скрыты фильтром — тоже сохраняем как было.
            debt_by_id = {
                r["id"]: r.get("debt", 0)
                for r in memo_answer_matrix()["rows"]
            }
            visible = {mid for mid in visible if debt_by_id.get(mid, 0) > 0}

    submitted = set(request.form.getlist("flag"))
    existing = load_answer_flags()
    new_flags: dict = {}
    for tid in tasks_all:
        for mid in model_ids:
            if tid in active_set and mid in visible:
                val = f"{mid}||{tid}" in submitted
            else:
                # Неактивные таски и скрытые фильтрами модели — сохраняем как было.
                val = bool((existing.get(tid) or {}).get(mid, False))
            if val:
                new_flags.setdefault(tid, {})[mid] = True
    save_answer_flags(new_flags)

    matrix = memo_answer_matrix()
    redirect_params = {"answer_filter": answer_filter}
    if only_debts:
        redirect_params["only_debts"] = "1"
    agents_csv = _tags_csv(agent_sel)
    providers_csv = _tags_csv(provider_sel)
    if agents_csv:
        redirect_params["agents"] = agents_csv
    if providers_csv:
        redirect_params["providers"] = providers_csv
    if filter_view != "hide":
        redirect_params["view"] = filter_view
    if chips_order != "alpha":
        redirect_params["chips"] = chips_order
    return redirect(url_for(
        "settings_page",
        success=f"Учёт ответов сохранён: закрыто {matrix['filled']} из {matrix['total']}.",
        **redirect_params,
    ))


@app.route("/edit/<model_id>")
def edit_page(model_id: str):
    index_data = ensure_index()
    info = index_data.get("models", {}).get(model_id)
    if not info:
        return redirect(url_for("leaderboard", error="Модель не найдена"))

    # Агент и компания — выпадающие списки только из справочника
    lookup_data = load_lookups()

    return EDIT_TEMPLATE.render(
        model={
            "id": model_id,
            "name": info.get("name", ""),
            "status": info.get("status", "active"),
            "agent": str(info.get("agent") or "").strip(),
            "provider": str(info.get("provider") or "").strip(),
        },
        agent_options=lookup_data["agents"],
        provider_options=lookup_data["providers"],
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": info.get("name", model_id), "href": f"/model/{model_id}"},
            {"label": "Редактирование"},
        ],
    )


@app.route("/edit/<model_id>", methods=["POST"])
def edit_model(model_id: str):
    name = request.form.get("name", "").strip()
    status = request.form.get("status", "").strip()
    agent = request.form.get("agent", "").strip()
    provider = request.form.get("provider", "").strip()

    if not name:
        return redirect(url_for("edit_page", model_id=model_id, error="Введите название модели"))

    if status not in ("active", "archived"):
        return redirect(url_for("edit_page", model_id=model_id, error="Неверный статус"))

    # Агент и компания: пустое значение, значение из справочника или текущее
    # значение модели без изменений (ручные значения «вне справочника»).
    index_data = ensure_index()
    current = index_data.get("models", {}).get(model_id, {})
    current_agent = str(current.get("agent") or "").strip()
    current_provider = str(current.get("provider") or "").strip()
    if agent and agent != current_agent and not has_value("agent", agent):
        return redirect(url_for(
            "edit_page", model_id=model_id,
            error=f"Агент «{agent}» отсутствует в справочнике: добавьте значение в разделе «Справочники».",
        ))
    if provider and provider != current_provider and not has_value("provider", provider):
        return redirect(url_for(
            "edit_page", model_id=model_id,
            error=f"Компания «{provider}» отсутствует в справочнике: добавьте значение в разделе «Справочники».",
        ))

    if not update_model(model_id, name, status, agent, provider):
        return redirect(url_for("leaderboard", error="Не удалось обновить модель"))

    status_label = "активна" if status == "active" else "неактивна (архив)"
    return redirect(url_for(
        "model_page",
        model_id=model_id,
        success=f"Модель «{name}» обновлена, статус: {status_label}.",
    ))


@app.route("/add_task")
def add_task_page():
    return ADD_TASK_TEMPLATE.render(
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": "Настройки", "href": "/settings"},
            {"label": "Добавить таску"},
        ],
    )


@app.route("/add_task", methods=["POST"])
def add_task():
    title = request.form.get("title", "").strip()
    slug = request.form.get("slug", "").strip()
    project = request.form.get("project", "").strip()
    baseline = request.form.get("baseline", "").strip()

    try:
        result = create_task(title, slug, project, baseline)
    except ValueError as e:
        return redirect(url_for("add_task_page", error=str(e)))

    index_data = generate_index()
    save_index(index_data)
    return redirect(url_for("settings_page", success=f"Таска {result['id']} добавлена."))


@app.route("/edit_task/<task_id>")
def edit_task_page(task_id: str):
    info = get_task_info(task_id)
    if not info:
        return redirect(url_for("settings_page", error="Таска не найдена"))
    return EDIT_TASK_TEMPLATE.render(
        task=info,
        error=request.args.get("error", ""),
        success=request.args.get("success", ""),
        crumbs=[
            {"label": "Рейтинг", "href": "/"},
            {"label": "Настройки", "href": "/settings"},
            {"label": f"{task_id} — редактирование"},
        ],
    )


@app.route("/edit_task/<task_id>", methods=["POST"])
def edit_task(task_id: str):
    title = request.form.get("title", "").strip()
    project = request.form.get("project", "").strip()
    baseline = request.form.get("baseline", "").strip()
    body = request.form.get("body", "")

    if not title:
        return redirect(url_for("edit_task_page", task_id=task_id, error="Введите название"))

    if not update_task(task_id, title, project, baseline, body):
        return redirect(url_for("settings_page", error="Не удалось обновить таску"))

    index_data = generate_index()
    save_index(index_data)
    return redirect(url_for("settings_page", success=f"Таска {task_id} обновлена."))


@app.route("/task/<task_id>/toggle", methods=["POST"])
def toggle_task(task_id: str):
    index_data = ensure_index()
    params = _settings_filter_params(index_data.get("models", {}))
    if not toggle_task_status(task_id):
        return redirect(url_for("settings_page", error="Не удалось переключить статус", **params))
    index_data = generate_index()
    save_index(index_data)
    return redirect(url_for("settings_page", success=f"Статус {task_id} изменён", **params))


@app.route("/task/<task_id>/current", methods=["POST"])
def set_current_task_route(task_id: str):
    index_data = ensure_index()
    params = _settings_filter_params(index_data.get("models", {}))
    if not set_current_task(task_id):
        return redirect(url_for("settings_page", error="Таска должна быть активной", **params))
    return redirect(url_for("settings_page", success=f"Текущая таска: {task_id}", **params))


# ─── Port handling ──────────────────────────────────────────────────


def find_free_port(start: int = 5000, max_tries: int = 10) -> int:
    import socket
    for port in range(start, start + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start


# ─── Main ───────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = find_free_port()
    print(f"ELO Benchmark сервер: http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
