#!/usr/bin/env python3
"""
test_data_cache.py — memo-слой консоли и роуты на tmp-фикстурах.

Проверяет:
  * 2.1 — DataKey реагирует на правку журнала и каждого управляющего
    файла (перезапись того же размера ловится по mtime); builder не
    перезапускается при неизменном ключе; clear() сбрасывает мемо;
    параллельные вызовы собирают значение один раз.
  * 2.2 — повторный запрос производных не перечитывает журнал
    (счётчики разбора и хэширования); ensure_index отдаёт тот же
    объект без перечитывания index.json.
  * 2.4 — все GET-роуты отдают 200 на фикстурах; POST /verdict пишет
    событие в журнал, после чего главная снова рендерится.
  * 2.6 — очередь `/settings` постранична (100 строк): сквозная
    нумерация, счётчик = все открытые ячейки, номер вне диапазона
    приводится к граничной странице, первая строка = топ-1.
  * 2.7 — виджет пагинации `/history` и очереди: окно ±2 вокруг
    текущей страницы, троеточия в разрывах (разрыв в одну страницу
    склеивается номером), неактивные стрелки на краях; алгоритм
    pagination_items (страниц <= 10 — все номера подряд).
  * Волна 1 (UI): контраст токенов подписей (AA ≥ 4.5:1), роли
    сообщений, scope="col" у заголовков таблиц, варианты карточки
    рекомендации («Другая пара»), счётчик рематчей, единая сводка,
    компактная плашка прогресса при 100%, favicon и подтверждения.
  * Волна 2 (UI): лента истории с аннулированными (include_voided,
    merge_history_feed, счётчик, перечёркнутая строка с причиной),
    форма «Аннулировать» в строке и в success-строке (POST /verdict/void,
    защита next, отказ без причины), контекст формы после записи
    (победитель в A, таск/дата, matchup_id), дата вердикта, подсказка
    личных встреч (JSON-остров) и обмен A ↔ B.
  * Волна 3 (данные и масштаб): поисковые фильтры истории (task/from/to/
    outcome/pair/only_voided, счётчик «найдено», пустое состояние),
    самодостаточная строка (ссылки моделей, бейдж таска, метка исхода,
    чип matchup_id, якорь id="v-<seq>") и редиректы `?v=`, поле «страница
    №» и «в конец» с сохранением фильтров, поиск и сортировка рейтинга
    (aria-sort, стабильные места), экспорт выборки CSV/JSON, деградация
    слепка (нет поиска, сортировки, комбобокса и экспорта).
  * Волна 4 (глубина): страница задачи /task/<id> (шапка, прогресс,
    список вердиктов 20/стр с пагинацией, 404, task.md) и переходы на
    неё из настроек, истории, очереди и карточки рекомендации; аналитика
    /stats A1–A8 (интервалы, динамика, активность, матрица, группы, ΔELO,
    оппозиция, исходы) и профиль модели (место/тренд, последний матч,
    покрытие по таскам, метаданные, поиск и сортировка «Личных встреч»).
  * Версия и сборка консоли: подвал всех страниц и секция «О консоли»
    настроек показывают тег последнего релиза (vX.Y.Z) и время коммита
    по Минску с меткой МСК; резолверы нормализуют источники и откатываются
    на файл версии.

Запуск: python tools/test_data_cache.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_cache
import elo
import lookups
import render_helpers
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


def _git(root: Path, *args: str) -> None:
    """Команда git в тестовом репозитории (тихий вывод, ошибка — исключение)."""
    subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True,
    )


@contextmanager
def _temp_storage():
    """tmp-хранилище с подменой путей elo/server/lookups на время теста."""
    with tempfile.TemporaryDirectory(prefix="bench_cache_") as tmp_str:
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


def test_key_changes_per_file():
    with _temp_storage() as paths:
        key = data_cache.data_key()
        assert data_cache.data_key() == key, "ключ должен быть стабилен без правок"

        # Любой управляющий файл меняет ключ (дописывание меняет размер)
        for name in ("models", "flags", "settings", "lookups"):
            path = paths[name]
            path.write_text(
                path.read_text(encoding="utf-8") + "\n", encoding="utf-8",
            )
            new_key = data_cache.data_key()
            assert new_key != key, f"правка {name} не изменила ключ"
            key = new_key

        # Журнал: дозапись строки
        with paths["journal"].open("a", encoding="utf-8") as f:
            f.write(JOURNAL_LINE)
        new_key = data_cache.data_key()
        assert new_key != key, "дозапись журнала не изменила ключ"
        key = new_key

        # Журнал: перезапись того же размера — ловится по mtime
        text = paths["journal"].read_text(encoding="utf-8")
        paths["journal"].write_text(
            text.replace('"winner": "a"', '"winner": "b"', 1),
            encoding="utf-8",
        )
        st = paths["journal"].stat()
        os.utime(paths["journal"], ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        new_key = data_cache.data_key()
        assert new_key != key, "перезапись журнала не изменила ключ"
        key = new_key

        # Возврат к прежнему содержимому — снова другой ключ (дайджест вернулся)
        paths["journal"].write_text(text, encoding="utf-8")
        st = paths["journal"].stat()
        os.utime(paths["journal"], ns=(st.st_atime_ns, st.st_mtime_ns + 2_000_000))
        assert data_cache.data_key() != key
    print("2.1 key changes per file: OK")


def test_builder_runs_once():
    with _temp_storage() as paths:
        calls: list[str] = []

        def builder(name: str):
            calls.append(name)
            return {"name": name, "n": len(calls)}

        v1 = data_cache.cached("x", lambda: builder("x"))
        v2 = data_cache.cached("x", lambda: builder("x"))
        assert v1 is v2, "повторный вызов должен вернуть тот же объект"
        assert calls == ["x"], f"builder перезапущен: {calls}"

        v3 = data_cache.cached("y", lambda: builder("y"))
        assert v3 is not v1 and calls == ["x", "y"]

        # Смена ключа сбрасывает всё: пересобираются оба имени
        paths["models"].write_text(MODELS_YAML + "\n", encoding="utf-8")
        v4 = data_cache.cached("x", lambda: builder("x"))
        assert v4 is not v1, "после смены ключа builder не перезапустился"
        v5 = data_cache.cached("y", lambda: builder("y"))
        assert v5 is not v3, "после смены ключа значение 'y' осталось старым"
        assert calls == ["x", "y", "x", "y"]
    print("2.1 builder runs once: OK")


def test_clear_resets():
    with _temp_storage() as _paths:
        calls: list[int] = []

        def builder():
            calls.append(1)
            return object()

        first = data_cache.cached("z", builder)
        data_cache.clear()
        second = data_cache.cached("z", builder)
        assert second is not first
        assert len(calls) == 2
    print("2.1 clear resets: OK")


def test_parallel_cached_single_build():
    with _temp_storage() as _paths:
        calls: list[int] = []
        results: list[int] = []
        errors: list[BaseException] = []

        def builder():
            time.sleep(0.1)
            calls.append(1)
            return 123

        def worker():
            try:
                results.append(data_cache.cached("slow", builder))
            except BaseException as e:  # noqa: BLE001 — тест печатает ошибку
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, f"ошибки потоков: {errors}"
        assert results == [123] * 4
        assert len(calls) == 1, f"builder выполнен {len(calls)} раз"
    print("2.1 parallel cached single build: OK")


def test_requests_do_not_reread_journal():
    with _temp_storage() as paths:
        reads = {"parse": 0, "digest": 0}
        real_load = elo.load_matchups
        real_digest = elo.matchups_digest

        def counting_load():
            reads["parse"] += 1
            return real_load()

        def counting_digest():
            reads["digest"] += 1
            return real_digest()

        saved_server_load = server.load_matchups
        server.load_matchups = counting_load
        elo.matchups_digest = counting_digest
        try:
            server.get_pair_stats()
            server.get_pair_stats()
            assert reads == {"parse": 1, "digest": 1}, (
                f"повторный запрос перечитал журнал: {reads}"
            )

            # Правка models.yaml: memo пересобирается, журнал парсится
            # заново, но дайджест не перехэшируется (stat не менялся)
            paths["models"].write_text(MODELS_YAML + "\n", encoding="utf-8")
            server.get_pair_stats()
            assert reads == {"parse": 2, "digest": 1}, (
                f"журнал/хэш пересобраны некорректно: {reads}"
            )

            # Дозапись журнала: stat изменился, дайджест пересчитан
            with paths["journal"].open("a", encoding="utf-8") as f:
                f.write(JOURNAL_LINE)
            server.get_pair_stats()
            assert reads == {"parse": 3, "digest": 2}, (
                f"правка журнала не инвалидировала memo: {reads}"
            )

            # ensure_index без перечитывания index.json
            idx1 = server.ensure_index()
            idx2 = server.ensure_index()
            assert idx1 is idx2, "ensure_index перечитал/пересобрал index"
            assert paths["index"].exists(), "index.json не сохранён"
        finally:
            server.load_matchups = saved_server_load
            elo.matchups_digest = real_digest
    print("2.2 requests do not reread journal: OK")


def test_routes_smoke():
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        get_routes = [
            "/",
            "/history",
            "/stats",
            "/settings",
            "/add",
            "/model/alpha",
            "/model/gamma",
            "/edit/alpha",
            "/add_task",
            "/edit_task/T-001",
        ]
        for url in get_routes:
            resp = client.get(url)
            assert resp.status_code == 200, (
                f"GET {url} → {resp.status_code}\n{resp.get_data(as_text=True)[:500]}"
            )

        resp = client.get("/model/nope")
        assert resp.status_code == 404, f"GET /model/nope → {resp.status_code}"

        # Волна 1: favicon живой консоли и компактная плашка при 100%
        home_html = client.get("/").get_data(as_text=True)
        assert '<link rel="icon" href="/static/icon.svg">' in home_html, (
            "нет favicon живой консоли"
        )
        assert "Прогресс прогона — 100% · все пары закрыты" in home_html, (
            "плашка не свернулась в строку при 100%"
        )
        assert "scrollIntoView" in home_html, "«Прогнать» потеряла прокрутку к форме"

        # Пустая очередь при полном покрытии объясняет рематч
        settings_html = client.get("/settings").get_data(as_text=True)
        assert "открытых: 0" in settings_html
        assert "рематчей: 1" in settings_html
        assert "Открытых пар нет. Ниже — матч для доп. точности (рематч)." in settings_html

        # Подтверждение удаления значения справочника — на форме
        assert 'onsubmit="return confirmDelete(this)"' in settings_html
        assert 'data-value="Agent"' in settings_html
        assert "function confirmDelete" in settings_html

        # Подтверждение архивации модели — на форме редактирования
        edit_html = client.get("/edit/alpha").get_data(as_text=True)
        assert 'onsubmit="return confirmModelStatus(this)"' in edit_html
        assert 'data-status="active"' in edit_html
        assert 'data-name="Alpha"' in edit_html
        assert "function confirmModelStatus" in edit_html

        # Запись вердикта через форму: событие T-001/002 в журнале
        resp = client.post("/verdict", data={
            "model_a": "alpha", "model_b": "beta",
            "winner": "b", "task": "T-001",
        })
        assert resp.status_code == 302, f"POST /verdict → {resp.status_code}"
        events = elo.load_matchups()
        assert any(e.get("matchup") == "T-001/002" for e in events), (
            "событие T-001/002 не записано в журнал"
        )

        # Сообщение об успехе после редиректа озвучивается (role=status)
        ok_html = client.post("/verdict", data={
            "model_a": "alpha", "model_b": "beta",
            "winner": "a", "task": "T-001",
        }, follow_redirects=True).get_data(as_text=True)
        assert 'class="alert alert-success" role="status"' in ok_html, (
            "у сообщения об успехе нет role=status"
        )

        # Ошибка формы — role=alert (состояние журнала не меняется)
        err_html = client.post(
            "/verdict", data={}, follow_redirects=True,
        ).get_data(as_text=True)
        assert 'class="alert alert-error" role="alert"' in err_html, (
            "у сообщения об ошибке нет role=alert"
        )

        # После записи главная перерисовывается на новом состоянии
        resp = client.get("/")
        assert resp.status_code == 200
        assert paths["index"].exists()
    print("2.4 routes smoke: OK")


def test_version_badge():
    """Версия и сборка: подвал и «О консоли»; фолбэки резолверов."""
    version = server.app_version()
    assert re.fullmatch(r"v\d+\.\d+\.\d+", version), (
        f"версия консоли не в формате релизного тега: {version!r}"
    )
    build = server.app_build_time()
    assert re.fullmatch(r"\d{2}\.\d{2}\.\d{4} \d{2}:\d{2} МСК", build), (
        f"сборка консоли не в формате даты-времени: {build!r}"
    )
    # Фиксированные моменты: результат не зависит от зоны тестовой машины
    assert server._format_build_time(
        datetime.fromisoformat("2026-10-19T18:23:54+00:00")
    ) == "19.10.2026 21:23 МСК", "UTC-момент не приведён к минскому времени"
    assert server._format_build_time(
        datetime.fromisoformat("2026-10-19T21:23:54+03:00")
    ) == "19.10.2026 21:23 МСК", "момент +03 не совпал с минским временем"
    version_mark = f'<span class="footer-version" title="Версия консоли">{version}</span>'
    build_mark = f'<span class="footer-build" title="Дата и время сборки">сборка {build}</span>'
    with _temp_storage():
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        for url in ("/", "/history", "/settings", "/model/alpha", "/add"):
            html = client.get(url).get_data(as_text=True)
            assert version_mark in html, f"{url}: в подвале нет версии {version}"
            assert build_mark in html, f"{url}: в подвале нет сборки {build}"
            assert 'class="brand-version"' not in html, (
                f"{url}: бейдж версии остался в шапке"
            )
        settings = client.get("/settings").get_data(as_text=True)
        assert f"<dt>Версия</dt><dd>{version}</dd>" in settings, (
            "/settings: секция «О консоли» без версии"
        )
        assert f"<dt>Сборка</dt><dd>{build}</dd>" in settings, (
            "/settings: секция «О консоли» без сборки"
        )
        assert "по минскому времени" in settings, (
            "/settings: подсказка «О консоли» без минского времени"
        )

        # Слепок витрины (read-only) показывает те же метаданные
        saved = bool(server.app.config.get("READ_ONLY"))
        server.app.config["READ_ONLY"] = True
        try:
            html = client.get("/").get_data(as_text=True)
            assert version_mark in html, "read-only слепок без версии в подвале"
            assert build_mark in html, "read-only слепок без сборки в подвале"
        finally:
            server.app.config["READ_ONLY"] = saved

    # Резолверы: без источников — пусто (блоки скрыты); фолбэки нормализуются
    with tempfile.TemporaryDirectory(prefix="bench_version_") as tmp_str:
        root = Path(tmp_str)
        assert server.resolve_app_version(root) == "", (
            "каталог без версии не должен давать строку"
        )
        assert server.resolve_build_time(root) == "", (
            "каталог без git и файла версии не должен давать строку"
        )
        version_file = root / "pyproject.toml"
        _write(version_file, '[project]\nversion = "1.2.3"\n')
        assert server.resolve_app_version(root) == "v1.2.3", (
            "файл версии не нормализован к vX.Y.Z"
        )
        # Фиксированный epoch: по Минску 06.05.2024 07:08 — тест не зависит
        # от часового пояса машины.
        moment = datetime(2024, 5, 6, 7, 8, tzinfo=server.MINSK_TZ)
        os.utime(version_file, (moment.timestamp(), moment.timestamp()))
        assert server.resolve_build_time(root) == "06.05.2024 07:08 МСК", (
            "фолбэк без git не взял время файла версии"
        )

        # Git-источники приоритетнее: версия — тег, сборка — время коммита
        if shutil.which("git") is None:
            print("    (git недоступен — проверки git-фолбэков пропущены)")
        else:
            _write(root / "readme.txt", "x\n")
            _git(root, "init", "-q")
            _git(root, "add", ".")
            _git(root, "-c", "user.name=Test", "-c", "user.email=test@example.com",
                 "commit", "-q", "-m", "init")
            assert server.resolve_app_version(root) == "v1.2.3", (
                "без тегов версия должна браться из файла"
            )
            commit_iso = subprocess.run(
                ["git", "show", "-s", "--format=%cI", "HEAD"],
                cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            expected = datetime.fromisoformat(commit_iso).astimezone(
                server.MINSK_TZ
            ).strftime("%d.%m.%Y %H:%M МСК")
            assert server.resolve_build_time(root) == expected, (
                "сборка из git-репозитория не совпала со временем HEAD"
            )
            _git(root, "tag", "v9.9.9")
            assert server.resolve_app_version(root) == "v9.9.9", (
                "тег релиза должен побеждать файл версии"
            )
    print("версия и сборка консоли: OK")


def test_merge_history_feed_unit():
    """merge_history_feed: порядок по seq, пометки voided, пустая секция."""
    applied = [
        {"matchup": "T-001/001", "seq": 1, "model_a_id": "alpha", "model_b_id": "beta"},
        {"matchup": "T-001/003", "seq": 3, "model_a_id": "alpha", "model_b_id": "beta"},
    ]
    voided = [{
        "matchup": "T-001/002", "seq": 2, "model_a_id": "alpha", "model_b_id": "gamma",
        "void": {"reason": "ошибка", "date": "2026-01-03",
                 "recorded_at": "2026-01-03T10:00:00+03:00", "matchup": "T-001/004"},
    }]
    feed = render_helpers.merge_history_feed(applied, voided)
    assert [h["matchup"] for h in feed] == ["T-001/003", "T-001/002", "T-001/001"]
    assert not feed[0].get("voided") and not feed[2].get("voided")
    assert feed[1]["voided"] is True
    # исходные словари не мутируются
    assert "voided" not in applied[0] and "voided" not in voided[0]

    # Пустая секция аннулированных: только применённые в обратном порядке
    feed2 = render_helpers.merge_history_feed(applied)
    assert [h["matchup"] for h in feed2] == ["T-001/003", "T-001/001"]

    # format_elo_history: passthrough matchup/voided/void_str с причиной и датой
    items = render_helpers.format_elo_history(
        feed, {"alpha": "Alpha", "beta": "Beta", "gamma": "Gamma"}
    )
    assert items[1]["voided"] is True and items[1]["matchup"] == "T-001/002"
    assert "аннулировано" in items[1]["void_str"]
    assert "ошибка" in items[1]["void_str"]
    assert items[0]["voided"] is False and items[0]["void_str"] == ""
    print("wave2 merge history feed: OK")


def test_void_route():
    """POST /verdict/void: успех, пустая причина, чужой id, повтор, защита next."""
    with _temp_storage() as _paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # Пустая причина: ошибка без изменения журнала
        resp = client.post("/verdict/void", data={
            "matchup_id": "T-001/001", "reason": "   ", "next": "/history",
        })
        assert resp.status_code == 302
        assert "error=" in resp.headers["Location"]
        assert len(elo.load_matchups()) == 1

        # Неизвестный вердикт: ошибка без изменения журнала
        resp = client.post("/verdict/void", data={
            "matchup_id": "T-001/999", "reason": "нет такого", "next": "/history",
        })
        assert "error=" in resp.headers["Location"]
        assert len(elo.load_matchups()) == 1

        # Успех: tombstone в журнале; внешний next игнорируется
        resp = client.post("/verdict/void", data={
            "matchup_id": "T-001/001", "reason": "ошибка записи",
            "next": "//evil.example/x",
        })
        assert resp.status_code == 302
        loc = resp.headers["Location"]
        assert loc.startswith("/history?") and "evil" not in loc, loc
        assert "success=" in loc
        events = elo.load_matchups()
        assert len(events) == 2
        assert events[1]["void_of"] == "T-001/001"
        assert events[1]["reason"] == "ошибка записи"

        # Повторное аннулирование отклонено без нового события
        resp = client.post("/verdict/void", data={
            "matchup_id": "T-001/001", "reason": "ещё раз", "next": "/history",
        })
        assert "error=" in resp.headers["Location"]
        assert len(elo.load_matchups()) == 2

        # Аннулирование tombstone-события отклонено
        resp = client.post("/verdict/void", data={
            "matchup_id": "T-001/002", "reason": "удалить аудит", "next": "/history",
        })
        assert "error=" in resp.headers["Location"]
        assert len(elo.load_matchups()) == 2

        # Локальный next с фильтром сохраняется
        client.post("/verdict", data={
            "model_a": "alpha", "model_b": "beta", "winner": "b",
            "task": "T-001", "date": "2026-01-03",
        })
        resp = client.post("/verdict/void", data={
            "matchup_id": "T-001/003", "reason": "дубль матча",
            "next": "/history?model=alpha",
        })
        loc = resp.headers["Location"]
        assert loc.startswith("/history?model=alpha&"), loc
        assert "success=" in loc
    print("wave2 void route: OK")


def test_history_voided_feed():
    """История: include_voided, счётчик, перечёркнутая строка и форма аннулирования."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # Второй вердикт, чтобы после аннулирования осталась применённая запись
        client.post("/verdict", data={
            "model_a": "alpha", "model_b": "beta", "winner": "a",
            "task": "T-001", "date": "2026-01-03",
        })
        client.post("/verdict/void", data={
            "matchup_id": "T-001/001", "reason": "ошибка протокола",
            "next": "/history",
        })

        # По умолчанию аннулированных в ленте нет, чекбокс выключен
        html = client.get("/history").get_data(as_text=True)
        assert "history-item-voided" not in html
        assert "Показывать аннулированные" in html
        assert 'name="include_voided" value="1" checked' not in html

        # С фильтром: строка видна, перечёркнута, с причиной и датой; счётчик
        html = client.get("/history?include_voided=1").get_data(as_text=True)
        assert "history-item-voided" in html
        assert "аннулировано" in html and "ошибка протокола" in html
        assert "Всего записей: 2 · аннулированных: 1" in html
        assert 'name="include_voided" value="1" checked' in html

        rows = re.findall(r'<div class="history-item[^"]*"[^>]*>.*?</div>', html, re.S)
        assert len(rows) == 2, [r[:90] for r in rows]
        # плоская разметка: во вложенных div-ах нет (экспорт зеркала)
        assert rows[0].count("<div") == 1 and rows[1].count("<div") == 1
        # применённая строка: маркер и форма аннулирования
        assert "history-item-voided" not in rows[0]
        assert 'action="/verdict/void"' in rows[0]
        assert 'value="T-001/002"' in rows[0]
        # аннулированная строка: маркер есть, формы нет
        assert "history-item-voided" in rows[1]
        assert 'action="/verdict/void"' not in rows[1]
        assert "ошибка протокола" in rows[1]

        # Пагинация сохраняет include_voided
        _write(paths["journal"], _history_journal(30))
        data_cache.clear()
        client.post("/verdict/void", data={
            "matchup_id": "T-001/001", "reason": "дубль", "next": "/history",
        })
        html = client.get("/history?include_voided=1").get_data(as_text=True)
        assert (
            "include_voided=1&amp;page=2" in html
            or "page=2&amp;include_voided=1" in html
        ), "ссылка пагинации не сохраняет include_voided"
    print("wave2 history voided feed: OK")


