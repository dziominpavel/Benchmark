#!/usr/bin/env python3
"""
export_web.py — статический read-only слепок консоли Benchmark для витрины.

Собирает полный слепок консоли (Рейтинг, История, Аналитика, Настройки,
страницы моделей и задач, очередь рекомендаций) в каталог `--out`. Слепок
автономен: все ссылки относительные, ресурсы — только файлы слепка; данные
репозитория не изменяются (консоль рендерится в режиме «только просмотр»).

Запуск:
    python tools/export_web.py --out <каталог> [--catalog-depth N]

--catalog-depth — глубина каталога слепка от корня витрины (по умолчанию 2,
т. е. публикация в /apps/<slug>/): маркер __catalog__ ведёт в каталог
«Мои приложения», маркер __root__ — в корень слепка.

Каталог вывода должен отсутствовать или быть пустым: сборка идёт «с нуля»,
повторная сборка не накапливает устаревшие файлы.
"""

from __future__ import annotations

import argparse
import json
import math
import posixpath
import re
import shutil
import sys
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))

import server  # noqa: E402  (импорт как библиотека: сервер стартует под __main__)

# ─── Пороги предупреждений (data не режется: только предупреждение) ──

HISTORY_WARN_RECORDS = 2000          # порог клиентского листания истории
QUEUE_WARN_PAGES = 500               # страниц очереди
SIZE_WARN_BYTES = 200 * 1024 * 1024  # объём слепка

HISTORY_PAGE_SIZE = 20               # размер страницы истории консоли

ROOT_MARKER = "__root__"
CATALOG_MARKER = "__catalog__"

# Абсолютные адреса консоли в разметке: корневые ссылки и ресурсы
_ATTR_RE = re.compile(r'(?P<attr>href|src|action)="(?P<value>/[^"]*)"')

# Строка истории: внутри .history-item нет вложенных div (только span/ссылки);
# после class допускаются атрибуты (якорь id="v-<seq>" для постоянных ссылок).
_HISTORY_ROW_RE = re.compile(r'<div class="history-item[^"]*"[^>]*>.*?</div>', re.S)

# ─── Разметка клиентского слоя зеркала ──────────────────────────────

# Обёртка таблицы целиком: срез кончается концом таблицы (внутри обёртки
# встречаются div-ы ячеек, поэтому границей служит </table>).
_TABLE_WRAP_RE = re.compile(r'<div class="table-wrap">.*?</table>\s*</div>', re.S)
# Строка рейтинга (первая ячейка — ранг) и её архивная разновидность
_RATING_ROW_RE = re.compile(r'<tr class="[^"]*">\s*<td class="rank">.*?</tr>', re.S)
_ARCHIVED_RATING_ROW_RE = re.compile(
    r'<tr class="archived[^"]*">\s*<td class="rank">.*?</tr>', re.S)
# Строка матрицы ответов (первая ячейка — модель) и её архивная разновидность
_FLAGS_ROW_RE = re.compile(r'<tr class="[^"]*">\s*<td class="model-cell">.*?</tr>', re.S)
_ARCHIVED_FLAGS_ROW_RE = re.compile(
    r'<tr class="archived[^"]*">\s*<td class="model-cell">.*?</tr>', re.S)
# Навигационный onchange фильтров: его роль в слепке исполняет mirror.js
_FORM_SUBMIT_RE = re.compile(r'\s+onchange="this\.form\.submit\(\)"')


class ExportError(Exception):
    """Нарушение при сборке слепка (диагностика печатается в stderr)."""


# ─── Карта вывода ───────────────────────────────────────────────────


def build_url_map(model_ids: list[str], queue_pages: int,
                  task_ids: list[str] | None = None) -> dict:
    """Карта «URL консоли → файл вывода».

    pages — обычные страницы (точный путь URL → файл; query сохраняется
    как есть), queue_files — страницы очереди по номеру queue_page.
    task_ids — страницы задач (ключи раздела tasks из index.json).
    """
    pages = {
        "/": "index.html",
        "/history": "history/index.html",
        "/stats": "stats/index.html",
        "/settings": "settings/index.html",
    }
    for mid in model_ids:
        pages[f"/model/{mid}"] = f"model/{mid}/index.html"
    for tid in task_ids or ():
        pages[f"/task/{tid}"] = f"task/{tid}/index.html"
    queue_files = {1: "settings/index.html"}
    for k in range(2, queue_pages + 1):
        queue_files[k] = f"settings/queue-{k:03d}/index.html"
    return {"pages": pages, "queue_files": queue_files}


