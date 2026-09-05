#!/usr/bin/env python3
"""Unit tests for elo.py — tasks 2.1-2.6."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from elo import expected_score, k_factor, round_elo, update_elo, recalculate


def test_expected_score():
    # 2.1: equal models -> 0.50
    e = expected_score(1200, 1200)
    assert abs(e - 0.50) < 0.001, f"Equal models: expected 0.50, got {e}"
    # favorite 1300 vs 1100 -> ~0.76
    e = expected_score(1300, 1100)
    assert abs(e - 0.76) < 0.01, f"Favorite: expected ~0.76, got {e}"
    print("2.1 expected_score: OK")


def test_k_factor():
    assert k_factor(0) == 40
    assert k_factor(9) == 40
    assert k_factor(10) == 32
    assert k_factor(15) == 32
    assert k_factor(30) == 32
    assert k_factor(31) == 24
    assert k_factor(35) == 24
    print("2.2 k_factor: OK")


def test_update_elo():
    # Favorite wins (expected) - small delta
    na, nb = update_elo(1300, 32, 1.0, 0.76, 1100, 32, 0.0, 0.24)
    assert na == 1308, f"Favorite win A: expected 1308, got {na}"
    assert nb == 1092, f"Favorite win B: expected 1092, got {nb}"
    # Underdog wins (upset) - large delta
    na, nb = update_elo(1100, 40, 1.0, 0.24, 1300, 24, 0.0, 0.76)
    assert na == 1130, f"Upset A: expected 1130, got {na}"
    assert nb == 1282, f"Upset B: expected 1282, got {nb}"
    print("2.3 update_elo: OK")


def test_round_elo():
    assert round_elo(1216.5) == 1216, f"1216.5 -> 1216 (bankers), got {round_elo(1216.5)}"
    assert round_elo(1217.5) == 1218, f"1217.5 -> 1218 (bankers), got {round_elo(1217.5)}"
    assert round_elo(1216.7) == 1217
    print("2.6 round_elo: OK")


def test_recalculate():
    matchups = [
        {"task": "T-001", "model_a": "A", "model_b": "B", "winner": "a", "date": "2026-09-05", "_matchup_id": "T-001/001"},
        {"task": "T-001", "model_a": "A", "model_b": "C", "winner": "a", "date": "2026-09-05", "_matchup_id": "T-001/002"},
        {"task": "T-001", "model_a": "B", "model_b": "C", "winner": "a", "date": "2026-09-05", "_matchup_id": "T-001/003"},
    ]
    result = recalculate(matchups, ["A", "B", "C"])
    a_elo = result["models"]["A"]["elo"]
    b_elo = result["models"]["B"]["elo"]
    c_elo = result["models"]["C"]["elo"]
    assert a_elo > b_elo > c_elo, f"ELO order wrong: A={a_elo} B={b_elo} C={c_elo}"
    assert result["models"]["A"]["wins"] == 2
    assert result["models"]["C"]["losses"] == 2
    assert result["models"]["B"]["wins"] == 1 and result["models"]["B"]["losses"] == 1
    print(f"2.4 recalculate: OK (A={a_elo} B={b_elo} C={c_elo})")


def test_elo_history():
    matchups = [
        {"task": "T-001", "model_a": "A", "model_b": "B", "winner": "a", "date": "2026-09-05", "_matchup_id": "T-001/001"},
    ]
    result = recalculate(matchups, ["A", "B"])
    history = result["elo_history"]
    assert len(history) == 1, f"1 matchup = 1 entry, got {len(history)}"
    h = history[0]
    assert h["matchup"] == "T-001/001"
    assert h["model_a_id"] == "A"
    assert h["model_b_id"] == "B"
    assert h["winner"] == "a"
    assert h["elo_a"] == {"before": 1200, "after": 1220, "delta": 20}
    assert h["elo_b"] == {"before": 1200, "after": 1180, "delta": -20}
    print("2.5 elo_history: OK")


def test_seq_ordering():
    """seq переопределяет порядок: вердикт с большим seq применяется позже,
    даже если его дата раньше (запись задним числом идёт по времени ЗАПИСИ)."""
    matchups = [
        # seq=2, но date раньше — порядок реплея по seq, не по date
        {"task": "T-001", "model_a": "A", "model_b": "B", "winner": "b",
         "date": "2026-09-04", "seq": 2, "_matchup_id": "T-001/002"},
        {"task": "T-001", "model_a": "A", "model_b": "B", "winner": "a",
         "date": "2026-09-05", "seq": 1, "_matchup_id": "T-001/001"},
    ]
    # recalculate получает уже отсортированный список — сортируем как load_matchups
    from elo import matchup_sort_key
    matchups.sort(key=matchup_sort_key)
    result = recalculate(matchups, ["A", "B"])
    # Оба матча между равными (1200) — сначала A выигрывает (+20/-20),
    # затем B выигрывает у 1220 — аутсайдер-B получает больше.
    a = result["models"]["A"]["elo"]
    b = result["models"]["B"]["elo"]
    assert b > a, f"Seq-ordering wrong: A={a} B={b} (B должен выиграть после проигрыша)"
    print(f"seq ordering: OK (A={a} B={b})")


def test_void():
    """Tombstone аннулирует вердикт — он не участвует в реплее."""
    matchups = [
        {"task": "T-001", "model_a": "A", "model_b": "B", "winner": "a",
         "date": "2026-09-05", "seq": 1, "_matchup_id": "T-001/001"},
        {"task": "T-001", "void_of": "T-001/001",
         "date": "2026-09-05", "seq": 2, "_matchup_id": "T-001/002"},
    ]
    from elo import matchup_sort_key
    matchups.sort(key=matchup_sort_key)
    result = recalculate(matchups, ["A", "B"])
    assert result["models"]["A"]["elo"] == 1200, "Аннулированный вердикт не должен влиять"
    assert result["models"]["A"]["games"] == 0
    assert "T-001/001" in result["voided"]
    print("void/tombstone: OK")


def test_unknown_models_warn():
    """Неразрешённые модели — громкий warning, не тихий skip."""
    matchups = [
        {"task": "T-001", "model_a": "unknown-X", "model_b": "unknown-Y", "winner": "a",
         "date": "2026-09-05", "seq": 1, "_matchup_id": "T-001/001"},
    ]
    result = recalculate(matchups, ["A", "B"])
    assert result["warnings"], "Должен быть warning о неразрешённых моделях"
    assert "T-001/001" in result["skipped"]
    print("unknown models warning: OK")


def test_recorded_at_required():
    """verify_snapshots требует recorded_at."""
    from elo import verify_snapshots
    matchups = [
        {"task": "T-001", "model_a": "A", "model_b": "B", "winner": "a",
         "date": "2026-09-05", "seq": 1,
         "_matchup_id": "T-001/001"},
    ]
    problems = verify_snapshots(matchups, ["A", "B"])
    assert any("recorded_at" in p for p in problems), "Должна быть проблема с recorded_at"
    print("recorded_at required: OK")


def test_collect_tasks_info():
    """collect_tasks_info корректно извлекает T-001 из имени директории."""
    from elo import collect_tasks_info
    # Функция читает реальные директории; проверим, что T-001 существует,
    # а ключа 'T' нет.
    info = collect_tasks_info()
    assert "T-001" in info, f"ожидался T-001, получили {list(info.keys())}"
    assert "T" not in info, f"не должен быть ключ T, получили {list(info.keys())}"
    print("collect_tasks_info: OK")


def test_snapshot_verification():
    """verify_snapshots детектит подделку записанного снэпшота."""
    from elo import verify_snapshots, matchup_sort_key
    # Вердикт с корректным снэпшотом (1200→1220 / 1200→1180)
    matchups = [
        {"task": "T-001", "model_a": "A", "model_b": "B", "winner": "a",
         "date": "2026-09-05", "seq": 1, "recorded_at": "2026-09-05T10:00:00+03:00",
         "_matchup_id": "T-001/001",
         "elo": {"A": {"before": 1200, "after": 1220, "delta": 20},
                 "B": {"before": 1200, "after": 1180, "delta": -20}}},
    ]
    matchups.sort(key=matchup_sort_key)
    problems = verify_snapshots(matchups, ["A", "B"])
    assert not problems, f"Корректный снэпшот не должен давать проблем: {problems}"

    # Подделанный снэпшот
    matchups[0]["elo"]["A"]["after"] = 1250
    problems = verify_snapshots(matchups, ["A", "B"])
    assert problems, "Подделанный снэпшот должен детектироваться"
    print("snapshot verification: OK")


if __name__ == "__main__":
    test_expected_score()
    test_k_factor()
    test_update_elo()
    test_round_elo()
    test_recalculate()
    test_elo_history()
    test_seq_ordering()
    test_void()
    test_unknown_models_warn()
    test_recorded_at_required()
    test_collect_tasks_info()
    test_snapshot_verification()
    print("\nALL ELO TESTS PASSED")
