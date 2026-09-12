#!/usr/bin/env python3
"""test_pairing.py — answer-aware рекомендации get_recommendations.

Герметичные тесты на подменённых данных (память, без изменения
models.yaml / index.json): READY-only, приоритет T-001, топ-1,
рематч-fallback, исключение архивных, поля записи.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import server
from server import get_recommendations


def _run_case(index_models, settings, flags, stats, verdict_tasks, top_n=1):
    """Вызывает get_recommendations на фикстурах с подменой источников.

    index_models: [(id, elo, games, status)].
    settings: {"current_task": ..., "tasks": {id: status}}.
    flags: {task: {model: bool}}.
    stats: {(a, b): (games, wins_a, wins_b)}.
    verdict_tasks: {(a, b): {task, ...}}.
    """
    index_data = {
        "models": {
            mid: {"elo": elo, "games": games, "status": status}
            for mid, elo, games, status in index_models
        }
    }
    fake_stats = {
        frozenset(pair): {"games": g, "wins": {pair[0]: wa, pair[1]: wb}}
        for pair, (g, wa, wb) in stats.items()
    }
    fake_verdicts = {
        frozenset(pair): set(tasks) for pair, tasks in verdict_tasks.items()
    }
    active = sorted(t for t, s in settings["tasks"].items() if s == "active")

    saved = (
        server.get_pair_stats, server.get_pair_task_verdicts,
        server.load_settings, server.load_answer_flags,
        server.get_model_name_map, server.active_tasks,
    )
    server.get_pair_stats = lambda: fake_stats
    server.get_pair_task_verdicts = lambda: fake_verdicts
    server.load_settings = lambda: settings
    server.load_answer_flags = lambda: flags
    server.get_model_name_map = lambda: {m[0]: m[0] for m in index_models}
    server.active_tasks = lambda _s=None: active
    try:
        return get_recommendations(index_data, top_n=top_n)
    finally:
        (server.get_pair_stats, server.get_pair_task_verdicts,
         server.load_settings, server.load_answer_flags,
         server.get_model_name_map, server.active_tasks) = saved


SETTINGS_2 = {"current_task": "T-001",
              "tasks": {"T-001": "active", "T-002": "active"}}
ABC = [("A", 1200, 10, "active"), ("B", 1200, 10, "active"),
       ("C", 1200, 10, "active")]


def test_ready_priority_t001():
    """READY из T-001 выше любого READY из T-002; BLOCKED-пары невидимы."""
    flags = {"T-001": {"A": True, "B": True},
             "T-002": {"A": True, "B": True, "C": True}}
    recs = _run_case(ABC, SETTINGS_2, flags, {}, {})
    assert len(recs) == 1, recs
    rec = recs[0]
    assert (rec["model_a"], rec["model_b"]) == ("A", "B"), rec
    assert rec["recommended_task"] == "T-001", rec
    assert rec["is_rematch"] is False, rec
    print("ready priority T-001: OK")


def test_blocked_new_model():
    """D без ответов нигде не рекомендуется; с флагом — догоняет T-001."""
    abcd = ABC + [("D", 1200, 0, "active")]
    flags = {"T-001": {"A": True, "B": True, "C": True},
             "T-002": {"A": True, "B": True, "C": True}}
    recs = _run_case(abcd, SETTINGS_2, flags, {}, {})
    assert len(recs) == 1, recs
    assert "D" not in (recs[0]["model_a"], recs[0]["model_b"]), recs
    assert recs[0]["recommended_task"] == "T-001", recs

    flags_d = {"T-001": {"A": True, "B": True, "C": True, "D": True},
               "T-002": {"A": True, "B": True, "C": True}}
    recs_d = _run_case(abcd, SETTINGS_2, flags_d, {}, {})
    assert len(recs_d) == 1, recs_d
    # D с 0 игр (тир 0) выше сыгранных пар тира 2 внутри T-001
    assert "D" in (recs_d[0]["model_a"], recs_d[0]["model_b"]), recs_d
    assert recs_d[0]["recommended_task"] == "T-001", recs_d
    print("blocked new model: OK")


def test_t002_waits_for_t001():
    """Пара с вердиктом в T-001 остаётся кандидатом в T-002, но топ-1 —
    из T-001, пока там есть READY."""
    flags = {"T-001": {"A": True, "B": True, "C": True},
             "T-002": {"A": True, "B": True, "C": True}}
    stats = {("A", "B"): (1, 1, 0)}
    verdicts = {("A", "B"): {"T-001"}}
    recs = _run_case(ABC, SETTINGS_2, flags, stats, verdicts)
    assert len(recs) == 1, recs
    assert recs[0]["recommended_task"] == "T-001", recs
    assert frozenset((recs[0]["model_a"], recs[0]["model_b"])) != {"A", "B"}, recs

    # T-001 полностью закрыт → топ-1 уходит в T-002 (ячейка A-B READY)
    verdicts_closed = {("A", "B"): {"T-001"}, ("A", "C"): {"T-001"},
                       ("B", "C"): {"T-001"}}
    recs2 = _run_case(ABC, SETTINGS_2, flags, stats, verdicts_closed)
    assert len(recs2) == 1, recs2
    assert recs2[0]["recommended_task"] == "T-002", recs2
    assert recs2[0]["is_rematch"] is False, recs2
    print("T-002 waits for T-001: OK")


def test_rematch_fallback_full():
    """READY пуст, всё DONE → 1 рематч с min pair_games и первым таском."""
    flags = {"T-001": {"A": True, "B": True, "C": True}}
    settings = {"current_task": "T-001", "tasks": {"T-001": "active"}}
    stats = {("A", "B"): (2, 1, 1), ("A", "C"): (2, 1, 1),
             ("B", "C"): (1, 1, 0)}
    verdicts = {("A", "B"): {"T-001"}, ("A", "C"): {"T-001"},
                ("B", "C"): {"T-001"}}
    recs = _run_case(ABC, settings, flags, stats, verdicts)
    assert len(recs) == 1, recs
    rec = recs[0]
    assert rec["is_rematch"] is True, rec
    assert rec["pair_games"] == 1, rec
    assert frozenset((rec["model_a"], rec["model_b"])) == {"B", "C"}, rec
    assert rec["recommended_task"] == "T-001", rec
    assert "reason" not in rec, rec
    print("rematch fallback (full): OK")


def test_rematch_fallback_all_blocked():
    """READY и DONE пусты (всё BLOCKED) → 1 рематч без учёта флагов."""
    recs = _run_case(ABC, SETTINGS_2, {}, {}, {})
    assert len(recs) == 1, recs
    assert recs[0]["is_rematch"] is True, recs
    assert recs[0]["recommended_task"] == "T-001", recs
    print("rematch fallback (all blocked): OK")


def test_archived_excluded():
    """Архивная модель не попадает ни в обычный режим, ни в рематчи."""
    models = [("A", 1200, 10, "active"), ("B", 1200, 10, "active"),
              ("C", 1200, 10, "archived")]
    flags = {"T-001": {"A": True, "B": True, "C": True}}
    settings = {"current_task": "T-001", "tasks": {"T-001": "active"}}
    recs = _run_case(models, settings, flags, {}, {})
    assert len(recs) == 1, recs
    assert set((recs[0]["model_a"], recs[0]["model_b"])) == {"A", "B"}, recs

    verdicts = {("A", "B"): {"T-001"}}
    stats = {("A", "B"): (1, 1, 0)}
    recs_re = _run_case(models, settings, flags, stats, verdicts)
    assert len(recs_re) == 1, recs_re
    assert set((recs_re[0]["model_a"], recs_re[0]["model_b"])) == {"A", "B"}, recs_re
    print("archived excluded: OK")


def test_single_model_empty():
    """Меньше двух активных моделей → пусто."""
    recs = _run_case([("A", 1200, 0, "active")], SETTINGS_2, {}, {}, {})
    assert recs == [], recs
    print("single model empty: OK")


def test_record_fields():
    """Поля записи: без reason, h2h-строки, score, is_rematch."""
    flags = {"T-001": {"A": True, "B": True}}
    models = [("A", 1200, 5, "active"), ("B", 1200, 5, "active")]
    settings = {"current_task": "T-001", "tasks": {"T-001": "active"}}
    recs = _run_case(models, settings, flags, {}, {})
    rec = recs[0]
    assert "reason" not in rec, rec
    assert rec["h2h_label"] == "личные встречи: не встречались", rec
    assert rec["score"] == 1.0, rec
    assert rec["is_rematch"] is False, rec

    stats = {("A", "B"): (2, 1, 1)}
    verdicts = {("A", "B"): {"T-001"}}
    recs_re = _run_case(models, settings, flags, stats, verdicts)
    assert recs_re[0]["h2h_label"] == "личные встречи: 2 · счёт 1:1", recs_re[0]
    print("record fields: OK")


def main() -> int:
    test_ready_priority_t001()
    test_blocked_new_model()
    test_t002_waits_for_t001()
    test_rematch_fallback_full()
    test_rematch_fallback_all_blocked()
    test_archived_excluded()
    test_single_model_empty()
    test_record_fields()
    print("\nALL PAIRING TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