def _rel_target(cur_file: str, target: str, as_dir: bool) -> str:
    """Относительный путь к цели из каталога текущего файла (posix).

    as_dir — ссылка на страницу-каталог (со слэшем на конце): статический
    сервер отдаёт из него index.html.
    """
    cur_dir = PurePosixPath(cur_file).parent
    target_path = PurePosixPath(target)
    if as_dir:
        target_path = target_path.parent
    t = () if str(target_path) == "." else target_path.parts
    s = () if str(cur_dir) == "." else cur_dir.parts
    i = 0
    while i < len(t) and i < len(s) and t[i] == s[i]:
        i += 1
    rel = "/".join([".."] * (len(s) - i) + list(t[i:])) or "."
    if as_dir:
        return rel + "/" if rel != "." else "./"
    return rel if rel != "." else target_path.name


def postprocess(html: str, out_file: str, urls: dict, catalog_depth: int) -> str:
    """Маркеры по глубине файла, снятые onchange и относительные ссылки."""
    depth = len(PurePosixPath(out_file).parent.parts)
    html = html.replace(ROOT_MARKER, "../" * depth)
    html = html.replace(CATALOG_MARKER, "../" * (catalog_depth + depth))
    html = _FORM_SUBMIT_RE.sub("", html)
    return _rewrite_links(html, out_file, urls)


def _rewrite_links(html: str, out_file: str, urls: dict) -> str:
    """`href|src|action="/…"` → относительные адреса вывода.

    `?queue_page=K` на «Настройках» ведёт на предгенерированный файл
    очереди (остальные параметры сохраняются), прочие query остаются
    на месте: их применяет клиентский слой зеркала.
    """
    pages: dict = urls["pages"]
    queue_files: dict = urls["queue_files"]
    max_queue = max(queue_files)

    def replace(match: re.Match) -> str:
        attr, value = match.group("attr"), match.group("value")
        fragment = ""
        if "#" in value:
            value, fragment = value.split("#", 1)
            fragment = "#" + fragment
        path, sep, query = value.partition("?")
        query = "?" + query if sep else ""
        if path == "/settings" and query:
            keep: list[str] = []
            page_no: int | None = None
            for part in query[1:].split("&amp;"):
                if part.startswith("queue_page="):
                    try:
                        page_no = int(part.split("=", 1)[1])
                    except ValueError:
                        page_no = 1
                else:
                    keep.append(part)
            if page_no is not None:
                page_no = min(max(page_no, 1), max_queue)
                target = queue_files[page_no]
                tail = ("?" + "&amp;".join(keep)) if keep else ""
                rel = _rel_target(out_file, target, as_dir=True)
                return f'{attr}="{rel}{tail}{fragment}"'
        if path in pages:
            rel = _rel_target(out_file, pages[path], as_dir=True)
        elif path.startswith("/static/"):
            rel = _rel_target(out_file, path.lstrip("/"), as_dir=False)
        else:
            raise ExportError(
                f"{out_file}: ссылка {value}{query}{fragment} отсутствует в карте вывода"
            )
        return f'{attr}="{rel}{query}{fragment}"'

    return _ATTR_RE.sub(replace, html)


# ─── Страницы ───────────────────────────────────────────────────────


def _fetch(client, url: str) -> str:
    """Рендер страницы консоли в read-only режиме (любой не-200 — ошибка)."""
    response = client.get(url)
    if response.status_code != 200:
        raise ExportError(f"GET {url} → {response.status_code}")
    return response.get_data(as_text=True)