def test_verdict_context_and_actions():
    """Форма: дата, контекст после записи, success-строка с «Отменить»."""
    with _temp_storage() as _paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # Невалидная дата: ошибка без события
        resp = client.post("/verdict", data={
            "model_a": "alpha", "model_b": "beta", "winner": "a",
            "task": "T-001", "date": "2026-13-40",
        })
        assert resp.status_code == 302 and "error=" in resp.headers["Location"]
        assert len(elo.load_matchups()) == 1

        # Запись с датой: событие несёт дату, редирект — контекст и matchup_id
        resp = client.post("/verdict", data={
            "model_a": "alpha", "model_b": "beta", "winner": "b",
            "task": "T-001", "date": "2026-01-03",
        })
        loc = resp.headers["Location"]
        assert "model_a=beta" in loc, loc
        assert "task=T-001" in loc and "date=2026-01-03" in loc, loc
        assert "matchup_id=T-001" in loc, loc
        events = elo.load_matchups()
        assert events[-1]["date"] == "2026-01-03"

        # Success-строка: поле даты, «Отменить» с формой и «Записать ещё»
        html = client.get(loc).get_data(as_text=True)
        assert 'value="2026-01-03"' in html
        assert "Отменить" in html and "Записать ещё" in html
        assert 'action="/verdict/void"' in html
        assert 'value="T-001/002"' in html
        assert "function writeMore" in html

        # Ничья: в поле A остаётся прежняя A
        resp = client.post("/verdict", data={
            "model_a": "beta", "model_b": "alpha", "winner": "draw",
            "task": "T-001", "date": "2026-01-04",
        })
        assert "model_a=beta" in resp.headers["Location"]
    print("wave2 verdict context and actions: OK")


