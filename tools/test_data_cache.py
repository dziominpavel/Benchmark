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

Запуск: python tools/test_data_cache.py
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import date, timedelta
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


def _history_journal(events: int) -> str:
    """Журнал alpha vs beta с ELO-снэпшотами, посчитанными тем же реплеем."""
    elo_a = elo_b = elo.DEFAULT_ELO
    games_a = games_b = 0
    lines: list[str] = []
    for seq in range(1, events + 1):
        winner = "a" if seq % 2 else "b"
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
        assert 'href="/history?task=T-002"' in applied
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


if __name__ == "__main__":
    test_key_changes_per_file()
    test_builder_runs_once()
    test_clear_resets()
    test_parallel_cached_single_build()
    test_requests_do_not_reread_journal()
    test_routes_smoke()
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
    print("\nALL DATA CACHE TESTS PASSED")