def _build_history(client, index_data: dict) -> str:
    """«История»: строки всех страниц консоли в один документ.

    Лента запрашивается с `include_voided=1` (аннулированные помечены
    классом `history-item-voided` и по умолчанию прячутся mirror.js).
    Клиентская пагинация зеркала (20 записей на страницу) работает по
    полному составу DOM, поэтому строки собираются со всех страниц
    консоли в порядке вывода, а к строке добавляются данные участников
    (data-a/data-b) — их использует mirror.js для фильтров.
    """
    base = _fetch(client, "/history?include_voided=1")
    # Слепок открывается с выключенным фильтром: аннулированные скрыты по
    # умолчанию (mirror.js), поэтому снимаем серверную отметку чекбокса.
    base = base.replace(
        'name="include_voided" value="1" checked',
        'name="include_voided" value="1"',
    )
    records = server.merge_history_feed(
        index_data.get("elo_history", []),
        index_data.get("voided_history", []),
    )
    pages = max(1, math.ceil(len(records) / HISTORY_PAGE_SIZE))
    rows: list[str] = []
    for k in range(1, pages + 1):
        html = base if k == 1 else _fetch(client, f"/history?include_voided=1&page={k}")
        found = _HISTORY_ROW_RE.findall(html)
        expected = max(0, min(HISTORY_PAGE_SIZE, len(records) - (k - 1) * HISTORY_PAGE_SIZE))
        if len(found) != expected:
            raise ExportError(
                f"/history?page={k}: извлечено {len(found)} строк вместо {expected} — "
                "разметка истории изменилась, требуется правка экспорта"
            )
        for j, row in enumerate(found):
            rec = records[(k - 1) * HISTORY_PAGE_SIZE + j]
            a = str(rec.get("model_a_id") or rec.get("model_a") or "")
            b = str(rec.get("model_b_id") or rec.get("model_b") or "")
            rows.append(
                row.replace(
                    '<div class="history-item',
                    f'<div data-a="{a}" data-b="{b}" class="history-item',
                    1,
                )
            )
    if not rows:
        return base
    matches = list(_HISTORY_ROW_RE.finditer(base))
    return base[:matches[0].start()] + "\n".join(rows) + base[matches[-1].end():]


# ─── Данные клиентского слоя зеркала ────────────────────────────────


def _model_status_counts(index_data: dict) -> tuple[int, int]:
    """(активных, архивных) моделей в срезе реестра index.json."""
    models = index_data.get("models", {})
    archived = sum(
        1 for info in models.values() if info.get("status", "active") == "archived"
    )
    return len(models) - archived, archived


def build_models_island(index_data: dict, island_id: str) -> str:
    """JSON-остров состава реестра для клиентского слоя зеркала.

    Компактные ключи: n — имя, c — подпись, e — Elo, g — игры, s — статус,
    a — агент, p — компания. `</` экранируется, чтобы JSON не оборвал
    script-блок.
    """
    payload = {}
    for mid, info in sorted(index_data.get("models", {}).items()):
        payload[mid] = {
            "n": str(info.get("name", mid)),
            "c": server.format_model_caption(info),
            "e": info.get("elo", server.DEFAULT_ELO),
            "g": info.get("games", 0),
            "s": info.get("status", "active"),
            "a": str(info.get("agent") or "").strip(),
            "p": str(info.get("provider") or "").strip(),
        }
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return (
        f'<script type="application/json" id="{island_id}">'
        + data.replace("</", "<\\/")
        + "</script>"
    )


def _inject_before_body(html: str, fragment: str) -> str:
    """Вставка инертного фрагмента (script/template) перед закрытием body."""
    pos = html.rfind("</body>")
    if pos == -1:
        raise ExportError("в разметке страницы не найден </body>")
    return html[:pos] + fragment + "\n" + html[pos:]


def _flags_table_wrap(html: str) -> str | None:
    """Срез обёртки таблицы матрицы ответов (по классу flags-table)."""
    for match in _TABLE_WRAP_RE.finditer(html):
        if 'class="flags-table"' in match.group(0):
            return match.group(0)
    return None