def test_pair_hints_island():
    """Подсказка личных встреч: JSON-остров, обмен сторон, именованные кнопки."""
    with _temp_storage() as _paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/").get_data(as_text=True)
        assert 'id="pair-hints"' in html
        m = re.search(
            r'<script type="application/json" id="pair-hints">(.*?)</script>',
            html, re.S,
        )
        assert m, "JSON-остров подсказки не найден"
        payload = json.loads(m.group(1))
        assert payload["alpha|beta"] == {"g": 1, "x": 1, "y": 0}

        # Элементы и функции подсказки/обмена в форме
        assert 'id="pairHint"' in html
        assert "Поменять A ↔ B" in html
        assert "function swapModels" in html
        assert "function updatePairHint" in html
        assert "function updateOutcomeLabels" in html
        assert "function optionName" in html
        # Фокус при загрузке — на поле A (в волне 3 — на input комбобокса)
        assert "const modelAEl = document.getElementById('modelA');" in html
        assert "target.focus()" in html
        assert "не встречались" in html

        # Невалидные параметры игнорируются: дата — сегодня, таск — current
        from datetime import date as date_cls
        today = date_cls.today().isoformat()
        html2 = client.get(
            "/?model_a=nope&model_b=beta&task=nope&date=2026-99-99"
        ).get_data(as_text=True)
        assert f'value="{today}"' in html2
        assert '<option value="nope" selected' not in html2
        assert re.search(r'<option value="beta" data-agent="[^"]*" selected>', html2)
        assert '<option value="T-001" selected>' in html2
    print("wave2 pair hints island: OK")


def test_wave2_integration_scenario():
    """Волна 2 end-to-end: запись с датой → отмена из success → лента → индекс."""
    with _temp_storage() as paths:
        _write(paths["journal"], "")
        data_cache.clear()
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # 1. Запись вердикта с датой: success-строка несёт форму отмены
        resp = client.post("/verdict", data={
            "model_a": "alpha", "model_b": "beta", "winner": "a",
            "task": "T-001", "date": "2026-02-05",
        })
        assert resp.status_code == 302
        alert = client.get(resp.headers["Location"]).get_data(as_text=True)
        assert "Записано" in alert and "Записать ещё" in alert
        form = re.search(
            r'action="/verdict/void"[^>]*>.*?name="matchup_id" value="([^"]+)"'
            r'.*?name="next" value="([^"]+)"',
            alert, re.S,
        )
        assert form, "success-строка без формы отмены"
        matchup_id = form.group(1)
        next_path = form.group(2).replace("&amp;", "&")
        assert matchup_id == "T-001/001"

        # 2. Отмена тем же маршрутом, что отправит браузер
        resp = client.post("/verdict/void", data={
            "matchup_id": matchup_id, "reason": "дубль после отмены",
            "next": next_path,
        })
        assert resp.status_code == 302
        loc = resp.headers["Location"]
        assert "success=" in loc and "matchup_id=" not in loc
        assert "model_a=alpha" in loc and "task=T-001" in loc, loc
        assert "date=2026-02-05" in loc, loc
        back = client.get(loc).get_data(as_text=True)
        assert "Вердикт T-001/001 аннулирован" in back
        assert "Записать ещё" in back
        assert 'action="/verdict/void"' not in back, "повторная отмена предлагается снова"

        # 3. Лента истории с фильтром показывает аннулированную запись
        html = client.get("/history?include_voided=1&model=alpha").get_data(as_text=True)
        assert "history-item-voided" in html
        assert "аннулировано" in html and "дубль после отмены" in html
        assert "Всего записей: 1 · аннулированных: 1" in html

        # 4. Журнал и индекс согласованы: порядок seq, tombstone, счётчики
        events = elo.load_matchups()
        assert [e.get("matchup") for e in events] == ["T-001/001", "T-001/002"]
        assert [e.get("seq") for e in events] == [1, 2]
        assert events[1]["void_of"] == "T-001/001"
        assert events[1]["reason"] == "дубль после отмены"

        idx = server.ensure_index()
        summary = idx["matchups_summary"]
        assert summary["total"] == 2 and summary["voided"] == 1
        assert summary["applied"] == 0 and summary["tombstone"] == 1
        assert idx["elo_history"] == []
        vh = idx["voided_history"]
        assert len(vh) == 1, vh
        assert vh[0]["matchup"] == "T-001/001" and vh[0]["seq"] == 1
        assert vh[0]["date"] == "2026-02-05"
        assert vh[0]["elo_a"] == {"before": 1200, "after": 1220, "delta": 20}
        assert vh[0]["void"]["matchup"] == "T-001/002"
        assert vh[0]["void"]["reason"] == "дубль после отмены"
    print("wave2 integration scenario: OK")


def test_pagination_items_window():
    """Окно виджета: первая/последняя/текущая ±2, троеточия, склейка разрыва."""
    items = render_helpers.pagination_items
    assert items(1, 1) == [1]
    assert items(1, 2) == [1, 2]
    assert items(2, 2) == [1, 2]
    assert items(5, 8) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert items(10, 10) == list(range(1, 11))
    # pages = 11: окно уже действует, троеточия с обеих сторон
    assert items(6, 11) == [1, None, 4, 5, 6, 7, 8, None, 11]
    # Длинная история: начало, середина, конец
    assert items(1, 27) == [1, 2, 3, None, 27]
    assert items(14, 27) == [1, None, 12, 13, 14, 15, 16, None, 27]
    assert items(27, 27) == [1, None, 25, 26, 27]
    # Разрыв ровно в одну страницу печатается номером, больший — троеточием
    assert items(5, 12) == [1, 2, 3, 4, 5, 6, 7, None, 12]
    print("2.7 pagination items window: OK")


