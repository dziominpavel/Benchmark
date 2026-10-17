#!/usr/bin/env python3
"""
test_trends.py — сверка compute_rank_trends (однопроходный Fenwick) с
наивной эталонной реализацией на синтетических историях.

Проверяет:
  * полное совпадение словарей трендов с эталоном на случайных историях
    (в том числе с принудительными ничьими ELO и застойными моделями)
    при разных window/stale_gap;
  * краевые случаи: пустая история, пул из одной модели, модель без
    личных игр, все модели застойные, события с участниками вне пула.

Запуск: python tools/test_trends.py
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import DEFAULT_ELO, expected_score, k_factor, update_elo
from render_helpers import (
    STALE_GLOBAL_GAP,
    TREND_WINDOW,
    compute_rank_trends,
)


def _rank(pool: list[str], elo: dict[str, int]) -> dict[str, int]:
    """Независимый эталон ранга: ELO по убыванию, затем id по возрастанию."""
    ordered = sorted(pool, key=lambda mid: (-elo.get(mid, DEFAULT_ELO), mid))
    return {mid: i + 1 for i, mid in enumerate(ordered)}


def naive_rank_trends(
    elo_history: list[dict],
    pool_ids: list[str],
    current_elo: dict[str, int],
    window: int = TREND_WINDOW,
    stale_gap: int = STALE_GLOBAL_GAP,
) -> dict[str, dict]:
    """Эталон: для каждого среза — пересчёт снимка с нуля (до оптимизации)."""
    pool = list(pool_ids)
    pool_set = set(pool)
    history = sorted(elo_history or [], key=lambda e: e.get("seq", 0))

    rank_now_map = _rank(pool, current_elo)

    personal: dict[str, list[int]] = {mid: [] for mid in pool}
    for e in history:
        seq = e.get("seq", 0)
        a_id = e.get("model_a_id", "")
        b_id = e.get("model_b_id", "")
        if a_id in pool_set:
            personal[a_id].append(seq)
        if b_id in pool_set:
            personal[b_id].append(seq)

    baseline: dict[str, int] = {}
    stale: set[str] = set()
    max_seq = max((e.get("seq", 0) for e in history), default=0)
    for mid in pool:
        seqs = personal[mid]
        if len(seqs) >= window + 1:
            if history and max_seq - seqs[-1] >= stale_gap:
                stale.add(mid)
            else:
                baseline[mid] = seqs[len(seqs) - window - 1]

    snapshots: dict[int, dict[str, int]] = {}
    for cut in sorted(set(baseline.values())):
        snap: dict[str, int] = {mid: DEFAULT_ELO for mid in pool}
        for e in history:
            if e.get("seq", 0) > cut:
                break
            a_id = e.get("model_a_id", "")
            b_id = e.get("model_b_id", "")
            if a_id in pool_set:
                val = e.get("elo_a", {}).get("after")
                if val is not None:
                    snap[a_id] = val
            if b_id in pool_set:
                val = e.get("elo_b", {}).get("after")
                if val is not None:
                    snap[b_id] = val
        snapshots[cut] = snap

    trends: dict[str, dict] = {}
    for mid in pool:
        rank_now = rank_now_map[mid]
        if mid in stale:
            gap = max_seq - personal[mid][-1]
            trends[mid] = {
                "delta": None,
                "label": "–",
                "arrow": "",
                "num": "–",
                "css": "history-delta-neutral",
                "title": (
                    f"без личных игр в последних {stale_gap} прогонах "
                    f"(последняя: {gap} назад)"
                ),
                "rank_then": None,
                "rank_now": rank_now,
                "elo_delta": None,
                "has_baseline": False,
                "stale": True,
            }
            continue
        if mid not in baseline:
            trends[mid] = {
                "delta": None,
                "label": "–",
                "arrow": "",
                "num": "–",
                "css": "history-delta-neutral",
                "title": "мало игр для тренда: нужно 6+ личных игр",
                "rank_then": None,
                "rank_now": rank_now,
                "elo_delta": None,
                "has_baseline": False,
            }
            continue
        snap = snapshots[baseline[mid]]
        rank_then = _rank(pool, snap)[mid]
        delta = rank_then - rank_now
        elo_delta = current_elo.get(mid, DEFAULT_ELO) - snap.get(mid, DEFAULT_ELO)
        if delta > 0:
            label, css = f"↑{delta}", "history-delta-up"
            arrow, num = "↑", str(delta)
        elif delta < 0:
            label, css = f"↓{-delta}", "history-delta-down"
            arrow, num = "↓", str(-delta)
        else:
            label, css = "=", "history-delta-neutral"
            arrow, num = "", "="
        trends[mid] = {
            "delta": delta,
            "label": label,
            "arrow": arrow,
            "num": num,
            "css": css,
            "title": (
                f"5 личных игр · ΔELO {elo_delta:+d} · "
                f"место {rank_then}→{rank_now}"
            ),
            "rank_then": rank_then,
            "rank_now": rank_now,
            "elo_delta": elo_delta,
            "has_baseline": True,
        }
    return trends


def _make_history(
    rng: random.Random,
    ids: list[str],
    outside: list[str],
    n_events: int,
    value_pool: list[int] | None = None,
    outside_only_tail: int = 0,
) -> tuple[list[dict], dict[str, int]]:
    """Синтетическая история по правилам движка (update_elo/k_factor).

    outside_only_tail: последние N событий — только участники вне пула
    (для проверки застойности без изменения ELO пула).
    """
    all_ids = ids + outside
    elo: dict[str, int] = {mid: DEFAULT_ELO for mid in all_ids}
    games: dict[str, int] = {mid: 0 for mid in all_ids}
    history: list[dict] = []
    for seq in range(1, n_events + 1):
        if outside_only_tail and seq > n_events - outside_only_tail:
            a, b = rng.sample(outside, 2)
        else:
            a, b = rng.sample(all_ids, 2)
        r_a, r_b = elo[a], elo[b]
        e_a = expected_score(r_a, r_b)
        e_b = 1.0 - e_a
        if rng.random() < e_a:
            s_a, s_b = 1.0, 0.0
        else:
            s_a, s_b = 0.0, 1.0
        new_a, new_b = update_elo(
            r_a, k_factor(games[a]), s_a, e_a,
            r_b, k_factor(games[b]), s_b, e_b,
        )
        if value_pool:
            # Принудительные ничьи ELO: значения из маленького набора.
            new_a = rng.choice(value_pool)
            new_b = rng.choice(value_pool)
        history.append({
            "seq": seq,
            "model_a_id": a,
            "model_b_id": b,
            "elo_a": {"before": r_a, "after": new_a},
            "elo_b": {"before": r_b, "after": new_b},
        })
        elo[a], elo[b] = new_a, new_b
        games[a] += 1
        games[b] += 1
    return history, elo


def _assert_same(label: str, history, pool, current, window, stale_gap):
    got = compute_rank_trends(
        history, pool, current, window=window, stale_gap=stale_gap,
    )
    want = naive_rank_trends(
        history, pool, current, window=window, stale_gap=stale_gap,
    )
    assert got == want, f"{label}: расхождение с эталоном"
    # Структурные инварианты результата
    for mid, tr in got.items():
        assert set(tr) == set(want[mid])
        if tr["has_baseline"]:
            assert tr["delta"] == tr["rank_then"] - tr["rank_now"]
            assert tr["rank_then"] is not None and tr["rank_now"] is not None


def test_matches_naive_random():
    rng = random.Random(42)
    cases = [
        # (моделей в пуле, событий, window, stale_gap)
        (8, 60, 5, 30),
        (12, 120, 5, 30),
        (20, 300, 5, 30),
        (12, 200, 3, 10),
        (10, 80, 5, 20),
        (30, 500, 5, 100),
        (6, 40, 5, 5),
        (15, 250, 2, 8),
    ]
    for n_models, n_events, window, stale_gap in cases:
        ids = [f"m{i:03d}" for i in range(n_models)]
        history, elo = _make_history(rng, ids, [], n_events)
        _assert_same(
            f"random {n_models}/{n_events}/w{window}/g{stale_gap}",
            history, ids, elo, window, stale_gap,
        )
    print("trends vs naive (random): OK")


def test_matches_naive_with_elo_ties():
    rng = random.Random(7)
    ids = [f"m{i:02d}" for i in range(10)]
    values = [1200, 1240, 1240, 1280, 1120]
    history, elo = _make_history(rng, ids, [], 120, value_pool=values)
    _assert_same("ties w5", history, ids, elo, 5, 30)
    _assert_same("ties w2", history, ids, elo, 2, 12)
    print("trends vs naive (ELO ties): OK")


def test_matches_naive_with_stale_tail():
    rng = random.Random(11)
    ids = [f"m{i:02d}" for i in range(8)]
    outside = [f"x{i:02d}" for i in range(3)]
    history, elo = _make_history(
        rng, ids, outside, 90, outside_only_tail=40,
    )
    _assert_same("stale tail", history, ids, elo, 5, 30)
    got = compute_rank_trends(history, ids, elo, window=5, stale_gap=30)
    stale_count = sum(1 for tr in got.values() if tr.get("stale"))
    assert stale_count > 0, "хвост без игр пула должен оставить застойные модели"
    print(f"trends stale tail ({stale_count} stale): OK")


def test_edge_empty_history():
    pool = ["a", "b", "c"]
    current = {mid: DEFAULT_ELO for mid in pool}
    _assert_same("empty", [], pool, current, 5, 30)
    got = compute_rank_trends([], pool, current)
    assert all(tr["has_baseline"] is False for tr in got.values())
    assert all(tr["rank_now"] in (1, 2, 3) for tr in got.values())
    print("trends empty history: OK")


def test_edge_single_model_pool():
    rng = random.Random(3)
    pool = ["m0"]
    outside = ["x0", "x1"]
    history, elo = _make_history(rng, pool, outside, 30)
    _assert_same("single pool", history, pool, elo, 5, 30)
    got = compute_rank_trends(history, pool, elo, window=5, stale_gap=30)
    assert got["m0"]["rank_now"] == 1
    if got["m0"]["has_baseline"]:
        assert got["m0"]["delta"] == 0, "в пуле из одной модели дельта = 0"
    print("trends single-model pool: OK")


def test_edge_participants_outside_pool():
    rng = random.Random(5)
    ids = [f"m{i:02d}" for i in range(6)]
    outside = [f"x{i:02d}" for i in range(6)]
    history, elo = _make_history(rng, ids, outside, 150)
    _assert_same("mixed pool", history, ids, elo, 5, 30)
    _assert_same("mixed pool w1", history, ids, elo, 1, 30)
    print("trends participants outside pool: OK")


def test_edge_empty_pool():
    rng = random.Random(9)
    history, _ = _make_history(rng, ["a", "b"], [], 10)
    got = compute_rank_trends(history, [], {})
    assert got == {}
    print("trends empty pool: OK")


if __name__ == "__main__":
    test_matches_naive_random()
    test_matches_naive_with_elo_ties()
    test_matches_naive_with_stale_tail()
    test_edge_empty_history()
    test_edge_single_model_pool()
    test_edge_participants_outside_pool()
    test_edge_empty_pool()
    print("\nALL TRENDS TESTS PASSED")
