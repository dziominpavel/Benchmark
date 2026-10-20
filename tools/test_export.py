#!/usr/bin/env python3
"""
test_export.py — статический слепок витрины: read-only режим и команда экспорта.

Проверяет:
  * 1.1 — в обычном рендере плашки зеркала нет, в read-only есть
    (плашка со ссылкой в каталог, футер без «локальной консоли», favicon).
  * 1.2 — в read-only нет POST-форм и write-ссылок; обычный режим не изменился.
  * 1.3 — в read-only устаревший index.json пересчитывается без записи файла.
  * 2.1 — состав и детерминизм вывода export_web.py.
  * 2.2 — каждая внутренняя ссылка слепка разрешается в файл, маркеров нет.
  * 2.3 — целостность и пороги: нарушитель → ненулевой код, чистая сборка → 0.
  * 3.1 — строки архива и остров реестра «Рейтинга», номера рангов в span.
  * 3.2 — шаблон строк архива матрицы «Настроек» и данные участников истории.
  * 3.3 — JSON-остров аналитики содержит все модели полного состава.
  * Волна 2: аннулированные строки истории в слепке (пометка, причина,
    участники), контролы аннулирования недоступны, фильтр «Показывать
    аннулированные» сохраняется, mirror.js знает про оба маркера.
  * Волна 4: страницы задач в слепке (`task/<id>/index.html`), бейдж таска
    и ID настроек ведут на статическую страницу задачи, слепок без записи
    (нет кнопки, task.md, форм аннулирования); аналитика A1–A8 в слепке без
    live-контролов (линии/период, ссылки ячеек матрицы, разбивка по таскам
    только при 2+ активных); профиль — место/последний матч/покрытие, ссылки
    вердиктов, поиск и сортировка «Личных встреч» вырезаны вместе с aria-sort.
  * Версия и сборка консоли: маркеры `.footer-version` (тег релиза) и
    `.footer-build` (время коммита) в подвале слепка.

Запуск: python tools/test_export.py
"""

from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_cache
import elo
import export_web
import lookups
import server

MODELS_YAML = """\
models:
  - id: alpha
    name: Alpha
    agent: Agent
    provider: Prov
    added: 2026-01-01
    status: active
  - id: beta
    name: Beta
    agent: Agent
    provider: Prov
    added: 2026-01-01
    status: active
  - id: gamma
    name: Gamma
    agent: Agent
    provider: Prov
    added: 2026-01-01
    status: archived
"""

SETTINGS_YAML = """\
current_task: T-001
tasks:
  T-001: active
"""

FLAGS_YAML = """\
answer_flags:
  T-001:
    alpha: true
    beta: true
"""

LOOKUPS_YAML = """\
agents:
  - Agent
providers:
  - Prov
"""

JOURNAL_LINE = (
    '{"version": 1, "seq": 1, "task": "T-001", "matchup": "T-001/001", '
    '"model_a": "alpha", "model_b": "beta", "model_a_id": "alpha", '
    '"model_b_id": "beta", "winner": "a", "date": "2026-01-02", '
    '"recorded_at": "2026-01-02T10:00:00+03:00", '
    '"elo": {"alpha": {"before": 1200, "after": 1220, "delta": 20}, '
    '"beta": {"before": 1200, "after": 1180, "delta": -20}}}\n'
)

