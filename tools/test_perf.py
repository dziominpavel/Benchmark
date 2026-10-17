#!/usr/bin/env python3
"""
test_perf.py — бюджетные замеры консоли на целевом масштабе (5.1).

Синтетическое хранилище: 1000 активных моделей, 10 000 событий журнала,
3 задачи. Проверяет требование «Отзывчивость консоли на целевом масштабе»
(дельта `leaderboard-ui` change scale-console-1000-models):

  * главная и переключение фильтров — ≤0.5 с в типовом состоянии покрытия
    (отмечены 100 моделей) и ≤1 с в предельном (отмечены все 1000);
  * повторные запросы без изменения данных — в тех же бюджетах;
  * `/settings`, `/history`, `/stats` — ≤1 с;
  * запись вердикта через веб-UI с пересчётом `data/index.json` — ≤1 с;
  * `elo.run_check()` (журнал + индекс) — ≤0.5 с.

Синтетика воспроизводима (SEED) и консистентна: ELO-снэпшоты событий
рассчитаны тем же протоколом, что и реплей (`elo.recalculate`), поэтому
`run_check()` на ней зелёный. Замеры — Flask test client в этом же
процессе + прямой вызов `run_check()`; холодный путь — после явного
сброса мемо-слоя (`data_cache.clear()`), в каждом окне замера собирается
мусор тест-харнесса (`gc.collect()`).

Запуск: python tools/test_perf.py
"""

from __future__ import annotations

import gc
import json
import random
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data_cache
import elo
import lookups
import server

N_MODELS = 1000
N_EVENTS = 10_000
N_TASKS = 3
TYPICAL_FLAGS = 100
SEED = 42

TASKS = ["T-001", "T-002", "T-003"]

BUDGET_TYPICAL = 0.5      # главная/фильтры, типовое покрытие
BUDGET_PEAK_MAIN = 1.0    # главная, предельное покрытие
BUDGET_PAGE = 1.0         # /settings, /history, /stats, запись вердикта
BUDGET_CHECK = 0.5        # elo.run_check()

FAILURES: list[str] = []


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _model_ids() -> list[str]:
    return [f"perf-{i:04d}" for i in range(N_MODELS)]


def _models_yaml(ids: list[str]) -> str:
    lines = ["models:"]
    for i, mid in enumerate(ids):
        lines += [
            f"  - id: {mid}",
            f"    name: Perf Model {i:04d}",
            f"    agent: Agent{i % 5}",
            f"    provider: Prov{i % 3}",
            "    added: 2026-01-01",
            "    status: active",
        ]
    return "\n".join(lines) + "\n"


def _flags_yaml(ids: list[str], flagged: int) -> str:
    lines = ["answer_flags:", "  T-001:"]
    lines += [f"    {mid}: true" for mid in ids[:flagged]]
    return "\n".join(lines) + "\n"


def _journal_text(ids: list[str]) -> str:
    """События с ELO-снэпшотами, посчитанными тем же реплеем, что `recalculate`."""
    rng = random.Random(SEED + 1)
    elo_cur = {mid: elo.DEFAULT_ELO for mid in ids}
    games = {mid: 0 for mid in ids}
    per_task = {t: 0 for t in TASKS}
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=3)))

    lines: list[str] = []
    for seq in range(1, N_EVENTS + 1):
        task = TASKS[(seq - 1) % N_TASKS]
        a, b = rng.sample(ids, 2)
        per_task[task] += 1

        r = rng.random()
        winner = "a" if r < 0.44 else "b" if r < 0.88 else "draw"
        if winner == "a":
            s_a, s_b = 1.0, 0.0
        elif winner == "b":
            s_a, s_b = 0.0, 1.0
        else:
            s_a, s_b = 0.5, 0.5

        r_a, r_b = elo_cur[a], elo_cur[b]
        e_a = elo.expected_score(r_a, r_b)
        new_a, new_b = elo.update_elo(
            r_a, elo.k_factor(games[a]), s_a, e_a,
            r_b, elo.k_factor(games[b]), s_b, 1.0 - e_a,
        )
        elo_cur[a], elo_cur[b] = new_a, new_b
        games[a] += 1
        games[b] += 1

        ts = base + timedelta(seconds=seq)
        event = {
            "version": elo.VERDICT_VERSION,
            "seq": seq,
            "task": task,
            "matchup": f"{task}/{per_task[task]:03d}",
            "model_a": a,
            "model_b": b,
            "model_a_id": a,
            "model_b_id": b,
            "winner": winner,
            "date": ts.date().isoformat(),
            "recorded_at": ts.isoformat(timespec="seconds"),
            "elo": {
                a: {"before": r_a, "after": new_a, "delta": new_a - r_a},
                b: {"before": r_b, "after": new_b, "delta": new_b - r_b},
            },
        }
        lines.append(json.dumps(event, ensure_ascii=False))
    return "\n".join(lines) + "\n"


@contextmanager
def _perf_storage():
    """tmp-хранилище на целевом масштабе с подменой путей elo/server/lookups."""
    ids = _model_ids()
    with tempfile.TemporaryDirectory(prefix="bench_perf_") as tmp_str:
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
        _write(paths["models"], _models_yaml(ids))
        _write(
            paths["settings"],
            "current_task: T-001\ntasks:\n"
            + "".join(f"  {t}: active\n" for t in TASKS),
        )
        _write(
            paths["lookups"],
            "agents:\n" + "".join(f"  - Agent{i}\n" for i in range(5))
            + "providers:\n" + "".join(f"  - Prov{i}\n" for i in range(3)),
        )
        for t in TASKS:
            _write(
                paths["tasks"] / f"{t}-perf" / "task.md",
                f'---\nid: {t}\ntitle: "Perf {t}"\nproject: "Benchmark"\n'
                'baseline_commit: ""\n---\n\nСинтетическая задача нагрузочного теста.\n',
            )
        _write(paths["journal"], _journal_text(ids))
        _write(paths["flags"], _flags_yaml(ids, TYPICAL_FLAGS))

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


