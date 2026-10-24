#!/usr/bin/env python3
"""
test_trends.py — сверка compute_rating_momentum с наивной эталонной
реализацией на синтетических историях.

Проверяет:
  * полное совпадение числовых полей с эталоном на случайных историях
    (включая ничьи и «остывшие» модели) при разных окнах и порогах;
  * краевые случаи: пустая история, пул из одной модели, участники вне
    пула, пустой пул, ровно 15 и 16 личных игр, граница z, свежесть
    14/15 дней, счёт побед-ничьих-поражений и формат тултипа;
  * независимость результата от появления новых моделей вне пула.

Запуск: python tools/test_trends.py
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import DEFAULT_ELO, expected_score, k_factor, update_elo
from render_helpers import (
    MOMENTUM_MAX_AGE_DAYS,
    MOMENTUM_MIN_GAMES,
    MOMENTUM_WINDOW,
    MOMENTUM_Z_THRESHOLD,
    _momentum_state,
    compute_rating_momentum,
)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def naive_momentum_state(
    records: list[dict],
    window: int,
    min_games: int,
    z_threshold: float,
    max_age_days: int,
    final_delta: int | None = None,
) -> str:
    """Эталон: вход по двум подряд заметным срезам + удержание."""
    state = ""
    prev_z: float | None = None
    prev_date: date | None = None
    for index, record in enumerate(records):
        recent = records[max(0, index + 1 - window):index + 1]
        if final_delta is not None and index == len(records) - 1:
            delta = final_delta
        else:
            delta = sum(r["delta"] for r in recent)
        variance = sum(
            (r["k"] ** 2)
            * expected_score(r["elo_before"], r["opp_before"])
            * (1.0 - expected_score(r["elo_before"], r["opp_before"]))
            for r in recent
        )
        sd = variance ** 0.5
        z = delta / sd if sd > 0 else 0.0
        current = _parse_date(record.get("date", ""))
        if index + 1 >= min_games:
            if (
                prev_date is not None
                and current is not None
                and (current - prev_date).days > max_age_days
            ):
                state = ""
                prev_z = None
            if state == "↑" and z >= z_threshold - 1e-9:
                pass
            elif state == "↓" and z <= -z_threshold + 1e-9:
                pass
            elif (
                z >= z_threshold - 1e-9
                and prev_z is not None
                and prev_z >= z_threshold - 1e-9
                and record["delta"] > 0
            ):
                state = "↑"
            elif (
                z <= -z_threshold + 1e-9
                and prev_z is not None
                and prev_z <= -z_threshold + 1e-9
                and record["delta"] < 0
            ):
                state = "↓"
            else:
                state = ""
        prev_z = z
        if current is not None:
            prev_date = current
    return state


def naive_rating_momentum(
    elo_history: list[dict],
    pool_ids: list[str],
    current_elo: dict[str, int],
    window: int = MOMENTUM_WINDOW,
    min_games: int = MOMENTUM_MIN_GAMES,
    z_threshold: float = MOMENTUM_Z_THRESHOLD,
    max_age_days: int = MOMENTUM_MAX_AGE_DAYS,
) -> dict[str, dict]:
    """Эталон: отдельный проход по личным играм каждой модели."""
    pool = list(pool_ids)
    pool_set = set(pool)
    history = sorted(elo_history or [], key=lambda e: e.get("seq", 0))

    personal: dict[str, list[dict]] = {mid: [] for mid in pool}
    games_before: dict[str, int] = {mid: 0 for mid in pool}
    all_dates: list[date] = []
    for event in history:
        parsed = _parse_date(event.get("date", ""))
        if parsed is not None:
            all_dates.append(parsed)
        for side, own_key, opp_key in (
            ("model_a_id", "elo_a", "elo_b"),
            ("model_b_id", "elo_b", "elo_a"),
        ):
            mid = event.get(side, "")
            if mid not in pool_set:
                continue
            own = event.get(own_key) or {}
            opp = event.get(opp_key) or {}
            before, after = own.get("before"), own.get("after")
            if before is None or after is None:
                continue
            winner = event.get("winner")
            if winner == "draw":
                result = 0.5
            elif (winner == "a" and side == "model_a_id") or (
                winner == "b" and side == "model_b_id"
            ):
                result = 1.0
            elif winner in ("a", "b"):
                result = 0.0
            else:
                continue
            delta = own.get("delta")
            if delta is None:
                delta = int(after) - int(before)
            personal[mid].append({
                "date": str(event.get("date", "") or ""),
                "delta": int(delta),
                "elo_before": int(before),
                "elo_after": int(after),
                "opp_before": int(opp.get("before", DEFAULT_ELO)),
                "result": result,
                "k": k_factor(games_before[mid]),
            })
            games_before[mid] += 1

    fresh_date = max(all_dates) if all_dates else None
    out: dict[str, dict] = {}
    for mid in pool:
        records = personal[mid]
        last_date = records[-1]["date"] if records else ""
        item = {
            "arrow": "",
            "css": "history-delta-neutral",
            "delta": None,
            "z": None,
            "games_in_window": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "last_date": last_date,
            "has_value": False,
            "title": "",
        }
        if len(records) < min_games:
            item["title"] = f"мало игр для тренда: нужно {min_games}+ личных игр"
            out[mid] = item
            continue

        recent = records[-window:]
        wins = sum(1 for r in recent if r["result"] == 1.0)
        draws = sum(1 for r in recent if r["result"] == 0.5)
        losses = sum(1 for r in recent if r["result"] == 0.0)
        delta = int(current_elo.get(mid, recent[-1]["elo_after"])) - int(
            recent[0]["elo_before"]
        )
        variance = sum(
            (r["k"] ** 2)
            * expected_score(r["elo_before"], r["opp_before"])
            * (1.0 - expected_score(r["elo_before"], r["opp_before"]))
            for r in recent
        )
        sd = variance ** 0.5
        z = delta / sd if sd > 0 else 0.0
        state = naive_momentum_state(
            records, window, min_games, z_threshold, max_age_days,
            final_delta=delta,
        )
        last_parsed = _parse_date(last_date)
        fresh = (
            fresh_date is not None
            and last_parsed is not None
            and (fresh_date - last_parsed).days <= max_age_days
        )
        item.update({
            "delta": delta,
            "z": z,
            "games_in_window": len(recent),
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "has_value": fresh,
        })
        if not fresh:
            item["title"] = f"нет личных игр в последних {max_age_days} днях"
        elif state:
            item["arrow"] = state
            item["css"] = (
                "history-delta-up" if state == "↑" else "history-delta-down"
            )
            item["title"] = "tooltip"
        out[mid] = item
    return out


def _make_history(
    rng: random.Random,
    ids: list[str],
    outside: list[str],
    n_events: int,
    draw_prob: float = 0.0,
    dates: list[str] | None = None,
    outside_only_tail: int = 0,
) -> tuple[list[dict], dict[str, int]]:
    """Синтетическая история по правилам движка (update_elo/k_factor)."""
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
        if rng.random() < draw_prob:
            winner, s_a, s_b = "draw", 0.5, 0.5
        elif rng.random() < e_a:
            winner, s_a, s_b = "a", 1.0, 0.0
        else:
            winner, s_a, s_b = "b", 0.0, 1.0
        new_a, new_b = update_elo(
            r_a, k_factor(games[a]), s_a, e_a,
            r_b, k_factor(games[b]), s_b, 1.0 - e_a,
        )
        date_str = dates[seq - 1] if dates else "2026-01-02"
        history.append({
            "seq": seq,
            "date": date_str,
            "model_a_id": a,
            "model_b_id": b,
            "winner": winner,
            "elo_a": {"before": r_a, "after": new_a, "delta": new_a - r_a},
            "elo_b": {"before": r_b, "after": new_b, "delta": new_b - r_b},
        })
        elo[a], elo[b] = new_a, new_b
        games[a] += 1
        games[b] += 1
    return history, elo


def _fixed_history(
    results: list[str], last_date: str = "2026-01-02",
) -> tuple[list[dict], dict[str, int]]:
    """m0 против x0 по заданной строке исходов ('a'/'b'/'draw')."""
    elo = {"m0": DEFAULT_ELO, "x0": DEFAULT_ELO}
    games = {"m0": 0, "x0": 0}
    history: list[dict] = []
    for seq, winner in enumerate(results, start=1):
        before_a, before_b = elo["m0"], elo["x0"]
        if winner == "draw":
            s_a = s_b = 0.5
        elif winner == "a":
            s_a, s_b = 1.0, 0.0
        else:
            s_a, s_b = 0.0, 1.0
        e_a = expected_score(before_a, before_b)
        new_a, new_b = update_elo(
            before_a, k_factor(games["m0"]), s_a, e_a,
            before_b, k_factor(games["x0"]), s_b, 1.0 - e_a,
        )
        history.append({
            "seq": seq,
            "date": last_date,
            "model_a_id": "m0",
            "model_b_id": "x0",
            "winner": winner,
            "elo_a": {"before": before_a, "after": new_a, "delta": new_a - before_a},
            "elo_b": {"before": before_b, "after": new_b, "delta": new_b - before_b},
        })
        elo["m0"], elo["x0"] = new_a, new_b
        games["m0"] += 1
        games["x0"] += 1
    return history, elo


def _outside_event(seq: int, date_str: str) -> dict:
    """Событие между моделями вне пула: меняет только свежесть журнала."""
    return {
        "seq": seq,
        "date": date_str,
        "model_a_id": "x1",
        "model_b_id": "x2",
        "winner": "a",
        "elo_a": {"before": DEFAULT_ELO, "after": DEFAULT_ELO + 10, "delta": 10},
        "elo_b": {"before": DEFAULT_ELO, "after": DEFAULT_ELO - 10, "delta": -10},
    }


def _assert_same(label: str, history, pool, current, **kwargs):
    got = compute_rating_momentum(history, pool, current, **kwargs)
    want = naive_rating_momentum(history, pool, current, **kwargs)
    assert set(got) == set(want), f"{label}: разный набор моделей"
    for mid in pool:
        g, w = got[mid], want[mid]
        for key in (
            "arrow", "css", "delta", "games_in_window", "wins", "draws",
            "losses", "last_date", "has_value",
        ):
            assert g[key] == w[key], (
                f"{label}/{mid}/{key}: {g[key]!r} != {w[key]!r}"
            )
        if g["z"] is None:
            assert w["z"] is None, f"{label}/{mid}: z не None"
        else:
            assert abs(g["z"] - w["z"]) < 1e-9, f"{label}/{mid}: z расходится"
        if g["arrow"]:
            assert g["title"].startswith("За "), f"{label}/{mid}: нет тултипа"
    return got


def test_matches_naive_random():
    rng = random.Random(42)
    cases = [
        # (моделей в пуле, событий, window, min_games)
        (8, 60, 10, 16),
        (12, 120, 10, 16),
        (20, 300, 10, 16),
        (12, 200, 5, 10),
        (10, 80, 10, 16),
        (30, 500, 10, 16),
        (6, 40, 3, 5),
        (15, 250, 10, 16),
    ]
    for n_models, n_events, window, min_games in cases:
        ids = [f"m{i:03d}" for i in range(n_models)]
        history, elo = _make_history(rng, ids, [], n_events)
        _assert_same(
            f"random {n_models}/{n_events}/w{window}/g{min_games}",
            history, ids, elo, window=window, min_games=min_games,
        )
    print("momentum vs naive (random): OK")


def test_matches_naive_with_draws():
    rng = random.Random(7)
    ids = [f"m{i:02d}" for i in range(12)]
    history, elo = _make_history(rng, ids, [], 200, draw_prob=0.35)
    got = _assert_same("draws", history, ids, elo)
    assert any(tr["draws"] > 0 for tr in got.values()), "ничьи не попали в окна"
    print("momentum vs naive (draws): OK")


def test_matches_naive_with_stale_tail():
    rng = random.Random(11)
    ids = [f"m{i:02d}" for i in range(8)]
    outside = [f"x{i:02d}" for i in range(3)]
    start = date(2026, 1, 1)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(90)]
    history, elo = _make_history(
        rng, ids, outside, 90, dates=dates, outside_only_tail=40,
    )
    got = _assert_same("stale tail", history, ids, elo)
    stale = [
        tr for tr in got.values()
        if tr["games_in_window"] == 10 and not tr["has_value"]
    ]
    assert stale, "хвост без игр пула должен оставить остывшие модели"
    assert all("нет личных игр" in tr["title"] for tr in stale)
    short = [
        tr for tr in got.values()
        if tr["games_in_window"] == 0 and not tr["has_value"]
    ]
    assert all("мало игр для тренда" in tr["title"] for tr in short)
    print(f"momentum stale tail ({len(stale)} stale, {len(short)} short): OK")


def test_edge_empty_history():
    pool = ["a", "b", "c"]
    current = {mid: DEFAULT_ELO for mid in pool}
    got = _assert_same("empty", [], pool, current)
    assert all(tr["has_value"] is False for tr in got.values())
    assert all(tr["arrow"] == "" for tr in got.values())
    assert all("мало игр для тренда" in tr["title"] for tr in got.values())
    print("momentum empty history: OK")


def test_edge_single_model_pool():
    rng = random.Random(3)
    pool = ["m0"]
    outside = ["x0", "x1"]
    history, elo = _make_history(rng, pool, outside, 60)
    got = _assert_same("single pool", history, pool, elo)
    assert got["m0"]["last_date"] == "2026-01-02"
    print("momentum single-model pool: OK")


def test_edge_participants_outside_pool():
    rng = random.Random(5)
    ids = [f"m{i:02d}" for i in range(6)]
    outside = [f"x{i:02d}" for i in range(6)]
    history, elo = _make_history(rng, ids, outside, 150)
    _assert_same("mixed pool", history, ids, elo)
    _assert_same("mixed pool w5", history, ids, elo, window=5, min_games=10)
    print("momentum participants outside pool: OK")


def test_edge_empty_pool():
    rng = random.Random(9)
    history, _ = _make_history(rng, ["a", "b"], [], 10)
    assert compute_rating_momentum(history, [], {}) == {}
    print("momentum empty pool: OK")


def test_min_games_boundary():
    fifteen, elo15 = _fixed_history(["a"] * 15)
    got15 = compute_rating_momentum(fifteen, ["m0"], elo15)
    assert got15["m0"]["has_value"] is False, "15 игр — значения нет"
    assert got15["m0"]["arrow"] == ""
    assert got15["m0"]["games_in_window"] == 0
    assert "нужно 16+" in got15["m0"]["title"]

    sixteen, elo16 = _fixed_history(["a"] * 16)
    got16 = compute_rating_momentum(sixteen, ["m0"], elo16)
    assert got16["m0"]["has_value"] is True, "16 игр — значение есть"
    assert got16["m0"]["games_in_window"] == 10
    assert got16["m0"]["arrow"] == "↑"
    print("momentum 15/16 games boundary: OK")


def test_z_threshold_boundary():
    # 10 игр по +6: z = 1.581 на текущем срезе и 1.500 на предыдущем.
    positive = _state_records([6] * 10)
    assert _momentum_state(positive, 10, 1, 1.5, 14) == "↑", (
        "порог ровно 1.5 должен давать стрелку"
    )
    assert _momentum_state(positive, 10, 1, 1.5 + 1e-6, 14) == "", (
        "порог выше z не должен давать стрелку"
    )

    negative = _state_records([-6] * 10)
    assert _momentum_state(negative, 10, 1, 1.5, 14) == "↓"
    assert _momentum_state(negative, 10, 1, 1.5 + 1e-6, 14) == ""
    print("momentum z threshold boundary: OK")


def test_freshness_boundary():
    results = ["a"] * 16
    history, elo = _fixed_history(results, last_date="2026-01-02")

    fresh = history + [_outside_event(17, "2026-01-16")]  # 14 дней
    got_fresh = compute_rating_momentum(fresh, ["m0"], elo)["m0"]
    assert got_fresh["has_value"] is True, "14 дней — ещё свежая форма"
    assert got_fresh["arrow"] == "↑"

    stale = history + [_outside_event(17, "2026-01-17")]  # 15 дней
    got_stale = compute_rating_momentum(stale, ["m0"], elo)["m0"]
    assert got_stale["has_value"] is False, "15 дней — уже остывшая форма"
    assert got_stale["arrow"] == ""
    assert "нет личных игр в последних 14 днях" == got_stale["title"]
    print("momentum freshness 14/15 days: OK")


def test_counts_and_title():
    results = ["b"] * 6 + ["a"] * 6 + ["draw"] * 2 + ["b"] + ["a"]
    history, elo = _fixed_history(results, last_date="2026-10-24")
    got = compute_rating_momentum(history, ["m0"], elo)["m0"]
    assert (got["wins"], got["draws"], got["losses"]) == (7, 2, 1)
    assert got["arrow"] == "↑"
    assert "7 побед, 2 ничьи, 1 поражение" in got["title"]
    assert "Последняя игра 24.10." in got["title"]
    assert got["title"].startswith("За 10 игр рейтинг +")
    print("momentum counts and title: OK")


def test_last_game_confirmation():
    # Заметный рост, но последняя игра — поражение: стрелки нет.
    up_then_loss, elo_up = _fixed_history(["b"] * 6 + ["a"] * 9 + ["b"])
    got = compute_rating_momentum(up_then_loss, ["m0"], elo_up)["m0"]
    assert got["z"] > 1.5, "движение окна должно оставаться заметным"
    assert got["arrow"] == "", "рост без подтверждения последней игрой"
    assert got["last_date"] == "2026-01-02"

    # Та же серия, но последняя игра — победа: стрелка возвращается.
    up_confirmed, elo_up2 = _fixed_history(["b"] * 6 + ["a"] * 10)
    got2 = compute_rating_momentum(up_confirmed, ["m0"], elo_up2)["m0"]
    assert got2["arrow"] == "↑"

    # Симметрия: заметное падение, последняя игра — победа.
    down_then_win, elo_down = _fixed_history(["a"] * 6 + ["b"] * 9 + ["a"])
    got3 = compute_rating_momentum(down_then_win, ["m0"], elo_down)["m0"]
    assert got3["z"] < -1.5
    assert got3["arrow"] == "", "падение без подтверждения последней игрой"

    down_confirmed, elo_down2 = _fixed_history(["a"] * 6 + ["b"] * 10)
    got4 = compute_rating_momentum(down_confirmed, ["m0"], elo_down2)["m0"]
    assert got4["arrow"] == "↓"

    # Нулевая дельта не подтверждает вход.
    history, _ = _fixed_history(["a"] * 15)
    last_after = history[-1]["elo_a"]["after"]
    zero_event = {
        "seq": 16,
        "date": "2026-01-02",
        "model_a_id": "m0",
        "model_b_id": "x0",
        "winner": "draw",
        "elo_a": {"before": last_after, "after": last_after, "delta": 0},
        "elo_b": {"before": 1200, "after": 1200, "delta": 0},
    }
    got5 = compute_rating_momentum(
        history + [zero_event], ["m0"], {"m0": last_after}, z_threshold=1.0,
    )["m0"]
    assert got5["z"] >= 1.0 and got5["delta"] > 0
    assert got5["arrow"] == "", "дельта 0 не подтверждает вход"
    print("momentum last-game confirmation: OK")


def _state_records(deltas: list[int], start_day: date | None = None) -> list[dict]:
    """Записи для проверки автомата состояний без реплея ELO."""
    start = start_day or date(2026, 1, 1)
    return [
        {
            "delta": d,
            "elo_before": 1200,
            "opp_before": 1200,
            "k": 24,
            "var": (24 ** 2) * 0.25,
            "day": start + timedelta(days=i),
            "date": (start + timedelta(days=i)).isoformat(),
        }
        for i, d in enumerate(deltas)
    ]


def test_hold_and_no_blink():
    """Удержание при |z| >= 1.5 и вход только по двум подряд срезам."""
    # Окно 3: три игры по +20 сразу дают вход (z = 2.89, предыдущий 2.36).
    assert _momentum_state(_state_records([20] * 3), 3, 1, 1.5, 14) == "↑"
    # Малая потеря -2: z = 1.83 — стрелка держится, не мигает.
    assert _momentum_state(
        _state_records([20] * 4 + [-2]), 3, 1, 1.5, 14,
    ) == "↑"
    # Провал -100: z = -3.95 — стрелка гаснет.
    assert _momentum_state(
        _state_records([20] * 4 + [-2, -100]), 3, 1, 1.5, 14,
    ) == ""
    # Возврат: первый и второй плюсы не зажигают, только третий подряд.
    assert _momentum_state(
        _state_records([20] * 4 + [-2, -100, 100]), 3, 1, 1.5, 14,
    ) == ""
    assert _momentum_state(
        _state_records([20] * 4 + [-2, -100, 100, 100]), 3, 1, 1.5, 14,
    ) == ""
    assert _momentum_state(
        _state_records([20] * 4 + [-2, -100, 100, 100, 100]), 3, 1, 1.5, 14,
    ) == "↑"
    # Нулевая дельта не подтверждает вход...
    assert _momentum_state(_state_records([7] * 9 + [0]), 10, 10, 1.5, 14) == ""
    # ...но не гасит уже горящую стрелку.
    assert _momentum_state(
        _state_records([12] * 10 + [0]), 10, 1, 1.5, 14,
    ) == "↑"
    # Пауза больше 14 дней сбрасывает состояние и требует нового входа.
    pause = _state_records([20] * 3) + [{
        "delta": 20,
        "elo_before": 1200,
        "opp_before": 1200,
        "k": 24,
        "var": (24 ** 2) * 0.25,
        "day": date(2026, 1, 1) + timedelta(days=20),
        "date": (date(2026, 1, 1) + timedelta(days=20)).isoformat(),
    }]
    assert _momentum_state(pause, 3, 1, 1.5, 14) == ""
    print("momentum hold and no 1-game blink: OK")


def test_newcomer_does_not_change_others():
    history, elo = _fixed_history(["a"] * 16)
    before = compute_rating_momentum(history, ["m0"], elo)["m0"]

    newcomer = [
        {
            "seq": 17 + i,
            "date": "2026-01-02",
            "model_a_id": "new",
            "model_b_id": "x0",
            "winner": "a",
            "elo_a": {
                "before": DEFAULT_ELO, "after": DEFAULT_ELO + 10, "delta": 10,
            },
            "elo_b": {
                "before": DEFAULT_ELO, "after": DEFAULT_ELO - 10, "delta": -10,
            },
        }
        for i in range(16)
    ]
    after = compute_rating_momentum(history + newcomer, ["m0"], elo)["m0"]
    assert before == after, "матчи новичка не должны менять чужие индикаторы"
    print("momentum newcomer independence: OK")


if __name__ == "__main__":
    test_matches_naive_random()
    test_matches_naive_with_draws()
    test_matches_naive_with_stale_tail()
    test_edge_empty_history()
    test_edge_single_model_pool()
    test_edge_participants_outside_pool()
    test_edge_empty_pool()
    test_min_games_boundary()
    test_z_threshold_boundary()
    test_freshness_boundary()
    test_counts_and_title()
    test_last_game_confirmation()
    test_hold_and_no_blink()
    test_newcomer_does_not_change_others()
    print("\nALL TRENDS TESTS PASSED")