TASK_MD = """\
---
id: T-001
title: "Smoke"
project: "Benchmark"
baseline_commit: ""
---

Тело smoke-задачи.
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@contextmanager
def _temp_storage():
    """tmp-хранилище с подменой путей elo/server/lookups на время теста."""
    with tempfile.TemporaryDirectory(prefix="bench_export_") as tmp_str:
        tmp = Path(tmp_str)
        paths = {
            "tmp": tmp,
            "journal": tmp / "matchups" / "journal.jsonl",
            "models": tmp / "models.yaml",
            "flags": tmp / "answer_flags.yaml",
            "settings": tmp / "settings.yaml",
            "lookups": tmp / "lookups.yaml",
            "index": tmp / "index.json",
            "tasks": tmp / "tasks",
        }
        _write(paths["models"], MODELS_YAML)
        _write(paths["settings"], SETTINGS_YAML)
        _write(paths["flags"], FLAGS_YAML)
        _write(paths["lookups"], LOOKUPS_YAML)
        _write(paths["journal"], JOURNAL_LINE)
        _write(paths["tasks"] / "T-001-smoke" / "task.md", TASK_MD)

        saved = {
            "elo.JOURNAL_PATH": elo.JOURNAL_PATH,
            "elo.MODELS_PATH": elo.MODELS_PATH,
            "elo.ANSWER_FLAGS_PATH": elo.ANSWER_FLAGS_PATH,
            "elo.SETTINGS_PATH": elo.SETTINGS_PATH,
            "elo.TASKS_DIR": elo.TASKS_DIR,
            "elo.INDEX_PATH": elo.INDEX_PATH,
            "lookups.LOOKUPS_PATH": lookups.LOOKUPS_PATH,
            "server.INDEX_PATH": server.INDEX_PATH,
            "server.MODELS_PATH": server.MODELS_PATH,
            "server.TASKS_DIR": server.TASKS_DIR,
        }
        elo.JOURNAL_PATH = paths["journal"]
        elo.MODELS_PATH = paths["models"]
        elo.ANSWER_FLAGS_PATH = paths["flags"]
        elo.SETTINGS_PATH = paths["settings"]
        elo.TASKS_DIR = paths["tasks"]
        elo.INDEX_PATH = paths["index"]
        lookups.LOOKUPS_PATH = paths["lookups"]
        server.INDEX_PATH = paths["index"]
        server.MODELS_PATH = paths["models"]
        server.TASKS_DIR = paths["tasks"]
        data_cache.clear()
        try:
            yield paths
        finally:
            data_cache.clear()
            elo.JOURNAL_PATH = saved["elo.JOURNAL_PATH"]
            elo.MODELS_PATH = saved["elo.MODELS_PATH"]
            elo.ANSWER_FLAGS_PATH = saved["elo.ANSWER_FLAGS_PATH"]
            elo.SETTINGS_PATH = saved["elo.SETTINGS_PATH"]
            elo.TASKS_DIR = saved["elo.TASKS_DIR"]
            elo.INDEX_PATH = saved["elo.INDEX_PATH"]
            lookups.LOOKUPS_PATH = saved["lookups.LOOKUPS_PATH"]
            server.INDEX_PATH = saved["server.INDEX_PATH"]
            server.MODELS_PATH = saved["server.MODELS_PATH"]
            server.TASKS_DIR = saved["server.TASKS_DIR"]


@contextmanager
def _read_only():
    """Включает режим «только просмотр» и гарантированно возвращает флаг."""
    saved = bool(server.app.config.get("READ_ONLY"))
    server.app.config["READ_ONLY"] = True
    try:
        yield
    finally:
        server.app.config["READ_ONLY"] = saved


def test_read_only_two_modes():
    with _temp_storage():
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # Обычная локальная консоль: плашки зеркала нет
        html = client.get("/").get_data(as_text=True)
        assert "mirror-banner" not in html, "плашка не должна появляться в локальной консоли"
        assert "локальная консоль" in html, "пропал футер локальной консоли"
        assert "__catalog__" not in html, "маркер каталога просочился в обычный рендер"

        # Read-only слепок: плашка, ссылка в каталог, favicon, футер зеркала
        with _read_only():
            html = client.get("/").get_data(as_text=True)
        assert "mirror-banner" in html, "в read-only нет плашки зеркала"
        assert "только просмотр" in html, "нет пометки «только просмотр»"
        assert "__catalog__" in html, "нет ссылки в каталог по маркеру"
        assert '__root__icon.svg' in html, "нет favicon по маркеру __root__"
        assert "локальная консоль" not in html, "футер read-only упоминает локальную консоль"
        assert "демонстрационная копия" in html

        # Возврат к обычному режиму: плашка исчезает
        html = client.get("/").get_data(as_text=True)
        assert "mirror-banner" not in html, "флаг read-only не вернулся в исходное состояние"
    print("1.1 read-only two modes: OK")


def test_read_only_inert_controls():
    with _temp_storage():
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # Обычный режим: контролы записи на месте (условия их не отключили)
        home = client.get("/").get_data(as_text=True)
        assert 'method="POST"' in home and 'action="/verdict"' in home
        assert "usePair(" in home, "пропал скрипт формы вердикта"
        assert "this.form.submit()" in home, "фильтры обычной консоли потеряли автоприменение"
        model_html = client.get("/model/alpha").get_data(as_text=True)
        assert 'href="/edit/alpha"' in model_html
        settings = client.get("/settings").get_data(as_text=True)
        assert 'action="/answer_flags"' in settings
        assert 'href="/add"' in settings and 'href="/add_task"' in settings

        # Слепок: POST-форм и write-адресов нет, контролы — в disabled fieldset
        with _read_only():
            home = client.get("/").get_data(as_text=True)
            model_html = client.get("/model/alpha").get_data(as_text=True)
            settings = client.get("/settings").get_data(as_text=True)

        for name, page in (("главная", home), ("модель", model_html),
                           ("настройки", settings)):
            assert "method=" + '"POST"' not in page, f"{name}: осталась POST-форма"
            for ref in ('href="/edit', 'href="/add', 'action="/verdict"',
                        'action="/answer_flags"', 'action="/lookups',
                        'action="/task/'):
                assert ref not in page, f"{name}: остался write-адрес {ref}"

        assert "<fieldset disabled" in home and "<fieldset disabled" in settings
        assert "Прогнать" in home and "disabled>Прогнать</button>" in home
        assert 'onclick="usePair(' not in home, "кнопка запуска осталась активной"
        assert "function validate" not in home, "скрипт записи отрендерен в read-only"
        assert 'aria-disabled="true"' in model_html, "«Изменить» не обезврежена"
    print("1.2 read-only inert controls: OK")


def test_read_only_no_cache_write():
    with _temp_storage() as paths:
        # Заведомо устаревший кэш: дайджест не совпадает с журналом
        _write(paths["index"], json.dumps({"matchups_digest": "stale"}))
        stale_text = paths["index"].read_text(encoding="utf-8")

        server.app.config["TESTING"] = True
        client = server.app.test_client()

        with _read_only():
            resp = client.get("/")
            assert resp.status_code == 200
            assert paths["index"].read_text(encoding="utf-8") == stale_text, (
                "read-only перезаписал устаревший index.json"
            )
            idx = server.ensure_index()
            assert idx.get("matchups_digest") != "stale", (
                "устаревший индекс не пересчитан в памяти"
            )

        # Обычный режим: тот же устаревший кэш обновляется на диске
        data_cache.clear()
        client.get("/")
        assert paths["index"].read_text(encoding="utf-8") != stale_text, (
            "обычный режим не обновил устаревший index.json"
        )
    print("1.3 read-only keeps stale cache: OK")


def _big_journal(count: int) -> str:
    """Синтетический журнал на count вердиктов между alpha и beta."""
    base = datetime(2026, 1, 2, 10, 0, 0)
    lines = []
    for seq in range(1, count + 1):
        ts = base + timedelta(minutes=seq)
        lines.append(json.dumps({
            "version": 1,
            "seq": seq,
            "task": "T-001",
            "matchup": f"T-001/{seq:04d}",
            "model_a": "alpha",
            "model_b": "beta",
            "model_a_id": "alpha",
            "model_b_id": "beta",
            "winner": "a" if seq % 2 else "b",
            "date": ts.date().isoformat(),
            "recorded_at": ts.isoformat(timespec="seconds"),
        }, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def test_export_output_and_determinism():
    with _temp_storage():
        with tempfile.TemporaryDirectory(prefix="bench_mirror_a_") as dir_a, \
                tempfile.TemporaryDirectory(prefix="bench_mirror_b_") as dir_b:
            with _read_only():
                assert export_web.main(["--out", dir_a]) == 0
                assert export_web.main(["--out", dir_b]) == 0
            files_a = {
                p.relative_to(dir_a).as_posix(): p.read_bytes()
                for p in Path(dir_a).rglob("*") if p.is_file()
            }
            files_b = {
                p.relative_to(dir_b).as_posix(): p.read_bytes()
                for p in Path(dir_b).rglob("*") if p.is_file()
            }
            assert set(files_a) == set(files_b), "состав сборок различается"
            for name, data in files_a.items():
                assert files_b[name] == data, f"содержимое различается: {name}"
            for expected in (
                "index.html", "history/index.html", "stats/index.html",
                "settings/index.html", "model/alpha/index.html",
                "model/gamma/index.html", "task/T-001/index.html",
                "static/css/console.css",
                "static/js/theme.js", "static/js/mirror.js",
                "static/js/filter-panel.js", "icon.svg",
            ):
                assert expected in files_a, f"нет файла вывода: {expected}"
    print("2.1 export output and determinism: OK")


def test_export_links_and_markers():
    with _temp_storage():
        with tempfile.TemporaryDirectory(prefix="bench_mirror_links_") as out:
            with _read_only():
                assert export_web.main(["--out", out, "--catalog-depth", "3"]) == 0
            errors = export_web.check_output(Path(out), 3)
            assert not errors, f"целостность нарушена: {errors}"
            html = (Path(out) / "index.html").read_text(encoding="utf-8")
            assert "../../../" in html, "ссылка в каталог не учла --catalog-depth"
            assert "__root__" not in html and "__catalog__" not in html
            history = (Path(out) / "history" / "index.html").read_text(encoding="utf-8")
            assert 'href="../static/css/console.css"' in history
            model = (Path(out) / "model" / "alpha" / "index.html").read_text(encoding="utf-8")
            assert 'src="../../static/js/theme.js"' in model

            # Кнопка «Настройки фильтра» и её скрипт есть на всех уровнях слепка
            for name, page, src in (
                ("главной", html, "static/js/filter-panel.js"),
                ("истории", history, "../static/js/filter-panel.js"),
                ("модели", model, "../../static/js/filter-panel.js"),
            ):
                assert f'src="{src}"' in page, f"слепок {name}: нет filter-panel.js"

            # Версия и сборка запечены в подвал слепка (та же строка shell)
            version = server.app_version()
            build = server.app_build_time()
            version_mark = f'<span class="footer-version" title="Версия консоли">{version}</span>'
            build_mark = f'<span class="footer-build" title="Дата и время сборки">сборка {build}</span>'
            for name, page in (("главной", html), ("истории", history), ("модели", model)):
                assert version_mark in page, f"слепок {name} без версии в подвале"
                assert build_mark in page, f"слепок {name} без сборки в подвале"

            # Волна 3: live-only элементы и мёртвые ссылки в слепок не попадают
            assert 'name="q"' not in html
            for marker in ("export-links", "sort-link", "aria-sort",
                           "data-combobox", "combobox.js"):
                assert marker not in html, f"слепок главной: live-only {marker}"
            for marker in ("export-links", "data-combobox", "combobox.js",
                           "page-jump", 'name="task"', 'name="from"',
                           'name="outcome"', 'name="pair"', 'name="only_voided"'):
                assert marker not in history, f"слепок истории: live-only {marker}"
            assert 'class="badge-task" href="../task/T-001/"' in history
            assert "matchup-chip" in history and "/history?v=" not in history

            # Живой поиск: скрипт не подключён, поисковых полей нет,
            # служебных data-атрибутов в разметке слепка нет.
            for name, page in (("главной", html), ("истории", history),
                               ("модели", model)):
                assert "live-search.js" not in page, f"слепок {name}: подключён live-search.js"
                for marker in ("data-live-search", "data-live-input",
                               "data-live-count", "data-live-empty",
                               "data-live-reset", "data-live-link",
                               "data-search="):
                    assert marker not in page, f"слепок {name}: live-only {marker}"
    print("2.2 links and markers: OK")


def test_export_queue_pages():
    ids = [f"m{i:02d}" for i in range(15)]
    with _temp_storage() as paths:
        models_yaml = ["models:"]
        for mid in ids:
            models_yaml += [
                f"  - id: {mid}",
                f"    name: Model {mid}",
                "    agent: Agent",
                "    provider: Prov",
                "    added: 2026-01-01",
                "    status: active",
            ]
        flags_yaml = ["answer_flags:", "  T-001:"]
        flags_yaml += [f"    {mid}: true" for mid in ids]
        _write(paths["models"], "\n".join(models_yaml) + "\n")
        _write(paths["flags"], "\n".join(flags_yaml) + "\n")
        _write(paths["journal"], "")
        data_cache.clear()

        with tempfile.TemporaryDirectory(prefix="bench_mirror_queue_") as out:
            with _read_only():
                assert export_web.main(["--out", out]) == 0
            root = Path(out)
            assert (root / "settings" / "queue-002" / "index.html").is_file(), \
                "нет второй страницы очереди"
            page1 = (root / "settings" / "index.html").read_text(encoding="utf-8")
            assert "queue-002/" in page1, "ссылка на вторую страницу не переписана в файл"
            assert "queue_page=" not in page1, "остались query-ссылки очереди"
            page2 = (root / "settings" / "queue-002" / "index.html").read_text(
                encoding="utf-8")
            assert "page-arrow" in page2, "на второй странице нет виджета пагинации"
            assert 'class="rank">101</td>' in page2, "вторая страница без строк 101+"
            assert 'id="mirror-models"' in page2, "страница очереди без острова реестра"
            assert 'href="../task/T-001/"' in page1, "ячейка таска очереди без ссылки"
            index = (root / "index.html").read_text(encoding="utf-8")
            assert 'href="task/T-001/"' in index, "таск карточки рекомендации без ссылки"
    print("2.2 queue pages: OK")


def _island_of(html: str, island_id: str) -> dict:
    """Разбирает JSON-остров зеркала по id."""
    match = re.search(
        r'<script type="application/json" id="' + island_id + r'">(.*?)</script>',
        html, re.S)
    assert match, f"нет острова {island_id}"
    return json.loads(match.group(1))


def test_export_mirror_layer():
    """3.1–3.3: острова данных, шаблоны архива, скрипт зеркала, снятые onchange.

    Обычный рендер (без экспорта) автоприменение фильтров сохраняет — его
    снимает именно postprocess слепка, чью работу исполняет mirror.js.
    """
    with _temp_storage():
        with tempfile.TemporaryDirectory(prefix="bench_mirror_layer_") as out:
            with _read_only():
                assert export_web.main(["--out", out]) == 0
            root = Path(out)
            index = (root / "index.html").read_text(encoding="utf-8")
            history = (root / "history" / "index.html").read_text(encoding="utf-8")
            stats = (root / "stats" / "index.html").read_text(encoding="utf-8")
            settings = (root / "settings" / "index.html").read_text(encoding="utf-8")

            # Скрипт зеркала подключён относительной ссылкой, файл в сборке
            assert 'src="static/js/mirror.js"' in index
            assert 'src="../static/js/mirror.js"' in settings
            assert 'src="../static/js/filter-panel.js"' in stats
            assert 'src="../static/js/filter-panel.js"' in settings
            script = (root / "static" / "js" / "mirror.js").read_text(encoding="utf-8")
            for marker in ("mirror-archived-rows", "mirror-table-wrap",
                           "mirror-stats-data", "HISTORY_PAGE_SIZE"):
                assert marker in script, f"mirror.js: нет маркера {marker}"

            # Навигационные onchange фильтров сняты (их роль играет mirror.js)
            for name, page in (("главная", index), ("история", history),
                               ("аналитика", stats), ("настройки", settings)):
                assert "this.form.submit()" not in page, f"{name}: остался onchange фильтров"

            # Остров реестра: полный состав, архивы отмечены
            island = _island_of(index, "mirror-models")
            assert set(island) == {"alpha", "beta", "gamma"}
            assert island["alpha"]["s"] == "active" and island["gamma"]["s"] == "archived"
            assert _island_of(history, "mirror-models") == island
            assert _island_of(settings, "mirror-models") == island
            assert set(_island_of(stats, "mirror-stats-data")) == {"alpha", "beta", "gamma"}

            # 3.1: номера рангов выделены в span под клиентскую перенумерацию
            assert '<span class="rank-num">1</span>' in index
            assert '<span class="rank-num">2</span>' in index

            # 3.1: шаблон архива главной несёт строку gamma (и только её)
            assert '<template id="mirror-archived-rows">' in index
            index_tpl = index.split('<template id="mirror-archived-rows">', 1)[1]
            index_tpl = index_tpl.split("</template>", 1)[0]
            assert "model/gamma/" in index_tpl, "в шаблоне архива нет ссылки на gamma"
            assert 'class="archived' in index_tpl, "строка архива без статусной пометки"
            assert "model/alpha/" not in index_tpl and "model/beta/" not in index_tpl

            # 3.2: шаблон архива матрицы «Настроек» — строка gamma с чекбоксами
            assert '<template id="mirror-archived-rows">' in settings
            settings_tpl = settings.split('<template id="mirror-archived-rows">', 1)[1]
            settings_tpl = settings_tpl.split("</template>", 1)[0]
            assert 'value="gamma||T-001"' in settings_tpl

            # 3.2: строки истории несут участников для серверных фильтров
            assert 'data-a="alpha" data-b="beta"' in history
    print("3.x mirror data layer: OK")


def _void_export_journal() -> str:
    """Журнал: две записи alpha vs beta и tombstone на первую."""
    base = datetime(2026, 1, 2, 10, 0, 0)
    events = []
    for seq, winner in ((1, "a"), (2, "b")):
        ts = base + timedelta(minutes=seq)
        events.append(json.dumps({
            "version": 1,
            "seq": seq,
            "task": "T-001",
            "matchup": f"T-001/{seq:03d}",
            "model_a": "alpha",
            "model_b": "beta",
            "model_a_id": "alpha",
            "model_b_id": "beta",
            "winner": winner,
            "date": ts.date().isoformat(),
            "recorded_at": ts.isoformat(timespec="seconds"),
        }, ensure_ascii=False))
    ts = base + timedelta(minutes=3)
    events.append(json.dumps({
        "version": 1,
        "seq": 3,
        "task": "T-001",
        "matchup": "T-001/003",
        "void_of": "T-001/001",
        "reason": "ошибка протокола",
        "date": ts.date().isoformat(),
        "recorded_at": ts.isoformat(timespec="seconds"),
    }, ensure_ascii=False))
    return "\n".join(events) + "\n"


def test_export_history_voided():
    """Волна 2: аннулированные строки в слепке; контролы записи недоступны."""
    with _temp_storage() as paths:
        _write(paths["journal"], _void_export_journal())
        data_cache.clear()

        with tempfile.TemporaryDirectory(prefix="bench_mirror_void_") as out:
            with _read_only():
                assert export_web.main(["--out", out]) == 0
            root = Path(out)
            history = (root / "history" / "index.html").read_text(encoding="utf-8")
            home = (root / "index.html").read_text(encoding="utf-8")

            # Аннулированная строка собрана в слепок: пометка, причина, участники
            assert "history-item-voided" in history, "нет пометки аннулированной строки"
            assert "ошибка протокола" in history, "нет причины аннулирования"
            rows = re.findall(
                r'<div data-a="[^"]*" data-b="[^"]*" class="history-item[^"]*"[^>]*>.*?</div>',
                history, re.S,
            )
            assert len(rows) == 2, f"строк истории: {len(rows)}"
            assert "history-item-voided" not in rows[0], "порядок ленты нарушен"
            assert "history-item-voided" in rows[1], "аннулированная строка не помечена"
            assert 'data-a="alpha" data-b="beta"' in rows[1], "нет участников у строки"

            # Контролы записи в зеркале недоступны, фильтр отображения остаётся
            assert 'action="/verdict/void"' not in history
            assert "Аннулировать" not in history
            assert "Показывать аннулированные" in history
            assert 'name="include_voided"' in history
            assert 'name="include_voided" value="1" checked' not in history, (
                "чекбокс аннулированных пришёл отмеченным — фильтр не скрыт по умолчанию"
            )
            assert "function swapModels" not in home
            assert 'name="date"' in home
            assert "Поменять A ↔ B" in home

            # Клиентский слой зеркала знает про аннулированные строки и фильтр
            script = (root / "static" / "js" / "mirror.js").read_text(encoding="utf-8")
            for marker in ("history-item-voided", "include_voided"):
                assert marker in script, f"mirror.js: нет маркера {marker}"
    print("wave2 export history voided: OK")


def test_export_task_pages():
    """Волна 4: страницы задач в слепке — без записи, ссылки разрешаются."""
    with _temp_storage():
        with tempfile.TemporaryDirectory(prefix="bench_mirror_task_") as out:
            with _read_only():
                assert export_web.main(["--out", out]) == 0
            root = Path(out)
            task_file = root / "task" / "T-001" / "index.html"
            assert task_file.is_file(), "нет страницы задачи в слепке"
            task = task_file.read_text(encoding="utf-8")

            # Шапка и прогресс на месте, действий записи нет
            assert "Smoke" in task and "Benchmark" in task
            assert 'aria-disabled="true">Записать вердикт по таску' in task
            assert 'href="/?task=' not in task and 'href="/task' not in task
            assert "task/T-001/md" not in task, "ссылка task.md просочилась в слепок"
            assert "void-form-open" not in task and "Аннулировать" not in task
            assert "page-jump" not in task and "history-pagination" not in task
            assert '<div class="stat-value">1 из 1</div>' in task
            assert "T-001/001" in task and 'class="badge-task"' not in task

            # Переходы: ID таски в настройках — на статическую страницу задачи
            settings = (root / "settings" / "index.html").read_text(encoding="utf-8")
            assert 'href="../task/T-001/"' in settings, "ID таски настроек без ссылки"
    print("wave4 export task pages: OK")


def test_export_stats_analytics():
    """Волна 6: слепок аналитики — карточка «Рейтинг», live-контролы вырезаны."""
    with _temp_storage():
        with tempfile.TemporaryDirectory(prefix="bench_mirror_stats_") as out:
            with _read_only():
                assert export_web.main(["--out", out]) == 0
            stats = (Path(out) / "stats" / "index.html").read_text(encoding="utf-8")

            # Карточка «Рейтинг» и SVG-ссылки на профили (разрешаются в файлы)
            assert "Рейтинг" in stats and "Динамика ELO" in stats
            assert 'aria-label="Рейтинг: 2 моделей' in stats
            assert 'href="../model/alpha/"' in stats
            assert "line-legend" in stats and "нет матчей в периоде" not in stats

            # Live-контролы выбора линий и периода в слепке не рендерятся
            assert "lines-form" not in stats
            assert 'name="lines"' not in stats and 'name="period"' not in stats
            assert "lines-presets" not in stats
            assert "lines-picker" not in stats

            # Удалённые блоки в слепке отсутствуют
            assert "Активность по дням" not in stats
            assert "Матрица пар" not in stats
            assert "Исходы" not in stats
            assert "Интервалы рейтинга" not in stats
            assert "Распределение Elo" not in stats

            # «Рейтинг» статичен: фильтры страницы в слепке не меняют SVG
            assert 'class="chart chart-rating"' in stats

            # Остальные карточки на месте
            assert "Агенты и компании" in stats and "card-subtitle" in stats
            assert "Взлёты и падения" in stats and "delta-list" in stats
            assert "Сила оппозиции" in stats
            assert "Остывшие" not in stats

            # Волна 5: бары рейтинга и линии A2 кликабельны (ссылки моделей
            # разрешаются в файлы)
            assert 'class="dist-link"' in stats, "бары рейтинга слепка без ссылок"
            assert 'class="chart-line-hit"' in stats, "линии A2 слепка без ссылок"

            # Таблица «Силы оппозиции» собрана со всех страниц: каждая
            # активная модель — ровно одна строка
            opp = stats.split('id="opposition"', 1)[1]
            opp_models = re.findall(r'<td><a href="\.\./model/([^/]+)/">', opp)
            assert len(opp_models) == len(set(opp_models)), "строки оппозиции задвоены"
            assert len(opp_models) == 2, f"в слепке {len(opp_models)} строк оппозиции"
    print("wave6 export stats analytics: OK")


def test_check_output_violations():
    with tempfile.TemporaryDirectory(prefix="bench_mirror_bad_") as out:
        root = Path(out)
        (root / "bad.html").write_text(
            '<a href="/root">1</a>'
            '<a href="https://example.com/x">2</a>'
            '<a href="missing.html">3</a>'
            '<form method="POST" action="/x"></form>'
            "маркер __root__",
            encoding="utf-8",
        )
        errors = export_web.check_output(root, 2)
        text = "\n".join(errors)
        assert "корневой адрес" in text
        assert "внешний ресурс" in text
        assert "файл не найден" in text
        assert "POST-форма" in text
        assert "остаточный маркер" in text
        assert len(errors) >= 5, errors
    print("2.3 check violations: OK")


def test_export_history_threshold_warning():
    with _temp_storage() as paths:
        count = export_web.HISTORY_WARN_RECORDS + 100
        _write(paths["journal"], _big_journal(count))
        data_cache.clear()

        buffer = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="bench_mirror_big_") as out:
            with redirect_stdout(buffer):
                with _read_only():
                    code = export_web.main(["--out", out])
            assert code == 0, "сборка с большой историей упала"
            printed = buffer.getvalue()
            assert "ПРЕДУПРЕЖДЕНИЕ" in printed and "история" in printed, printed
            assert "Слепок собран" in printed, printed
            history_html = (Path(out) / "history" / "index.html").read_text(
                encoding="utf-8")
            rows = history_html.count('<div data-a="')
            assert rows == count, f"история неполная: {rows} из {count}"
    print("2.3 history threshold warning: OK")


def test_export_profile():
    """Волна 4: слепок профиля — место, последний матч, покрытие, без H2H-контролов."""
    with _temp_storage():
        with tempfile.TemporaryDirectory(prefix="bench_mirror_profile_") as out:
            with _read_only():
                assert export_web.main(["--out", out]) == 0
            page = (Path(out) / "model" / "alpha" / "index.html").read_text(
                encoding="utf-8")

            # 5.1: место/тренд и «Последний матч» со ссылкой на вердикт
            assert 'class="profile-rank">Место 1 из 2</span>' in page
            assert "мало игр для тренда" in page
            assert 'id="profile-last-match"' in page
            assert 'href="../../history/?v=1#v-1"' in page

            # Волна 5: точки графика динамики ведут к записям вердиктов
            assert 'class="chart-dot-link"' in page, "точки графика слепка без ссылок"

            # 5.3: кнопка «Показать в истории» ведёт на экспортированную историю
            assert 'href="../../history/?model=alpha"' in page
            assert "Показать в истории" in page

            # 5.2: покрытие по таскам ведёт на экспортированные страницы задач
            assert 'href="../../task/T-001/"' in page

            # 5.3: поиск и сортировка H2H в слепке не рендерятся,
            # таблица — в порядке по умолчанию
            assert "h2h-controls" not in page
            assert "sort-link" not in page
            assert "aria-sort" not in page
    print("wave4 export profile: OK")


def test_export_captions_toggle():
    """Слепок повторяет переключатель «Отражать агент-компанию».

    Подписи в статике предрендерены (это данные), но по умолчанию скрыты:
    класс «captions-off» стоит в разметке, а показ ведёт клиентский слой
    по `?captions=show` — как в живой консоли.
    """
    with _temp_storage():
        with tempfile.TemporaryDirectory(prefix="bench_mirror_captions_") as out:
            with _read_only():
                assert export_web.main(["--out", out]) == 0
            root = Path(out)
            index = (root / "index.html").read_text(encoding="utf-8")
            history = (root / "history" / "index.html").read_text(encoding="utf-8")

            # Флажок «Отражать агент-компанию» есть в панели настроек.
            assert 'name="captions" value="show"' in index, "в слепке нет флажка подписи"
            assert 'name="captions" value="show"' in history, "в слепке истории нет флажка"

            # Подписи предрендерены (данные), но по умолчанию скрыты.
            assert "Prov · Agent" in index, "подписи не попали в статику"
            assert 'class="captions-off"' in index, "нет класса «подписи скрыты»"
            css = (root / "static" / "css" / "console.css").read_text(encoding="utf-8")
            assert "body.captions-off .model-caption" in css, "нет правила гашения подписи"

            # В запечённых ссылках параметра нет: состояние ведёт клиент.
            assert "captions=show" not in index, "в ссылках слепка остался параметр подписей"

            # Клиентский слой знает про параметр и умеет его применять.
            script = (root / "static" / "js" / "mirror.js").read_text(encoding="utf-8")
            assert 'input[name="captions"]' in script, "mirror.js не знает про флажок"
            assert 'params.get("captions")' in script, "mirror.js не читает параметр"
            assert "applyCaptions" in script, "mirror.js не применяет состояние подписей"

            # Остров реестра сохраняет подписи (это данные, а не вид).
            island = _island_of(index, "mirror-models")
            assert island["alpha"]["c"] == "Prov · Agent", "подпись не сохранена в острове"
    print("export captions toggle: OK")


if __name__ == "__main__":
    test_read_only_two_modes()
    test_read_only_inert_controls()
    test_read_only_no_cache_write()
    test_export_output_and_determinism()
    test_export_links_and_markers()
    test_export_queue_pages()
    test_export_mirror_layer()
    test_export_history_voided()
    test_export_task_pages()
    test_export_stats_analytics()
    test_export_profile()
    test_export_captions_toggle()
    test_check_output_violations()
    test_export_history_threshold_warning()
    print("\nALL EXPORT TESTS PASSED")