def _history_journal(events: int, winners: str | None = None) -> str:
    """Журнал alpha vs beta с ELO-снэпшотами, посчитанными тем же реплеем.

    winners — строка исходов 'a'/'b' по событию (по умолчанию чередование).
    """
    elo_a = elo_b = elo.DEFAULT_ELO
    games_a = games_b = 0
    lines: list[str] = []
    for seq in range(1, events + 1):
        winner = winners[seq - 1] if winners else ("a" if seq % 2 else "b")
        s_a, s_b = (1.0, 0.0) if winner == "a" else (0.0, 1.0)
        before_a, before_b = elo_a, elo_b
        e_a = elo.expected_score(before_a, before_b)
        new_a, new_b = elo.update_elo(
            before_a, elo.k_factor(games_a), s_a, e_a,
            before_b, elo.k_factor(games_b), s_b, 1.0 - e_a,
        )
        elo_a, elo_b = new_a, new_b
        games_a += 1
        games_b += 1
        lines.append(json.dumps({
            "version": elo.VERDICT_VERSION,
            "seq": seq,
            "task": "T-001",
            "matchup": f"T-001/{seq:03d}",
            "model_a": "alpha",
            "model_b": "beta",
            "model_a_id": "alpha",
            "model_b_id": "beta",
            "winner": winner,
            "date": "2026-01-02",
            "recorded_at": f"2026-01-02T10:{seq % 60:02d}:00+03:00",
            "elo": {
                "alpha": {"before": before_a, "after": new_a, "delta": new_a - before_a},
                "beta": {"before": before_b, "after": new_b, "delta": new_b - before_b},
            },
        }, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def test_history_pagination_widget():
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # Одностраничная история — виджета нет
        html = client.get("/history").get_data(as_text=True)
        assert 'class="pagination"' not in html, "виджет при одной странице"

        # 540 событий → 27 страниц по 20 записей
        _write(paths["journal"], _history_journal(540))
        data_cache.clear()

        def href(n: int) -> str:
            return f'href="/history?page={n}"'

        html1 = client.get("/history").get_data(as_text=True)
        assert href(2) in html1 and href(3) in html1 and href(27) in html1
        assert href(4) not in html1 and href(26) not in html1
        assert html1.count('class="ellipsis"') == 1
        assert '<span class="current" aria-current="page">1</span>' in html1
        assert html1.count("page-arrow disabled") == 1, "на первой странице «←» неактивна"
        assert 'rel="next"' in html1 and 'rel="prev"' not in html1

        html14 = client.get("/history?page=14").get_data(as_text=True)
        for n in (1, 12, 13, 15, 16, 27):
            assert href(n) in html14, f"нет ссылки на страницу {n}"
        for n in (2, 11, 17, 26):
            assert href(n) not in html14, f"лишняя ссылка на страницу {n}"
        assert html14.count('class="ellipsis"') == 2
        assert '<span class="current" aria-current="page">14</span>' in html14
        assert 'href="/history?page=13" rel="prev"' in html14

        html27 = client.get("/history?page=27").get_data(as_text=True)
        assert href(26) in html27 and href(25) in html27 and href(1) in html27
        assert 'href="/history?page=28"' not in html27
        assert html27.count('class="ellipsis"') == 1
        assert html27.count("page-arrow disabled") == 1, "на последней странице «→» неактивна"

        # Ссылки виджета сохраняют фильтр модели
        htmlf = client.get("/history?model=alpha").get_data(as_text=True)
        assert (
            'href="/history?page=2&amp;model=alpha"' in htmlf
            or 'href="/history?model=alpha&amp;page=2"' in htmlf
        ), "ссылка пагинации не сохраняет model"
    print("2.7 history pagination widget: OK")


def test_settings_queue_pagination():
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

        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # 105 открытых ячеек (C(15,2), вердиктов нет) → 2 страницы: 100 + 5
        resp = client.get("/settings")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "открытых: 105" in html, "счётчик должен показывать все открытые ячейки"
        assert "Очередь рекомендаций (" not in html, "суффикс (N) остался в заголовке"
        assert "Обоснование</th>" in html, "нет колонки «Обоснование» в очереди"
        assert "queue_page=2" in html, "нет перехода на следующую страницу"
        assert "queue_page=3" not in html, "лишняя третья страница"
        assert 'class="rank">100</td>' in html
        assert 'class="rank">101</td>' not in html
        assert '<span class="current" aria-current="page">1</span>' in html
        assert "queue_page=1" not in html, "текущая страница не должна быть ссылкой"
        assert html.count("page-arrow disabled") == 1, "на первой странице «←» неактивна"
        assert "← Назад</a>" not in html and "Вперёд →</a>" not in html

        resp = client.get("/settings?queue_page=2")
        html2 = resp.get_data(as_text=True)
        assert 'class="rank">101</td>' in html2
        assert 'class="rank">105</td>' in html2
        assert 'class="rank">106</td>' not in html2
        assert "queue_page=1" in html2, "нет перехода назад"
        assert "queue_page=3" not in html2, "после последней страницы ссылки нет"
        assert '<span class="current" aria-current="page">2</span>' in html2
        assert html2.count("page-arrow disabled") == 1, "на последней странице «→» неактивна"

        # Номер вне диапазона → последняя страница; невалидный → первая
        html99 = client.get("/settings?queue_page=99").get_data(as_text=True)
        assert 'class="rank">105</td>' in html99, "99 не приведён к последней странице"
        html_abc = client.get("/settings?queue_page=abc").get_data(as_text=True)
        assert 'class="rank">1</td>' in html_abc, "невалидный номер → первая страница"

        # Первая строка первой страницы — топ-1 рекомендации
        idx = server.ensure_index()
        top1 = server.get_recommendations(idx, top_n=1)
        assert top1 and not top1[0].get("is_rematch")
        first = top1[0]
        row = (
            f'<a href="/model/{first["model_a"]}" class="edit-link">'
            f'{first["name_a"]}</a> vs '
            f'<a href="/model/{first["model_b"]}" class="edit-link">'
            f'{first["name_b"]}</a>'
        )
        assert row in html, "первая строка очереди не совпадает с топ-1"
        assert f'<td class="queue-reason">{server.format_reason(first)}</td>' in html, (
            "обоснование первой строки очереди не совпадает с format_reason"
        )
    print("2.6 settings queue pagination: OK")


def _wcag_contrast(fg: tuple[float, float, float], bg: tuple[float, float, float]) -> float:
    """Контраст WCAG 2.x между двумя RGB-цветами (компоненты 0..255)."""
    def _lum(rgb: tuple[float, float, float]) -> float:
        def chan(c: float) -> float:
            c = c / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (chan(x) for x in rgb)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    l1, l2 = _lum(fg), _lum(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def test_caption_contrast_tokens():
    """Токены подписей моделей: контраст >= 4.5:1 в обеих темах (AA)."""
    css_path = Path(__file__).resolve().parent / "static" / "css" / "console.css"
    text = css_path.read_text(encoding="utf-8")
    light_at = text.index('[data-theme="light"]')
    parts = {"тёмная": text[:light_at], "светлая": text[light_at:]}

    def token(part: str, name: str) -> str:
        m = re.search(rf"{name}:\s*([^;]+);", part)
        assert m, f"токен {name} не найден в теме"
        return m.group(1).strip()

    def rgb(value: str) -> tuple[int, int, int]:
        assert re.fullmatch(r"#[0-9a-fA-F]{6}", value), f"не hex-цвет: {value}"
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))

    for theme, part in parts.items():
        surface = rgb(token(part, "--surface"))
        muted = rgb(token(part, "--muted"))
        alpha = float(token(part, "--caption-opacity"))
        blended = tuple(
            m * alpha + s * (1 - alpha) for m, s in zip(muted, surface)
        )
        ratio = _wcag_contrast(blended, surface)
        assert ratio >= 4.5, f"{theme} тема: контраст подписи {ratio:.2f}:1 < 4.5:1"
        print(f"  контраст подписи ({theme}): {ratio:.2f}:1")
    print("1.1 caption contrast tokens: OK")


def test_tables_scope_col():
    """Все заголовки таблиц консоли имеют scope="col"."""
    with _temp_storage() as _paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        for url in ("/", "/settings"):
            html = client.get(url).get_data(as_text=True)
            ths = re.findall(r"<th\b[^>]*>", html)
            assert ths, f"{url}: таблиц с th не найдено"
            bad = [t for t in ths if 'scope="col"' not in t]
            assert not bad, f"{url}: th без scope=\"col\": {bad[:3]}"
    print("1.3 tables scope col: OK")


def test_rec_alternatives():
    """Карточка рекомендации: top-3 варианта, «Другая пара», ссылки имён."""
    with _temp_storage() as paths:
        ids = ["m01", "m02", "m03", "m04"]
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

        server.app.config["TESTING"] = True
        client = server.app.test_client()
        html = client.get("/").get_data(as_text=True)

        assert html.count('class="rec-item rec-variant"') == 3, "не три варианта карточки"
        assert html.count('rec-variant" hidden') == 2, "альтернативы не скрыты"
        assert "Другая пара" in html and 'onclick="cycleRecommendation()"' in html
        assert "showRec" not in html and "nextRec" not in html, "протёк запрещённый ID"
        assert '<a href="/model/m01" class="edit-link">' in html, "имена моделей — не ссылки"
        css_path = Path(__file__).resolve().parent / "static" / "css" / "console.css"
        css = css_path.read_text(encoding="utf-8")
        assert ".rec-item[hidden]" in css, "нет CSS-правила скрытия вариантов"

    # Одна рекомендация — кнопки «Другая пара» нет
    with _temp_storage():
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        html = client.get("/").get_data(as_text=True)
        assert html.count('class="rec-item rec-variant"') == 1
        assert "Другая пара" not in html, "кнопка при одной рекомендации не нужна"
        assert 'onclick="cycleRecommendation()"' not in html
    print("2.2 rec alternatives: OK")


def test_rematch_count_unit():
    """R = вердикты − уникальные пары (синтетический индекс)."""
    with _temp_storage() as _paths:
        saved = server.ensure_index
        try:
            server.ensure_index = lambda: {
                "matchups_summary": {"total": 3},
                "elo_history": [
                    {"model_a_id": "a", "model_b_id": "b"},
                    {"model_a_id": "a", "model_b_id": "b"},
                    {"model_a_id": "a", "model_b_id": "c"},
                ],
            }
            data_cache.clear()
            assert server.memo_rematch_count() == 1, "повторная встреча не посчитана"

            # Fallback без matchups_summary: счётчик — по matchups_index
            server.ensure_index = lambda: {
                "matchups_index": [{"n": 1}, {"n": 2}],
                "elo_history": [
                    {"model_a_id": "a", "model_b_id": "b"},
                    {"model_a_id": "a", "model_b_id": "c"},
                ],
            }
            data_cache.clear()
            assert server.memo_rematch_count() == 0, "без повторов R должен быть 0"
        finally:
            server.ensure_index = saved
    print("3.1 rematch count: OK")


def test_summary_line():
    """Единая сводка: состав, ссылки, счётчик рематчей."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        def segment(html: str) -> str:
            marker = '<div class="stats stats-summary">'
            assert marker in html, "нет блока сводки"
            return html.split(marker)[1].split("</div>")[0]

        html = client.get("/").get_data(as_text=True)
        seg = segment(html)
        assert 'Моделей: <a href="/settings#models">2</a> из 3' in seg, seg
        assert 'Вердиктов: <a href="/history">1</a>' in seg, seg
        assert "рематчей" not in seg, "рематчи при нуле не должны показываться"
        assert 'Пары: <a href="/settings#recommendation-queue">1/1</a>' in seg, seg
        assert 'Таски: <a href="/settings#tasks">1 из 1</a>' in seg, seg
        assert "Обновлено:" in seg
        assert "Прогресс" not in seg, "слово «Прогресс» в сводке запрещено"

        settings_html = client.get("/settings").get_data(as_text=True)
        settings_seg = segment(settings_html)
        assert 'Моделей: <a href="#models">2 из 3</a>' in settings_seg, settings_seg
        assert 'Вердиктов: <a href="/history">1</a>' in settings_seg
        assert "рематчей" not in settings_seg
        assert settings_html.index("settings-nav") < settings_html.index("stats stats-summary"), (
            "сводка должна идти после анкор-навигации"
        )

        # 2 вердикта одной пары → 1 рематч; часть «(рематчей: 1)» появляется
        _write(paths["journal"], _history_journal(2))
        data_cache.clear()
        html2 = client.get("/").get_data(as_text=True)
        assert "(рематчей: 1)" in segment(html2), "рематч не показан на главной"
        settings2 = client.get("/settings").get_data(as_text=True)
        assert "(рематчей: 1)" in segment(settings2), "рематч не показан в настройках"
    print("3.2 summary line: OK")


def test_progress_card_states():
    """Плашка прогресса: компактная строка при 100%, бар при частичном."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/").get_data(as_text=True)
        assert "Прогресс прогона — 100% · все пары закрыты" in html
        assert "progress-track" not in html, "при 100% бар не нужен"

        _write(paths["journal"], "")
        data_cache.clear()
        html2 = client.get("/").get_data(as_text=True)
        assert "progress-track" in html2, "при частичном покрытии нужен бар"
        assert "осталось 1" in html2
        assert "все пары закрыты" not in html2
    print("3.3 progress card states: OK")