class MirrorData:
    """Данные и шаблоны строк клиентского слоя слепка (mirror.js).

    Базовые рендеры страниц показывают только пул по умолчанию, поэтому
    строки архива собираются из рендера «все» и вкладываются в страницу
    тегами template; остров реестра строится один раз. Если базовый пул
    пуст и таблицы нет вовсе, вкладывается таблица целиком из рендера
    «все» — страница остаётся работоспособной при любом состоянии реестра.
    """

    def __init__(self, client, index_data: dict) -> None:
        self.client = client
        self.index_data = index_data
        self.models_island = build_models_island(index_data, "mirror-models")
        self.stats_island = build_models_island(index_data, "mirror-stats-data")
        self.active, self.archived = _model_status_counts(index_data)
        self._index_fragment: str | None = None
        self._settings_fragment: str | None = None

    @staticmethod
    def _fragment(archived_rows: list[str], full_table: str | None) -> str:
        """Теги template: строки архива и (при необходимости) таблица целиком.

        Строки вкладываются в table/tbody: вне контекста таблицы парсер HTML
        игнорирует одиночные <tr>.
        """
        parts: list[str] = []
        if archived_rows:
            parts.append(
                '<template id="mirror-archived-rows"><table><tbody>'
                + "\n".join(archived_rows)
                + "</tbody></table></template>"
            )
        if full_table is not None:
            parts.append('<template id="mirror-table-wrap">' + full_table + "</template>")
        return "\n".join(parts)

    def validate_index_base(self, html: str) -> None:
        """Сверяет базовый рендер главной: строк ровно по числу активных."""
        wrap = _TABLE_WRAP_RE.search(html)
        if wrap:
            rows = _RATING_ROW_RE.findall(wrap.group(0))
            if len(rows) != self.active:
                raise ExportError(
                    f"/: строк рейтинга {len(rows)} вместо {self.active} — "
                    "разметка главной изменилась, требуется правка экспорта"
                )
        elif self.active:
            raise ExportError(
                f"/: нет таблицы рейтинга при {self.active} активных моделях"
            )

    def index_fragment(self, base_html: str) -> str:
        if self._index_fragment is None:
            self._index_fragment = self._build_index_fragment(base_html)
        return self._index_fragment

    def _build_index_fragment(self, base_html: str) -> str:
        if not self.index_data.get("models"):
            return ""  # пустой реестр: таблицы нет ни в одном режиме
        base_has_table = _TABLE_WRAP_RE.search(base_html) is not None
        if not self.archived and base_has_table:
            return ""
        all_wrap = _TABLE_WRAP_RE.search(_fetch(self.client, "/?filter=all"))
        if all_wrap is None:
            raise ExportError("/?filter=all: не найдена таблица рейтинга")
        rows = _ARCHIVED_RATING_ROW_RE.findall(all_wrap.group(0))
        if len(rows) != self.archived:
            raise ExportError(
                f"/?filter=all: строк архива {len(rows)} вместо {self.archived} — "
                "разметка главной изменилась, требуется правка экспорта"
            )
        return self._fragment(rows, None if base_has_table else all_wrap.group(0))

    def validate_settings_base(self, html: str) -> None:
        """Сверяет базовый рендер «Настроек»: строк матрицы по числу активных."""
        wrap = _flags_table_wrap(html)
        if wrap:
            rows = _FLAGS_ROW_RE.findall(wrap)
            if len(rows) != self.active:
                raise ExportError(
                    f"/settings: строк матрицы {len(rows)} вместо {self.active} — "
                    "разметка настроек изменилась, требуется правка экспорта"
                )
        elif self.active and 'name="answer_filter"' in html:
            raise ExportError(
                f"/settings: нет таблицы матрицы при {self.active} активных моделях"
            )

    def settings_fragment(self, base_html: str) -> str:
        if self._settings_fragment is None:
            self._settings_fragment = self._build_settings_fragment(base_html)
        return self._settings_fragment

    def _build_settings_fragment(self, base_html: str) -> str:
        if not self.index_data.get("models"):
            return ""  # пустой реестр: матрицы нет ни в одном режиме
        if 'name="answer_filter"' not in base_html:
            return ""  # нет активных тасков — матрицы нет и в консоли
        base_has_table = _flags_table_wrap(base_html) is not None
        if not self.archived and base_has_table:
            return ""
        all_wrap = _flags_table_wrap(_fetch(self.client, "/settings?answer_filter=all"))
        if all_wrap is None:
            raise ExportError("/settings?answer_filter=all: не найдена таблица матрицы")
        rows = _ARCHIVED_FLAGS_ROW_RE.findall(all_wrap)
        if len(rows) != self.archived:
            raise ExportError(
                f"/settings?answer_filter=all: строк архива {len(rows)} вместо "
                f"{self.archived} — разметка настроек изменилась"
            )
        return self._fragment(rows, None if base_has_table else all_wrap)