def _timed(fn, *args, **kwargs):
    """Замер с гигиеной: перед окном собирается мусор тест-харнесса.

    Окно замера — только вызов; уборка объектов, созданных подготовкой
    фикстуры (не часть пользовательского сценария), не попадает внутрь.
    """
    gc.collect()
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0


def _check(label: str, seconds: float, budget: float) -> None:
    status = "OK" if seconds <= budget else "FAIL"
    print(f"  {label:<52} {seconds:6.3f} с  (бюджет {budget:.1f} с)  {status}")
    if seconds > budget:
        FAILURES.append(f"{label}: {seconds:.3f} с > {budget:.1f} с")


def test_perf_budgets() -> None:
    ids = _model_ids()
    with _perf_storage() as paths:
        # 0. Синтетика консистентна: индекс собирается, --check зелёный,
        # повторный run_check() уже не «холодный» по индексу.
        idx = elo.generate_index()
        elo.save_index(idx)
        assert len(idx["elo_history"]) == N_EVENTS, (
            f"в индексе {len(idx['elo_history'])} записей вместо {N_EVENTS}"
        )
        assert not elo.verify_snapshots(elo.load_matchups(), ids), "снэпшоты синтетики расходятся с реплеем"

        server.app.config["TESTING"] = True
        client = server.app.test_client()

        # A. Типовое состояние покрытия: отмечены 100 моделей на T-001.
        data_cache.clear()
        resp, dt = _timed(lambda: client.get("/"))
        assert resp.status_code == 200, f"GET / → {resp.status_code}"
        _check("главная, холодная (типовое покрытие, 100 флагов)", dt, BUDGET_TYPICAL)

        _, dt = _timed(lambda: client.get("/"))
        _check("главная, повторный запрос", dt, BUDGET_TYPICAL)

        filters = [
            ("/?filter=all", "фильтр «Все»"),
            ("/?filter=archived", "фильтр «Архивные»"),
            ("/?agents=Agent1", "фильтр по агенту"),
            ("/?providers=Prov2", "фильтр по компании"),
            ("/?view=highlight", "режим «Подсвечивать»"),
        ]
        for url, label in filters:
            resp, dt = _timed(lambda u=url: client.get(u))
            assert resp.status_code == 200, f"GET {url} → {resp.status_code}"
            _check(label, dt, BUDGET_TYPICAL)
        _, dt = _timed(lambda: client.get("/?filter=all"))
        _check("фильтр «Все», повторный клик", dt, BUDGET_TYPICAL)

        # B. Предельное состояние: отмечены все 1000 моделей на активную
        # задачу. Главная — ≤1 с, повтор — ≤0.5 с; /settings — ≤1 с.
        _write(paths["flags"], _flags_yaml(ids, N_MODELS))
        data_cache.clear()
        resp, dt = _timed(lambda: client.get("/"))
        assert resp.status_code == 200
        _check("главная, холодная (предел: 1000 флагов)", dt, BUDGET_PEAK_MAIN)

        _, dt = _timed(lambda: client.get("/"))
        _check("главная, повторный запрос (предел)", dt, BUDGET_TYPICAL)

        data_cache.clear()
        resp, dt = _timed(lambda: client.get("/settings"))
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200, f"GET /settings → {resp.status_code}"
        assert "открытых" in html and "queue_page=2" in html, "очередь /settings не построена"
        _check("/settings, холодная (очередь, стр. 1)", dt, BUDGET_PAGE)

        resp, dt = _timed(lambda: client.get("/settings?queue_page=2"))
        assert resp.status_code == 200
        _check("/settings (очередь, стр. 2)", dt, BUDGET_PAGE)

        # C. Запись вердикта через веб-UI вместе с пересчётом index.json.
        resp, dt = _timed(lambda: client.post("/verdict", data={
            "model_a": ids[0], "model_b": ids[1],
            "winner": "a", "task": "T-001",
        }))
        assert resp.status_code == 302, f"POST /verdict → {resp.status_code}"
        assert len(elo.load_matchups()) == N_EVENTS + 1, "вердикт не записан в журнал"
        _check("POST /verdict (запись + пересчёт index.json)", dt, BUDGET_PAGE)

        # D. Страницы после изменения данных (мемо пересобирается).
        resp, dt = _timed(lambda: client.get("/history"))
        assert resp.status_code == 200
        assert f"Всего записей: {N_EVENTS + 1}" in resp.get_data(as_text=True), (
            "история не видит новую запись"
        )
        _check("/history (10 001 запись)", dt, BUDGET_PAGE)

        resp, dt = _timed(lambda: client.get("/stats"))
        assert resp.status_code == 200, f"GET /stats → {resp.status_code}"
        _check("/stats", dt, BUDGET_PAGE)

        # E. Проверка целостности журнала и индекса (--check).
        t0 = time.perf_counter()
        rc = elo.run_check()
        dt = time.perf_counter() - t0
        assert rc == 0, "run_check() нашёл проблемы в синтетическом журнале"
        _check("elo.run_check() (журнал + индекс)", dt, BUDGET_CHECK)

    if FAILURES:
        print("\nПревышенные бюджеты:")
        for f in FAILURES:
            print(f"  ✗ {f}")
        raise AssertionError(f"превышено бюджетов: {len(FAILURES)}")
    print("PERF BUDGETS: OK")


if __name__ == "__main__":
    test_perf_budgets()
    print("\nALL PERF TESTS PASSED")
