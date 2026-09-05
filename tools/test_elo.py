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
    assert len(history) == 2, f"1 matchup x 2 models = 2 entries, got {len(history)}"
    for h in history:
        assert "model" in h and "elo" in h and "delta" in h and "after_matchup" in h
    print("2.5 elo_history: OK")


if __name__ == "__main__":
    test_expected_score()
    test_k_factor()
    test_update_elo()
    test_round_elo()
    test_recalculate()
    test_elo_history()
    print("\nALL ELO TESTS PASSED")