# ─── Целостность вывода ─────────────────────────────────────────────


class _LinkCollector(HTMLParser):
    """Собирает ссылки/ресурсы и POST-формы HTML-файла слепка."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.post_forms = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        data = dict(attrs)
        if tag == "form" and (data.get("method") or "").lower() == "post":
            self.post_forms += 1
        for name in ("href", "src", "action"):
            if data.get(name):
                self.links.append((name, data[name]))


def check_output(out_root: Path, catalog_depth: int) -> list[str]:
    """Проход по HTML слепка: корневые адреса, внешние ресурсы, POST-формы,
    остаточные маркеры, неразрешимые ссылки. Возвращает список нарушений.
    """
    errors: list[str] = []
    for path in sorted(out_root.rglob("*.html")):
        out_file = path.relative_to(out_root).as_posix()
        depth = len(PurePosixPath(out_file).parent.parts)
        catalog_href = "../" * (catalog_depth + depth)
        html = path.read_text(encoding="utf-8")
        errors.extend(_check_file(html, out_file, out_root, catalog_href))
    return errors


def _check_file(html: str, out_file: str, out_root: Path, catalog_href: str) -> list[str]:
    errors: list[str] = []
    if ROOT_MARKER in html or CATALOG_MARKER in html:
        errors.append(f"{out_file}: остаточный маркер {ROOT_MARKER}/{CATALOG_MARKER}")
    collector = _LinkCollector()
    collector.feed(html)
    if collector.post_forms:
        errors.append(f"{out_file}: POST-форма ({collector.post_forms})")
    base = PurePosixPath(out_file).parent
    for attr, raw in collector.links:
        value = (raw or "").strip()
        if not value or value.startswith("#"):
            continue
        if value == catalog_href:
            continue  # ссылка в каталог витрины — вне корня слепка
        if re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:", value):
            errors.append(f'{out_file}: {attr}="{value}" — внешний ресурс')
            continue
        if value.startswith("/"):
            errors.append(f'{out_file}: {attr}="{value}" — корневой адрес')
            continue
        if value.startswith("?"):
            continue
        path = value.split("#", 1)[0].split("?", 1)[0]
        if not path:
            continue
        target = posixpath.normpath(str(base / path))
        if path.endswith("/") or target == ".":
            target = posixpath.normpath(target + "/index.html")
        if target.startswith(".."):
            errors.append(f'{out_file}: {attr}="{value}" — вне слепка')
            continue
        if not (out_root / target).is_file():
            errors.append(f'{out_file}: {attr}="{value}" — файл не найден ({target})')
    return errors


# ─── Сборка ─────────────────────────────────────────────────────────


def _warn(message: str) -> None:
    print(f"ПРЕДУПРЕЖДЕНИЕ: {message}")


def _fail(message: str) -> int:
    print(f"Ошибка экспорта: {message}", file=sys.stderr)
    return 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Статический read-only слепок консоли Benchmark для витрины",
    )
    parser.add_argument("--out", required=True, help="каталог вывода (пустой или отсутствующий)")
    parser.add_argument(
        "--catalog-depth", type=int, default=2,
        help="глубина каталога слепка от корня витрины (по умолчанию 2: /apps/<slug>/)",
    )
    args = parser.parse_args(argv)
    if args.catalog_depth < 0:
        parser.error("--catalog-depth не может быть отрицательным")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    out_root = Path(args.out)
    if out_root.exists() and not out_root.is_dir():
        return _fail(f"путь вывода не каталог: {out_root}")
    if out_root.exists() and any(out_root.iterdir()):
        return _fail(f"каталог вывода не пуст: {out_root}")
    try:
        return _build(args, out_root)
    except ExportError as exc:
        return _fail(str(exc))


def _build(args: argparse.Namespace, out_root: Path) -> int:
    server.app.config["READ_ONLY"] = True
    server.app.config["TESTING"] = True
    client = server.app.test_client()

    index_data = server.ensure_index()
    model_ids = sorted(index_data.get("models", {}))
    task_ids = sorted(index_data.get("tasks", {}))
    coverage = server.memo_coverage()
    queue_open = coverage.get("total", 0) - coverage.get("filled", 0)
    queue_pages = max(1, math.ceil(queue_open / server.QUEUE_PAGE_SIZE))
    urls = build_url_map(model_ids, queue_pages, task_ids)

    shutil.copytree(TOOLS_DIR / "static", out_root / "static")
    shutil.copyfile(TOOLS_DIR / "static" / "icon.svg", out_root / "icon.svg")

    written: list[str] = []
    mirror = MirrorData(client, index_data)

    def _write(out_file: str, html: str, island: str = "", fragment: str = "") -> None:
        path = out_root / out_file
        path.parent.mkdir(parents=True, exist_ok=True)
        if fragment:
            html = _inject_before_body(html, fragment)
        if island:
            html = _inject_before_body(html, island)
        html = postprocess(html, out_file, urls, args.catalog_depth)
        path.write_text(html, encoding="utf-8", newline="\n")
        written.append(out_file)

    index_html = _fetch(client, "/")
    mirror.validate_index_base(index_html)
    _write("index.html", index_html,
           island=mirror.models_island, fragment=mirror.index_fragment(index_html))

    _write("history/index.html", _build_history(client, index_data),
           island=mirror.models_island)
    _write("stats/index.html", _fetch(client, "/stats"), island=mirror.stats_island)

    settings_html = _fetch(client, "/settings")
    mirror.validate_settings_base(settings_html)
    settings_fragment = mirror.settings_fragment(settings_html)
    _write("settings/index.html", settings_html,
           island=mirror.models_island, fragment=settings_fragment)
    for k in range(2, queue_pages + 1):
        _write(urls["queue_files"][k], _fetch(client, f"/settings?queue_page={k}"),
               island=mirror.models_island, fragment=settings_fragment)
    for mid in model_ids:
        _write(f"model/{mid}/index.html", _fetch(client, f"/model/{mid}"))
    for tid in task_ids:
        _write(f"task/{tid}/index.html", _fetch(client, f"/task/{tid}"))

    errors = check_output(out_root, args.catalog_depth)
    if errors:
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        print(f"Проверка вывода не пройдена: нарушений {len(errors)}", file=sys.stderr)
        return 1

    history_count = len(index_data.get("elo_history", []))
    total_size = sum(f.stat().st_size for f in out_root.rglob("*") if f.is_file())
    if history_count > HISTORY_WARN_RECORDS:
        _warn(
            f"история: {history_count} записей — больше порога клиентского листания "
            f"({HISTORY_WARN_RECORDS}); страница собирается полностью"
        )
    if queue_pages > QUEUE_WARN_PAGES:
        _warn(
            f"очередь: {queue_pages} страниц — больше предела ({QUEUE_WARN_PAGES}); "
            "страницы собираются полностью"
        )
    if total_size > SIZE_WARN_BYTES:
        _warn(
            f"объём слепка: {total_size / (1024 * 1024):.0f} МБ — больше предела "
            f"({SIZE_WARN_BYTES // (1024 * 1024)} МБ)"
        )

    print(f"Слепок собран: {out_root}")
    print(
        f"  страниц: {len(written)} (моделей: {len(model_ids)}, "
        f"страниц очереди: {queue_pages})"
    )
    print(f"  объём: {total_size / (1024 * 1024):.1f} МБ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