def _wave3_journal() -> str:
    """Журнал волны 3: T-001 и T-002, разные даты и исходы (replay ELO)."""
    elo_a = elo_b = elo.DEFAULT_ELO
    games_a = games_b = 0
    counters = {"T-001": 0, "T-002": 0}
    events = [
        ("T-001", "a", "2026-01-02"),
        ("T-002", "b", "2026-01-10"),
        ("T-002", "draw", "2026-01-20"),
    ]
    lines: list[str] = []
    for seq, (task, winner, day) in enumerate(events, start=1):
        if winner == "a":
            s_a, s_b = 1.0, 0.0
        elif winner == "b":
            s_a, s_b = 0.0, 1.0
        else:
            s_a, s_b = 0.5, 0.5
        before_a, before_b = elo_a, elo_b
        e_a = elo.expected_score(before_a, before_b)
        new_a, new_b = elo.update_elo(
            before_a, elo.k_factor(games_a), s_a, e_a,
            before_b, elo.k_factor(games_b), s_b, 1.0 - e_a,
        )
        elo_a, elo_b = new_a, new_b
        games_a += 1
        games_b += 1
        counters[task] += 1
        lines.append(json.dumps({
            "version": elo.VERDICT_VERSION,
            "seq": seq,
            "task": task,
            "matchup": f"{task}/{counters[task]:03d}",
            "model_a": "alpha",
            "model_b": "beta",
            "model_a_id": "alpha",
            "model_b_id": "beta",
            "winner": winner,
            "date": day,
            "recorded_at": f"{day}T10:00:00+03:00",
            "elo": {
                "alpha": {"before": before_a, "after": new_a, "delta": new_a - before_a},
                "beta": {"before": before_b, "after": new_b, "delta": new_b - before_b},
            },
        }, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def _history_rows(html: str) -> list[str]:
    """Строки ленты истории (контракт зеркального постпроцессора)."""
    return re.findall(
        r'<div class="history-item[^"]*"[^>]*>.*?</div>', html, re.S,
    )


def _rating_rows(html: str) -> list[str]:
    """Строки таблицы рейтинга."""
    return re.findall(r'<tr class="[^"]*">\s*<td class="rank">.*?</tr>', html, re.S)


def test_wave3_history_filters():
    """Волна 3: поисковые фильтры истории — таск, даты, исход, пара, комбинации."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        _write(paths["journal"], _wave3_journal())
        data_cache.clear()
        client.post("/verdict/void", data={
            "matchup_id": "T-002/001", "reason": "дубль матча", "next": "/history",
        })

        html = client.get("/history?include_voided=1").get_data(as_text=True)
        assert len(_history_rows(html)) == 3
        assert "Всего записей: 3 · аннулированных: 1" in html

        # Таск: T-002 — применённая и аннулированная записи
        for value in ("T-002", "T-002/002"):
            html = client.get(
                f"/history?task={value}&include_voided=1"
            ).get_data(as_text=True)
            assert len(_history_rows(html)) == 2
            assert "T-002/002" in html and "T-002/001" in html
            assert "T-001/001" not in html, "запись другого таска не отфильтрована"
        assert "Всего записей: 3 · аннулированных: 1 · найдено: 2" in html

        # Даты: только запись 2026-01-10 (она аннулирована)
        html = client.get("/history?from=2026-01-05&to=2026-01-15").get_data(as_text=True)
        assert _history_rows(html) == []
        assert "По выбранным условиям записей не найдено." in html
        html = client.get(
            "/history?from=2026-01-05&to=2026-01-15&include_voided=1"
        ).get_data(as_text=True)
        rows = _history_rows(html)
        assert len(rows) == 1 and "T-002/001" in rows[0]
        assert " · найдено: 1" in html

        # Исход
        html = client.get("/history?outcome=draw").get_data(as_text=True)
        rows = _history_rows(html)
        assert len(rows) == 1 and "T-002/002" in rows[0]
        assert 'name="outcome" value="draw" checked' in html

        # Пара: подстрока по id и именам (регистр не важен)
        for value in ("alph", "BETA"):
            html = client.get(
                f"/history?pair={value}&include_voided=1"
            ).get_data(as_text=True)
            assert len(_history_rows(html)) == 3
        html = client.get("/history?pair=gamma").get_data(as_text=True)
        assert _history_rows(html) == []

        # Точная пара idA:idB: порядок не важен, чужая пара — пусто
        html = client.get(
            "/history?pair=beta:alpha&include_voided=1"
        ).get_data(as_text=True)
        assert len(_history_rows(html)) == 3
        html = client.get(
            "/history?pair=alpha:gamma&include_voided=1"
        ).get_data(as_text=True)
        assert _history_rows(html) == []

        # Комбинация фильтров
        html = client.get(
            "/history?task=T-002&outcome=b&include_voided=1"
        ).get_data(as_text=True)
        rows = _history_rows(html)
        assert len(rows) == 1 and "T-002/001" in rows[0]

        # Невалидные значения игнорируются
        html = client.get("/history?from=2026-99-99&outcome=zzz").get_data(as_text=True)
        assert len(_history_rows(html)) == 2
        assert " · найдено:" not in html
        assert " · аннулированных:" not in html

        # Чип «Только аннулированные»
        html = client.get("/history?only_voided=1").get_data(as_text=True)
        rows = _history_rows(html)
        assert len(rows) == 1 and "history-item-voided" in rows[0]
        assert "Всего записей: 3 · аннулированных: 1" in html
        assert 'name="only_voided" value="1" checked' in html
        assert "filter-reset" in html
    print("wave3 history filters: OK")


def test_wave3_history_row_anchor():
    """Волна 3: самодостаточная строка истории и постоянные ссылки `?v=`."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        _write(paths["journal"], _wave3_journal())
        data_cache.clear()
        client.post("/verdict/void", data={
            "matchup_id": "T-002/001", "reason": "дубль матча", "next": "/history",
        })

        html = client.get("/history?include_voided=1").get_data(as_text=True)
        rows = _history_rows(html)
        assert len(rows) == 3
        applied = [r for r in rows if 'id="v-3"' in r][0]
        assert 'class="badge-task"' in applied
        assert 'href="/task/T-002"' in applied
        assert 'href="/model/alpha"' in applied and 'href="/model/beta"' in applied
        assert "history-divider" in applied
        assert 'class="outcome outcome-draw"' in applied
        assert 'aria-label="Ничья: Alpha vs Beta"' in applied
        assert 'class="matchup-chip"' in applied
        assert 'href="/history?v=3#v-3"' in applied
        assert "void-form-open" in applied

        voided = [r for r in rows if 'id="v-2"' in r][0]
        assert "history-item-voided" in voided
        assert "аннулировано" in voided and "дубль матча" in voided
        assert "history-void-note" in voided and "void-form-open" not in voided

        # `?v=` по записи в текущем составе: редирект на якорь, фильтры целы
        resp = client.get("/history?v=1")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/history#v-1"
        resp = client.get("/history?include_voided=1&v=2")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/history?include_voided=1#v-2"
        # Аннулированная запись вне текущего состава: полная лента + include_voided
        resp = client.get("/history?v=2")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/history?include_voided=1#v-2"
        # Ссылка на запись со второй страницы несёт page
        resp = client.get("/history?model=alpha&v=3")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/history?model=alpha#v-3"

        # Неизвестный seq: предупреждение, список не изменён
        html = client.get("/history?v=999").get_data(as_text=True)
        assert "Вердикт v=999 не найден — список записей не изменён." in html
        assert len(_history_rows(html)) == 2

    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        _write(paths["journal"], _history_journal(25))
        data_cache.clear()
        resp = client.get("/history?v=1")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/history?page=2#v-1"
    print("wave3 history row and anchor: OK")


def test_wave3_history_controls():
    """Волна 3: контролы поиска истории, пресеты дат, «страница №» и «в конец»."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/history").get_data(as_text=True)
        assert 'name="task"' in html and 'name="from"' in html and 'name="to"' in html
        assert 'name="pair"' in html
        assert 'name="outcome" value="a"' in html and 'name="outcome" value="b"' in html
        assert 'name="outcome" value="draw"' in html
        assert 'name="only_voided"' in html
        assert ">7 дней<" in html and ">30 дней<" in html and ">всё<" in html
        # Одна страница — ни поля, ни «в конец»
        assert 'class="page-jump"' not in html
        assert "в конец" not in html

        # 30 записей → 2 страницы: поле перехода и «в конец» с фильтрами
        _write(paths["journal"], _history_journal(30))
        data_cache.clear()
        html = client.get("/history?task=T-001&include_voided=1").get_data(as_text=True)
        assert len(_history_rows(html)) == 20
        assert 'class="page-jump"' in html
        jump = html.split('class="page-jump"', 1)[1].split("</form>", 1)[0]
        assert 'name="task" value="T-001"' in jump
        assert 'name="include_voided" value="1"' in jump
        assert 'name="page"' in jump and 'max="2"' in jump
        assert 'href="/history?page=2&amp;include_voided=1&amp;task=T-001"' in html
        assert "в конец" in html

        # Пресеты дат сохраняют прочие фильтры; активный — по from/to
        html = client.get("/history?model=alpha").get_data(as_text=True)
        assert '<a class="filter-preset is-active" href="/history?model=alpha">всё</a>' in html
        week_ago = (date.today() - timedelta(days=7)).isoformat()
        today = date.today().isoformat()
        assert (
            f'href="/history?model=alpha&amp;from={week_ago}&amp;to={today}"' in html
        )
        html = client.get(f"/history?from={week_ago}&to={today}").get_data(as_text=True)
        assert (
            f'<a class="filter-preset is-active" '
            f'href="/history?from={week_ago}&amp;to={today}">7 дней</a>' in html
        )
    print("wave3 history controls: OK")


def test_wave3_rating_search_sort():
    """Волна 3: поиск `q` и сортировка таблицы рейтинга."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # Поиск: подстрока имени/id, значение остаётся в поле
        html = client.get("/?q=alph").get_data(as_text=True)
        rows = _rating_rows(html)
        assert len(rows) == 1 and "model/alpha" in rows[0]
        assert 'name="q" value="alph"' in html

        _write(paths["models"], MODELS_YAML + """\
  - id: delta
    name: Delta
    agent: Other
    provider: Other
    added: 2026-01-01
    status: active
""")
        data_cache.clear()
        # Комбинация с чипами агентов (И между группами)
        html = client.get("/?q=elta&agents=Other").get_data(as_text=True)
        rows = _rating_rows(html)
        assert len(rows) == 1 and "model/delta" in rows[0]
        html = client.get("/?q=elta&agents=Agent").get_data(as_text=True)
        assert _rating_rows(html) == []
        assert "Ничего не найдено по запросу «elta»" in html
        # Подсветка: поиск сужает список, чипы только красят
        html = client.get("/?q=elta&view=highlight").get_data(as_text=True)
        assert len(_rating_rows(html)) == 1

        # Невалидный sort игнорируется
        html = client.get("/?sort=hack").get_data(as_text=True)
        assert "aria-sort" not in html
        assert len(_rating_rows(html)) == 3

        # Сортировка по ELO: asc, aria-sort и стрелка только у активной колонки
        html = client.get("/?sort=elo&dir=asc").get_data(as_text=True)
        rows = _rating_rows(html)
        assert "model/beta" in rows[0], "elo asc: первой должна идти beta"
        assert "model/alpha" in rows[2], "elo asc: alpha (максимум) — последняя"
        assert html.count('aria-sort="ascending"') == 1
        assert 'aria-sort="descending"' not in html
        assert '<span class="rank-num">1</span>' in rows[2], "места не пересчитаны"
        # Повторный клик по активной колонке — переворот направления
        assert 'href="/?sort=elo&amp;dir=desc"' in html
        # Колонка «Тренд» сортируемая
        assert 'href="/?sort=trend&amp;dir=desc"' in html

        # Ссылки сортировки сохраняют поиск и чипы
        html = client.get("/?q=alpha&agents=Agent&sort=name&dir=asc").get_data(as_text=True)
        assert 'href="/?q=alpha&amp;agents=Agent&amp;sort=name&amp;dir=desc"' in html
        assert 'href="/?q=alpha&amp;agents=Agent&amp;sort=elo&amp;dir=desc"' in html

        # По умолчанию — по месту, без aria-sort и стрелок; комбобокс подключён
        html = client.get("/").get_data(as_text=True)
        assert "aria-sort" not in html
        assert "sort-arrow" not in html
        assert 'src="/static/js/combobox.js"' in html
        assert "data-combobox" in html
    print("wave3 rating search and sort: OK")


def test_wave3_export_routes():
    """Волна 3: экспорт выборки рейтинга и истории (CSV/JSON)."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        _write(paths["journal"], _wave3_journal())
        data_cache.clear()
        client.post("/verdict/void", data={
            "matchup_id": "T-002/001", "reason": "дубль матча", "next": "/history",
        })

        idx = json.loads(paths["index"].read_text(encoding="utf-8"))
        elo_alpha = idx["models"]["alpha"]["elo"]
        elo_beta = idx["models"]["beta"]["elo"]
        today = date.today().isoformat()

        # Ссылки экспорта на странице — с текущими параметрами
        html = client.get("/?q=alpha&sort=elo&dir=asc").get_data(as_text=True)
        assert 'href="/export/rating.csv?q=alpha&amp;sort=elo&amp;dir=asc"' in html
        assert 'href="/export/rating.json?q=alpha&amp;sort=elo&amp;dir=asc"' in html

        resp = client.get("/export/rating.csv?sort=elo&dir=asc")
        assert resp.status_code == 200
        assert resp.headers["Content-Disposition"] == (
            f'attachment; filename="rating-{today}.csv"'
        )
        text = resp.get_data(as_text=True)
        assert text.startswith("\ufeff"), "CSV без BOM"
        lines = text.lstrip("\ufeff").rstrip("\r\n").split("\r\n")
        assert lines[0].startswith(
            "Место;id;Имя;Компания;Агент;ELO;±;Игры;Победы;Поражения;Ничьи;Винрейт, %"
        )
        assert lines[1].startswith(f"2;beta;Beta;Prov;Agent;{elo_beta};")
        assert lines[2].startswith(f"1;alpha;Alpha;Prov;Agent;{elo_alpha};")

        resp = client.get("/export/rating.json?sort=elo&dir=asc&q=beta")
        payload = resp.get_json()
        assert payload["count"] == 1 and payload["rows"][0]["id"] == "beta"
        assert payload["sort"] == "elo" and payload["dir"] == "asc"
        assert payload["filters"]["q"] == "beta"
        assert payload["generated_at"]

        # История: аннулированная запись с причиной, фильтры страницы
        resp = client.get("/export/history.csv?include_voided=1")
        assert resp.headers["Content-Disposition"] == (
            f'attachment; filename="history-{today}.csv"'
        )
        body = resp.get_data(as_text=True).lstrip("\ufeff")
        lines = body.rstrip("\r\n").split("\r\n")
        assert lines[0].startswith("seq;matchup;task;date;recorded_at;model_a_id;")
        assert len(lines) == 4, "в выборке истории не 3 записи"
        assert "T-002/001" in body and "дубль матча" in body and ";1;" in body

        resp = client.get("/export/history.json?task=T-002&outcome=draw")
        payload = resp.get_json()
        assert payload["filters"]["task"] == "T-002"
        assert payload["filters"]["outcome"] == "draw"
        assert payload["count"] == 1
        assert payload["rows"][0]["matchup"] == "T-002/002"
        assert payload["rows"][0]["task"] == "T-002"

        # Экспорт — только чтение: журнал не меняется
        journal_before = paths["journal"].read_bytes()
        client.get("/export/rating.csv")
        client.get("/export/history.json")
        assert paths["journal"].read_bytes() == journal_before
    print("wave3 export routes: OK")


def test_wave3_read_only_degrade():
    """Волна 3: в слепке нет поиска, сортировки, комбобокса и экспорта."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        _write(paths["journal"], _wave3_journal())
        data_cache.clear()
        saved = bool(server.app.config.get("READ_ONLY"))
        server.app.config["READ_ONLY"] = True
        try:
            html = client.get("/").get_data(as_text=True)
            assert 'name="q"' not in html
            assert "export-links" not in html and "/export/rating" not in html
            assert "sort-link" not in html and "aria-sort" not in html
            assert "data-combobox" not in html
            assert "combobox.js" not in html

            html = client.get("/history").get_data(as_text=True)
            assert 'name="task"' not in html
            assert 'name="from"' not in html and 'name="to"' not in html
            assert 'name="outcome"' not in html and 'name="pair"' not in html
            assert 'name="only_voided"' not in html
            assert 'class="page-jump"' not in html
            assert "/export/history" not in html
            assert "data-combobox" not in html
        finally:
            server.app.config["READ_ONLY"] = saved
    print("wave3 read-only degrade: OK")


def test_wave4_task_page():
    """Волна 4: страница задачи — шапка, прогресс, 404 и task.md."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/task/T-001").get_data(as_text=True)
        assert "Smoke" in html and "Benchmark" in html
        assert "активна" in html and "текущая" in html
        assert 'href="/?task=T-001"' in html, "нет действия «Записать вердикт»"
        assert 'href="/history?task=T-001"' in html, "нет действия «История таска»"
        assert 'href="/task/T-001/md"' in html, "нет ссылки task.md"
        assert "baseline:" not in html, "пустой baseline не рендерится"

        # Прогресс: 1 вердикт, 1 из 1 пара, 2 модели, 0 аннулированных
        assert '<div class="stat-value">1</div><div class="stat-label">Вердиктов</div>' in html
        assert '<div class="stat-value">1 из 1</div><div class="stat-label">Пар закрыто</div>' in html
        assert '<div class="stat-value">2</div><div class="stat-label">Моделей</div>' in html
        assert '<div class="stat-value">0</div><div class="stat-label">Аннулировано</div>' in html

        # Строка вердикта: без бейджа таска, чип matchup, live-форма аннулирования
        assert "T-001/001" in html and "Alpha" in html and "Beta" in html
        assert 'class="badge-task"' not in html, "на странице задачи бейдж не нужен"
        assert "void-form-open" in html

        # Неизвестная таска — 404 (страница и task.md)
        assert client.get("/task/T-999").status_code == 404
        assert client.get("/task/T-999/md").status_code == 404

        # task.md — text/plain с телом задачи
        md = client.get("/task/T-001/md")
        assert md.status_code == 200
        assert md.headers["Content-Type"].startswith("text/plain")
        assert "Тело smoke-задачи." in md.get_data(as_text=True)

        # Неактивная таска: плашка «неактивна», без «текущая»
        _write(paths["settings"], "current_task: ''\ntasks:\n  T-001: inactive\n")
        data_cache.clear()
        html2 = client.get("/task/T-001").get_data(as_text=True)
        assert "неактивна" in html2 and "текущая" not in html2
    print("wave4 task page: OK")


def test_wave4_task_verdicts_pagination():
    """Волна 4: список вердиктов таска — порядок, пустое состояние, пагинация."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()
        _write(paths["journal"], _history_journal(540))
        data_cache.clear()

        html = client.get("/task/T-001").get_data(as_text=True)
        rows = _history_rows(html)
        assert len(rows) == 20, "страница списка — 20 записей"
        assert 'id="v-540"' in rows[0], "порядок по seq по убыванию"
        assert 'id="v-521"' in rows[-1]
        assert 'href="/task/T-001?page=2"' in html, "нет ссылки на страницу 2"
        assert 'href="/task/T-001?page=27"' in html, "нет ссылки на последнюю страницу"
        assert 'class="page-jump"' in html, "нет поля «Страница»"

        html14 = client.get("/task/T-001?page=14").get_data(as_text=True)
        assert '<span class="current" aria-current="page">14</span>' in html14
        assert 'href="/task/T-001?page=13" rel="prev"' in html14

        last = client.get("/task/T-001?page=27").get_data(as_text=True)
        assert len(_history_rows(last)) == 20
        assert 'id="v-1"' in last

        # Номер вне диапазона приводится к границам
        assert 'id="v-1"' in client.get("/task/T-001?page=99").get_data(as_text=True)
        assert 'id="v-540"' in client.get("/task/T-001?page=abc").get_data(as_text=True)

        # Аннулированные — перечёркнуты с причиной; формы возврата на страницу таска
        _write(paths["journal"], _wave3_journal())
        _write(paths["flags"], FLAGS_YAML + "  T-002:\n    alpha: true\n    beta: true\n")
        data_cache.clear()
        resp = client.post("/verdict/void", data={
            "matchup_id": "T-002/001", "reason": "дубль матча",
            "next": "/task/T-002",
        })
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("/task/T-002"), "возврат на страницу таска"
        html2 = client.get("/task/T-002").get_data(as_text=True)
        rows2 = _history_rows(html2)
        assert len(rows2) == 2
        voided = [r for r in rows2 if "history-item-voided" in r][0]
        assert "дубль матча" in voided and "void-form-open" not in voided
        assert '<div class="stat-value">1</div><div class="stat-label">Вердиктов</div>' in html2
        assert '<div class="stat-value">1 из 1</div><div class="stat-label">Пар закрыто</div>' in html2
        assert '<div class="stat-value">1</div><div class="stat-label">Аннулировано</div>' in html2

        # Пустое состояние: таск известен, вердиктов нет
        _write(paths["journal"], "")
        data_cache.clear()
        html3 = client.get("/task/T-001").get_data(as_text=True)
        assert "У таска пока нет вердиктов" in html3
        assert '<div class="stat-value">0 из 1</div><div class="stat-label">Пар закрыто</div>' in html3
        assert "history-pagination" not in html3, "виджет пагинации при пустом списке"
    print("wave4 task verdicts pagination: OK")


def test_wave4_task_links():
    """Волна 4: переходы на страницу задачи из настроек, истории, очереди, карточки."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # С вердиктом: бейдж строки истории и ID в списке тасков
        settings = client.get("/settings").get_data(as_text=True)
        assert '<a href="/task/T-001" class="edit-link">T-001</a>' in settings
        history = client.get("/history").get_data(as_text=True)
        assert '<a class="badge-task" href="/task/T-001" title=' in history

        # Без вердиктов: открытые ячейки → очередь и карточка рекомендации
        _write(paths["journal"], "")
        data_cache.clear()
        settings2 = client.get("/settings").get_data(as_text=True)
        assert '<td><a href="/task/T-001" class="edit-link">T-001</a></td>' in settings2, (
            "ячейка таска в очереди рекомендаций не ссылается на страницу"
        )
        main = client.get("/").get_data(as_text=True)
        assert 'class="rec-task">таск: <a href="/task/T-001"' in main, (
            "таск в карточке рекомендации не ссылается на страницу"
        )
    print("wave4 task links: OK")


def test_wave4_stats_a1_a2():
    """Волна 4: /stats — карточки A1/A2, выбор линий, период, лимит, пусто."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/stats").get_data(as_text=True)
        # Порядок карточек: A1 → «Распределение Elo» → A2
        i1 = html.index("Интервалы рейтинга")
        i2 = html.index("Распределение Elo")
        i3 = html.index("Динамика ELO")
        assert i1 < i2 < i3, "порядок карточек аналитики"

        # A1: активный пул, интервалы, группа, ссылки на профили
        assert 'aria-label="Интервалы рейтинга: 2 моделей' in html
        assert 'href="/model/alpha"' in html and 'href="/model/beta"' in html
        assert 'href="/model/gamma"' not in html, "архивная модель попала в A1"
        assert "место не определено" in html
        assert "interval-gap" not in html, "прочерк без игр"

        # A1 не зависит от фильтров страницы: распределение меняется, A1 — нет
        html_all = client.get("/stats?filter=all").get_data(as_text=True)
        assert "моделей: 2" in html and "моделей: 3" in html_all
        assert 'aria-label="Интервалы рейтинга: 2 моделей' in html_all

        # A2 по умолчанию: топ-5 активных, период 90, пресеты
        assert 'name="period" value="90" checked' in html
        assert html.count('class="lines-check"') == 2, "чекбоксы активных моделей"
        assert 'name="lines" value="alpha" checked' in html
        assert 'name="lines" value="beta" checked' in html
        assert "lines-presets" in html and "/stats?lines=" in html
        assert 'aria-label="Динамика ELO: линий 2, матчей 1"' in html

        # A2: выбор одной линии из URL
        one = client.get("/stats?lines=beta").get_data(as_text=True)
        assert 'aria-label="Динамика ELO: линий 1, матчей 1"' in one
        legend_one = one.split('class="line-legend"', 1)[1].split("</div>", 1)[0]
        assert legend_one.count('class="line-legend-item') == 1
        assert "Beta" in legend_one and "Alpha" not in legend_one

        # Период из URL: 30/90/all; невалидное значение → 90
        for value in ("30", "all"):
            page = client.get(f"/stats?period={value}").get_data(as_text=True)
            assert f'name="period" value="{value}" checked' in page
        bad = client.get("/stats?period=zzz").get_data(as_text=True)
        assert 'name="period" value="90" checked' in bad

        # Дефолт и лимит линий: 12 активных моделей, журнал пуст
        ids = [f"m{i:02d}" for i in range(12)]
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
        _write(paths["models"], "\n".join(models_yaml) + "\n")
        _write(paths["journal"], "")
        data_cache.clear()

        twelve = client.get("/stats").get_data(as_text=True)
        assert twelve.count('class="line-legend-item') == 5, "дефолт — топ-5"
        all12 = client.get("/stats?lines=" + ",".join(ids)).get_data(as_text=True)
        assert all12.count('class="line-legend-item') == 10, "кап 10 линий"
        assert "Нет матчей выбранных моделей в периоде" in all12

        # Пусто: все модели архивные — оба блока показывают заглушки
        _write(paths["models"], (
            "models:\n  - id: gamma\n    name: Gamma\n    agent: Agent\n"
            "    provider: Prov\n    added: 2026-01-01\n    status: archived\n"
        ))
        data_cache.clear()
        empty = client.get("/stats").get_data(as_text=True)
        assert "Нет активных моделей" in empty
        assert "Нет матчей выбранных моделей в периоде" in empty
        assert "line-legend" not in empty, "легенда без выбранных линий"
    print("wave4 stats A1/A2: OK")


def test_wave4_stats_a3_a5():
    """Волна 4: /stats — A3 активность, A4 матрица (ссылки, рематч), A5 сводки."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/stats").get_data(as_text=True)
        # A3: сводка и столбик единственного дня
        assert "дней: 1 · вердиктов: 1 · максимум: 1" in html
        assert "activity-bar" in html and "02.01.2026: 1" in html
        # A4: матрица активного пула, ссылка на историю пары
        assert 'aria-label="Матрица пар: 2 моделей, встреч 1"' in html
        assert 'href="/history?pair=alpha:beta"' in html
        assert "pair-cell-diagonal" in html
        assert "pair-cell-rematch" not in html, "одна встреча — не рематч"
        # A5: сводки по активному пулу (архивная gamma не участвует)
        assert '<h3 class="card-subtitle">Агенты</h3>' in html
        assert "<td>Agent</td><td>2</td><td>1200</td><td>1200</td><td>2</td><td>50%</td>" in html
        assert "<td>Prov</td><td>2</td><td>1200</td><td>1200</td><td>2</td><td>50%</td>" in html
        assert "без агента" not in html

        # Рематч: две встречи — метка рематча и подсказка
        _write(paths["journal"], _history_journal(2))
        data_cache.clear()
        html2 = client.get("/stats").get_data(as_text=True)
        assert "pair-cell-rematch" in html2 and "pair-rematch-dot" in html2
        assert "Alpha vs Beta: 2 · рематч" in html2
        assert "дней: 1 · вердиктов: 2 · максимум: 2" in html2

        # Пустые журнал и матрица — заглушки A3/A4
        _write(paths["journal"], "")
        data_cache.clear()
        html3 = client.get("/stats").get_data(as_text=True)
        assert "Нет применённых встреч" in html3
        assert "В истории нет вердиктов" in html3
        assert "matrix-wrap" not in html3
        assert "activity-bar" not in html3
    print("wave4 stats A3/A5: OK")


def test_wave4_stats_a6_a8():
    """Волна 4: /stats — A6 окна и остывшие, A7 оппозиция, A8 доли и таски."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/stats").get_data(as_text=True)
        # A6: единственный матч — рост alpha и падение beta
        assert "Взлёты и падения" in html
        assert 'class="delta-sum delta-up">+20' in html
        assert 'class="delta-sum delta-down">-20' in html
        assert "Остывшие" not in html, "обе активные модели играли"

        # A7: пул в порядке рейтинга, прочерков нет — обе играли
        opp = html.split('id="opposition"', 1)[1].split('id="outcomes"', 1)[0]
        assert '<a href="/model/alpha">Alpha</a>' in opp
        assert "<td>1220</td>" in opp and "<td>1180</td>" in opp
        assert "<td>1200</td>" in opp, "средний ELO соперников"
        assert "<td>0</td>" in opp, "у beta нет побед над топ-10"
        assert "—" not in opp

        # A8: одна активная задача — общие доли без разбивки
        assert "всего применённых вердиктов: 1" in html
        assert 'class="outcome-pct">100%' in html
        assert "По активным задачам" not in html

        # Две активные задачи: разбивка с ссылками на страницы задач
        lines = _history_journal(2).strip().splitlines()
        second = json.loads(lines[1])
        second["task"] = "T-002"
        second["matchup"] = "T-002/001"
        lines[1] = json.dumps(second, ensure_ascii=False)
        _write(paths["journal"], "\n".join(lines) + "\n")
        data_cache.clear()

        two = client.get("/stats").get_data(as_text=True)
        assert "По активным задачам" in two
        assert 'href="/task/T-001"' in two and 'href="/task/T-002"' in two
        assert "всего применённых вердиктов: 2" in two
        assert two.count('class="outcome-pct">50%</span>') == 2
        assert 'class="outcome-pct">0%</span>' in two
        assert "победила A · 100% (1)" in two, "разбивка T-001"
        assert "победила B · 100% (1)" in two, "разбивка T-002"

        # Пустой журнал: A4/A8 — заглушки, A6 — пустые окна и все активные остыли
        _write(paths["journal"], "")
        data_cache.clear()
        empty = client.get("/stats").get_data(as_text=True)
        assert "Нет применённых встреч." in empty
        assert "Нет применённых вердиктов." in empty
        assert "Остывшие" in empty
        assert empty.count('class="delta-empty">Нет роста</div>') == 2
        assert "delta-sum" not in empty, "роста и падения нет"
        assert empty.count('class="delta-name"') == 2, "остыли обе модели"
        opp_empty = empty.split('id="opposition"', 1)[1].split('id="outcomes"', 1)[0]
        assert opp_empty.count("—") == 4, "модели без игр — прочерки"
    print("wave4 stats A6/A8: OK")


