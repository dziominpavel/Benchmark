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

Запуск: python tools/test_data_cache.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
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

        # После записи главная перерисовывается на новом состоянии
        resp = client.get("/")
        assert resp.status_code == 200
        assert paths["index"].exists()
    print("2.4 routes smoke: OK")


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
        assert "осталось 105" in html, "счётчик должен показывать все открытые ячейки"
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
    print("2.6 settings queue pagination: OK")


if __name__ == "__main__":
    test_key_changes_per_file()
    test_builder_runs_once()
    test_clear_resets()
    test_parallel_cached_single_build()
    test_requests_do_not_reread_journal()
    test_routes_smoke()
    test_pagination_items_window()
    test_settings_queue_pagination()
    test_history_pagination_widget()
    print("\nALL DATA CACHE TESTS PASSED")