def _profile_journal() -> str:
    """Три матча alpha>beta, gamma>alpha, beta>gamma со снэпшотами реплея."""
    elo_map = {
        "alpha": elo.DEFAULT_ELO, "beta": elo.DEFAULT_ELO,
        "gamma": elo.DEFAULT_ELO,
    }
    games = {"alpha": 0, "beta": 0, "gamma": 0}
    plan = [
        (("alpha", "beta"), "a"),
        (("alpha", "gamma"), "b"),
        (("beta", "gamma"), "a"),
    ]
    lines: list[str] = []
    for seq, ((a, b), winner) in enumerate(plan, start=1):
        before_a, before_b = elo_map[a], elo_map[b]
        s_a, s_b = (1.0, 0.0) if winner == "a" else (0.0, 1.0)
        e_a = elo.expected_score(before_a, before_b)
        new_a, new_b = elo.update_elo(
            before_a, elo.k_factor(games[a]), s_a, e_a,
            before_b, elo.k_factor(games[b]), s_b, 1.0 - e_a,
        )
        elo_map[a], elo_map[b] = new_a, new_b
        games[a] += 1
        games[b] += 1
        lines.append(json.dumps({
            "version": elo.VERDICT_VERSION,
            "seq": seq,
            "task": "T-001",
            "matchup": f"T-001/{seq:03d}",
            "model_a": a,
            "model_b": b,
            "model_a_id": a,
            "model_b_id": b,
            "winner": winner,
            "date": "2026-01-02",
            "recorded_at": f"2026-01-02T10:{seq:02d}:00+03:00",
            "elo": {
                a: {"before": before_a, "after": new_a, "delta": new_a - before_a},
                b: {"before": before_b, "after": new_b, "delta": new_b - before_b},
            },
        }, ensure_ascii=False))
    return "\n".join(lines) + "\n"


def test_wave4_profile():
    """Волна 4: профиль — место/тренд, последний матч, покрытие, метаданные, H2H."""
    with _temp_storage() as paths:
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # 5.1: место в активном пуле, тренд, «Последний матч»
        html = client.get("/model/alpha").get_data(as_text=True)
        assert 'class="profile-rank">Место 1 из 2</span>' in html
        assert 'class="trend-arrow"' not in html, "1 игра — стрелки нет"
        assert "мало игр для тренда" in html, "пояснение вместо стрелки"
        assert 'id="profile-last-match"' in html
        assert '<a href="/model/beta" class="edit-link">Beta</a>' in html
        assert "Победа" in html
        assert 'class="history-delta-up">+20</span>' in html
        assert 'href="/history?v=1#v-1"' in html
        assert "Матчей нет" not in html

        # 5.3: дата истории — постоянная ссылка, кнопка «Показать в истории»
        assert 'title="Постоянная ссылка на вердикт №1"' in html
        assert "2026-01-02 10:00:00" in html
        assert 'href="/history?model=alpha"' in html
        assert "Показать в истории" in html

        # 5.3: по умолчанию H2H — по числу встреч по убыванию, aria-sort и ссылки
        assert 'aria-sort="descending"' in html
        assert 'href="/model/alpha?h2h_sort=winrate&amp;h2h_dir=desc"' in html

        # Архивная модель: места нет, матчей и встреч нет
        gamma = client.get("/model/gamma").get_data(as_text=True)
        assert "Вне активного рейтинга" in gamma
        assert 'class="profile-rank"' not in gamma
        assert "Матчей нет" in gamma
        assert "Пока нет встреч" in gamma

        # 5.2: покрытие — активный T-001 с одним матчем и ссылкой
        assert 'href="/task/T-001" class="edit-link">T-001</a> — 1' in html
        # 5.2: метаданные частичные — добавлена и статус, без версии и релиза
        assert 'id="model-meta"' in html
        assert "<dt>Добавлена</dt><dd>2026-01-01</dd>" in html
        assert "<dt>Статус</dt><dd>активна</dd>" in html
        assert "<dt>Версия</dt>" not in html and "<dt>Релиз</dt>" not in html

        # 5.2: второй активный таск без матчей — прочерк
        _write(
            paths["settings"],
            "current_task: T-001\ntasks:\n  T-001: active\n  T-002: active\n",
        )
        data_cache.clear()
        two = client.get("/model/alpha").get_data(as_text=True)
        assert 'href="/task/T-002" class="edit-link">T-002</a> — —' in two

        # 5.2: нет активных тасков — блок скрыт
        _write(
            paths["settings"],
            "current_task: T-002\ntasks:\n  T-001: inactive\n  T-002: inactive\n",
        )
        data_cache.clear()
        hidden = client.get("/model/alpha").get_data(as_text=True)
        assert 'id="task-coverage"' not in hidden

        # 5.1: 6 игр (проигрыш, затем пять побед) — стрелка «↑1»
        _write(paths["journal"], _history_journal(6, "baaaaa"))
        data_cache.clear()
        arrow = client.get("/model/alpha").get_data(as_text=True)
        assert "Место 1 из 2" in arrow
        assert '<span class="trend-arrow">↑</span>' in arrow
        assert '<span class="trend-num">1</span>' in arrow
        assert 'href="/history?v=6#v-6"' in arrow, "последний матч — seq 6"

        # 5.3: поиск и сортировка «Личных встреч»
        _write(paths["journal"], _profile_journal())
        data_cache.clear()

        def h2h_of(page_html: str) -> str:
            return page_html.split('id="h2h"', 1)[1].split('id="history"', 1)[0]

        base = client.get("/model/alpha").get_data(as_text=True)
        base_h2h = h2h_of(base)
        assert 'aria-sort="descending"' in base_h2h
        assert base_h2h.index(">Beta</a>") < base_h2h.index(">Gamma</a>"), "имя при равенстве"

        asc = client.get("/model/alpha?h2h_sort=winrate&h2h_dir=asc").get_data(as_text=True)
        asc_h2h = h2h_of(asc)
        assert 'aria-sort="ascending"' in asc_h2h
        assert 'aria-sort="descending"' not in asc_h2h
        assert asc_h2h.index(">Gamma</a>") < asc_h2h.index(">Beta</a>"), "0.0% выше 100.0%"

        desc = client.get("/model/alpha?h2h_sort=winrate").get_data(as_text=True)
        desc_h2h = h2h_of(desc)
        assert 'aria-sort="descending"' in desc_h2h
        assert 'href="/model/alpha?h2h_sort=winrate&amp;h2h_dir=asc"' in desc_h2h
        assert desc_h2h.index(">Beta</a>") < desc_h2h.index(">Gamma</a>")

        found = client.get("/model/alpha?h2h_q=BETA").get_data(as_text=True)
        found_h2h = h2h_of(found)
        assert ">Beta</a>" in found_h2h and ">Gamma</a>" not in found_h2h
        assert 'value="BETA"' in found, "строка поиска сохраняется"
        assert 'name="h2h_sort" value="games"' in found, "сортировка сохраняется"

        none = client.get("/model/alpha?h2h_q=zzz").get_data(as_text=True)
        assert "Никого не найдено" in none
        assert ">Beta</a>" not in h2h_of(none)

        dirty = client.get("/model/alpha?h2h_sort=bogus&h2h_dir=up").get_data(as_text=True)
        assert 'aria-sort="descending"' in h2h_of(dirty), "мусорные параметры → дефолт"

        # 5.2: полные метаданные — все пять полей
        _write(paths["models"], (
            "models:\n"
            "  - id: alpha\n"
            "    name: Alpha\n"
            "    version: \"1.2\"\n"
            "    released: 2025-12-01\n"
            "    added: 2026-01-01\n"
            "    status: active\n"
            "    notes: \"Тестовая заметка\"\n"
        ))
        data_cache.clear()
        full = client.get("/model/alpha").get_data(as_text=True)
        assert "<dt>Версия</dt><dd>1.2</dd>" in full
        assert "<dt>Релиз</dt><dd>2025-12-01</dd>" in full
        assert "<dt>Добавлена</dt><dd>2026-01-01</dd>" in full
        assert "<dt>Статус</dt><dd>активна</dd>" in full
        assert "<dt>Заметки</dt><dd>Тестовая заметка</dd>" in full

        # 5.2: пустые метаданные — блока нет
        _write(paths["models"], (
            "models:\n"
            "  - id: alpha\n"
            "    name: Alpha\n"
            "    version: \n"
            "    released: \n"
            "    added: \n"
            "    status: \n"
            "    notes: \n"
        ))
        data_cache.clear()
        bare = client.get("/model/alpha").get_data(as_text=True)
        assert 'id="model-meta"' not in bare
        assert "Место" in bare, "страница рендерится"
    print("wave4 profile: OK")


def test_wave5_history_title():
    """Волна 5: заголовок вкладки истории несёт число записей выборки."""
    with _temp_storage():
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/history").get_data(as_text=True)
        assert "<title>История — 1 запись — ELO Benchmark</title>" in html

        one = client.get("/history?model=alpha").get_data(as_text=True)
        assert "<title>История — 1 запись — ELO Benchmark</title>" in one

        empty = client.get("/history?model=gamma").get_data(as_text=True)
        assert "<title>История — 0 записей — ELO Benchmark</title>" in empty
    print("wave5 history title: OK")


def test_wave5_chart_links():
    """Волна 5: графики кликабельны — распределение/A2/A3 и точки профиля."""
    with _temp_storage():
        server.app.config["TESTING"] = True
        client = server.app.test_client()

        html = client.get("/stats").get_data(as_text=True)
        assert '<a href="/model/alpha" class="dist-link">' in html
        assert 'class="chart-line-hit"' in html and 'href="/model/beta"' in html
        assert (
            'href="/history?from=2026-01-02&amp;to=2026-01-02"' in html
        ), "столбик дня без ссылки"

        model = client.get("/model/alpha").get_data(as_text=True)
        assert 'class="chart-dot-link"' in model and 'class="chart-dot-hit"' in model
        assert model.count('href="/history?v=1#v-1"') >= 2, (
            "точка графика не ведёт к записи вердикта"
        )

        saved = bool(server.app.config.get("READ_ONLY"))
        server.app.config["READ_ONLY"] = True
        try:
            ro = client.get("/stats").get_data(as_text=True)
            assert "/history?from=" not in ro, "столбики дней ведут на фильтр дат"
            assert 'class="dist-link"' in ro, "бары распределения без ссылок"
            assert 'class="chart-line-hit"' in ro, "линии A2 без ссылок"
            ro_model = client.get("/model/alpha").get_data(as_text=True)
            assert 'class="chart-dot-link"' in ro_model, "точки графика без ссылок"
        finally:
            server.app.config["READ_ONLY"] = saved
    print("wave5 chart links: OK")


if __name__ == "__main__":
    test_key_changes_per_file()
    test_builder_runs_once()
    test_clear_resets()
    test_parallel_cached_single_build()
    test_requests_do_not_reread_journal()
    test_routes_smoke()
    test_version_badge()
    test_merge_history_feed_unit()
    test_void_route()
    test_history_voided_feed()
    test_verdict_context_and_actions()
    test_pair_hints_island()
    test_wave2_integration_scenario()
    test_caption_contrast_tokens()
    test_tables_scope_col()
    test_pagination_items_window()
    test_history_pagination_widget()
    test_settings_queue_pagination()
    test_rec_alternatives()
    test_rematch_count_unit()
    test_summary_line()
    test_progress_card_states()
    test_wave3_history_filters()
    test_wave3_history_row_anchor()
    test_wave3_history_controls()
    test_wave3_rating_search_sort()
    test_wave3_export_routes()
    test_wave3_read_only_degrade()
    test_wave4_task_page()
    test_wave4_task_verdicts_pagination()
    test_wave4_task_links()
    test_wave4_stats_a1_a2()
    test_wave4_stats_a3_a5()
    test_wave4_stats_a6_a8()
    test_wave4_profile()
    test_wave5_history_title()
    test_wave5_chart_links()
    print("\nALL DATA CACHE TESTS PASSED")
