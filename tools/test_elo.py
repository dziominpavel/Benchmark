#!/usr/bin/env python3
"""Unit tests for elo.py — задачи ELO-движка и журнального хранилища."""
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from elo import expected_score, k_factor, round_elo, update_elo, recalculate
from render_helpers import build_elo_scale, scale_segment


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
    """collect_tasks_info: T-001 из имени директории; счётчик — из событий журнала."""
    from elo import collect_tasks_info
    journal = [
        {"task": "T-001", "matchup": "T-001/001", "seq": 1},
        {"task": "T-001", "matchup": "T-001/002", "seq": 2},
        {"task": "T-001", "matchup": "T-001/003", "seq": 3, "void_of": "T-001/002"},
    ]
    info = collect_tasks_info(journal)
    assert "T-001" in info, f"ожидался T-001, получили {list(info.keys())}"
    assert "T" not in info, f"не должен быть ключ T, получили {list(info.keys())}"
    assert info["T-001"]["matchups_count"] == 3, info["T-001"]
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


def test_settings_roundtrip():
    """settings: запись и чтение возвращают те же значения; дефолты при отсутствии."""
    import tempfile
    from elo import load_settings, save_settings

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "settings.yaml"
        # Отсутствующий файл → дефолты
        s = load_settings(path)
        assert s == {"current_task": "", "tasks": {}}, s

        save_settings({"current_task": "T-001",
                       "tasks": {"T-001": "active", "typo": "inactive"}}, path)
        s2 = load_settings(path)
        assert s2["current_task"] == "T-001", s2
        assert s2["tasks"]["typo"] == "inactive", s2
        assert s2["tasks"]["T-001"] == "active", s2
        # Без BOM
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    print("settings roundtrip: OK")


def test_known_tasks():
    """known_tasks включает T-NNN только из журнала, директорий и settings."""
    from elo import known_tasks
    journal = [{"task": "T-002", "matchup": "T-002/001", "seq": 1}]
    tasks = known_tasks({"current_task": "", "tasks": {"extra-1": "active"}}, journal)
    assert "T-001" in tasks, f"ожидался T-001, получили {tasks}"
    assert "T-002" in tasks, f"ожидался T-002 из событий журнала, получили {tasks}"
    assert "general" not in tasks, f"general больше не таска: {tasks}"
    assert "extra-1" not in tasks, f"extra-1 не T-NNN, не должен быть таской: {tasks}"
    print("known_tasks: OK")


def test_active_and_current_task():
    """Таска без записи активна; неактивный current_task → первая активная."""
    from elo import active_tasks, is_task_active, resolve_current_task, known_tasks
    s = {"current_task": "T-001",
         "tasks": {"T-002": "active", "T-001": "inactive"}}
    assert not is_task_active(s, "T-001")
    assert is_task_active(s, "never-seen")  # без записи → активна
    assert "T-001" in known_tasks(s)  # неактивная остаётся известной
    assert "T-001" not in active_tasks(s)
    assert resolve_current_task(s) == "T-002"  # неактивный → fallback
    s2 = {"current_task": "", "tasks": {}}
    assert resolve_current_task(s2) == "T-001"  # первая активная известная
    print("active/current task: OK")


def test_get_coverage():
    """Видимые ячейки (оба флага true): BLOCKED невидимы, повторы не считаются."""
    from elo import get_coverage
    models = [{"id": "A", "status": "active"}, {"id": "B", "status": "active"},
              {"id": "C", "status": "active"}, {"id": "D", "status": "archived"}]
    settings = {"current_task": "T-001",
                "tasks": {"T-001": "active", "T-002": "active",
                          "typo": "inactive"}}
    flags_all = {"T-001": {"A": True, "B": True, "C": True},
                 "T-002": {"A": True, "B": True, "C": True}}
    mus = [
        # A-B: 3 игры в T-001 → 1 ячейка; 1 игра в T-002 → ещё 1
        {"task": "T-001", "model_a_id": "A", "model_b_id": "B", "winner": "a", "_matchup_id": "T-001/001"},
        {"task": "T-001", "model_a_id": "B", "model_b_id": "A", "winner": "b", "_matchup_id": "T-001/002"},
        {"task": "T-001", "model_a_id": "A", "model_b_id": "B", "winner": "draw", "_matchup_id": "T-001/003"},
        {"task": "T-002", "model_a_id": "A", "model_b_id": "B", "winner": "a", "_matchup_id": "T-002/001"},
        # A-C в T-002
        {"task": "T-002", "model_a_id": "A", "model_b_id": "C", "winner": "a", "_matchup_id": "T-002/002"},
        # Не-T-NNN таска не считается
        {"task": "typo", "model_a_id": "B", "model_b_id": "C", "winner": "a", "_matchup_id": "typo/001"},
        # С архивной моделью D — не считается
        {"task": "T-001", "model_a_id": "A", "model_b_id": "D", "winner": "a", "_matchup_id": "T-001/004"},
        # Аннулированный вердикт — не считается
        {"task": "T-001", "model_a_id": "B", "model_b_id": "C", "winner": "a", "_matchup_id": "T-001/005"},
        {"task": "T-001", "void_of": "T-001/005", "_matchup_id": "T-001/006"},
    ]
    cov = get_coverage(settings, mus, models, flags_all)
    # Активных моделей 3 → C(3,2)=3 пары; активных тасков 2 → total=6
    # Ячейки: (T-001,A-B), (T-002,A-B), (T-002,A-C) = 3
    assert cov["total"] == 6, cov
    assert cov["filled"] == 3, cov
    assert abs(cov["percent"] - 50.0) < 0.01, cov

    # Нет активных тасков → percent=None
    cov_none = get_coverage({"current_task": "",
                             "tasks": {"T-001": "inactive",
                                       "T-002": "inactive",
                                       "typo": "inactive"}}, mus, models, flags_all)
    assert cov_none["percent"] is None, cov_none

    # <2 активных моделей → percent=None
    cov_one = get_coverage(settings, mus, [{"id": "A", "status": "active"}], flags_all)
    assert cov_one["percent"] is None, cov_one
    print("get_coverage: OK")


def test_get_coverage_answer_aware():
    """Динамика знаменателя от флагов: BLOCKED исключены с обеих сторон."""
    from elo import get_coverage
    models = [{"id": "A", "status": "active"}, {"id": "B", "status": "active"},
              {"id": "C", "status": "active"}]
    settings = {"current_task": "T-001",
                "tasks": {"T-001": "active", "T-002": "active"}}
    # A,B закрыли всё между собой; C без ответов на T-002
    mus = [
        {"task": "T-001", "model_a_id": "A", "model_b_id": "B", "winner": "a", "_matchup_id": "T-001/001"},
        {"task": "T-001", "model_a_id": "A", "model_b_id": "C", "winner": "a", "_matchup_id": "T-001/002"},
        {"task": "T-001", "model_a_id": "B", "model_b_id": "C", "winner": "a", "_matchup_id": "T-001/003"},
        {"task": "T-002", "model_a_id": "A", "model_b_id": "B", "winner": "a", "_matchup_id": "T-002/001"},
    ]
    flags = {"T-001": {"A": True, "B": True, "C": True},
             "T-002": {"A": True, "B": True}}  # C x T-002 = BLOCKED
    cov = get_coverage(settings, mus, models, flags)
    # Видимые: T-001 × 3 пары + T-002 × {A,B} = 4; DONE: 3 + 1 = 4 → 100%
    assert (cov["filled"], cov["total"]) == (4, 4), cov
    assert cov["percent"] == 100.0, cov

    # Новая модель D без ответов: знаменатель не меняется
    models_d = models + [{"id": "D", "status": "active"}]
    cov_d = get_coverage(settings, mus, models_d, flags)
    assert (cov_d["filled"], cov_d["total"]) == (4, 4), cov_d
    assert cov_d["percent"] == 100.0, cov_d

    # D получил ответ на T-001: +3 READY → 4 из 7
    flags_d = {"T-001": {"A": True, "B": True, "C": True, "D": True},
               "T-002": {"A": True, "B": True}}
    cov_d2 = get_coverage(settings, mus, models_d, flags_d)
    assert (cov_d2["filled"], cov_d2["total"]) == (4, 7), cov_d2
    assert abs(cov_d2["percent"] - 100 * 4 / 7) < 0.01, cov_d2
    assert cov_d2["percent"] < 100.0, cov_d2  # есть READY → строго < 100%

    # Снятие флага прячет и DONE-ячейку целиком (вердикт остаётся, но не считается)
    flags_un = {"T-001": {"A": True, "C": True, "D": True},
                "T-002": {"A": True, "B": True}}
    cov_un = get_coverage(settings, mus, models_d, flags_un)
    # Видимые T-001: AC, AD, CD (без B); T-002: AB. DONE: (T-001,AC), (T-002,AB)
    assert (cov_un["filled"], cov_un["total"]) == (2, 4), cov_un
    assert cov_un["percent"] == 50.0, cov_un

    # Все BLOCKED (пустые флаги) → percent=None
    cov_blocked = get_coverage(settings, mus, models, {})
    assert cov_blocked["total"] == 0, cov_blocked
    assert cov_blocked["percent"] is None, cov_blocked

    # Рематчи сверх первой игры не двигают счёт
    mus_rematch = mus + [
        {"task": "T-001", "model_a_id": "A", "model_b_id": "B", "winner": "b", "_matchup_id": "T-001/010"},
        {"task": "T-001", "model_a_id": "A", "model_b_id": "B", "winner": "draw", "_matchup_id": "T-001/011"},
    ]
    cov_re = get_coverage(settings, mus_rematch, models, flags)
    assert (cov_re["filled"], cov_re["total"]) == (4, 4), cov_re
    assert cov_re["percent"] == 100.0, cov_re
    print("get_coverage answer-aware: OK")


def test_format_model_roundtrip():
    """parse_existing↔format_model сохраняют agent/provider и не добавляют мусор."""
    from register_model import format_model, parse_existing
    text = (
        "# шапка\n\nmodels:\n"
        "  - id: a\n"
        "    name: \"A\"\n"
        "    agent: Cursor\n"
        "    provider: Anthropic\n"
        "    version: v1\n"
        "    added: 2026-01-02\n"
        "    status: active\n"
        "  - id: b\n"
        "    name: \"B\"\n"
        "    agent: \n"
        "    provider: \n"
        "    version: \n"
        "    added: 2026-01-03\n"
        "    status: archived\n"
    )
    models, _ = parse_existing(text)
    assert [m["id"] for m in models] == ["a", "b"], models
    assert models[0]["agent"] == "Cursor" and models[0]["provider"] == "Anthropic"

    out = format_model(models[0])
    back, _ = parse_existing("models:\n" + out + "\n")
    assert back[0] == models[0], f"round-trip потерял поля: {models[0]} != {back[0]}"

    # Пустые agent/provider остаются пустыми строками, released/notes не появляются
    back_b, _ = parse_existing("models:\n" + format_model(models[1]) + "\n")
    assert back_b[0]["agent"] == "" and back_b[0]["provider"] == ""
    assert "released" not in back_b[0] and "notes" not in back_b[0]

    # Запись без agent/provider (старый формат) переживает круг без выдуманных значений
    legacy = {"id": "c", "name": "C", "version": "1", "added": "2026-01-04", "status": "active"}
    back_c, _ = parse_existing("models:\n" + format_model(legacy) + "\n")
    assert back_c[0].get("agent", "") == "" and back_c[0].get("provider", "") == ""
    print("format_model round-trip: OK")


def test_index_stale_agent_provider():
    """is_index_stale замечает правку agent/provider и старый кэш без agent."""
    import json
    import tempfile
    import elo as elo_mod

    models_yaml = (
        "models:\n"
        "  - id: m\n"
        "    name: \"M\"\n"
        "    agent: Cursor\n"
        "    provider: Anthropic\n"
        "    version: 1\n"
        "    added: 2026-01-01\n"
        "    status: active\n"
    )
    cache = {
        "version": 2,
        "updated": "2026-01-01",
        "matchups_digest": elo_mod.matchups_digest(),
        "models": {
            "m": {"name": "M", "agent": "Cursor", "provider": "Anthropic",
                  "added": "2026-01-01", "status": "active",
                  "elo": 1200, "games": 0, "wins": 0, "losses": 0, "draws": 0},
        },
    }
    old_models, old_index = elo_mod.MODELS_PATH, elo_mod.INDEX_PATH
    try:
        with tempfile.TemporaryDirectory() as tmp:
            mp = Path(tmp) / "models.yaml"
            ip = Path(tmp) / "index.json"
            elo_mod.MODELS_PATH, elo_mod.INDEX_PATH = mp, ip

            mp.write_text(models_yaml, encoding="utf-8")
            ip.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            assert elo_mod.is_index_stale() is False

            mp.write_text(models_yaml.replace("agent: Cursor", "agent: Devin"), encoding="utf-8")
            assert elo_mod.is_index_stale() is True

            mp.write_text(models_yaml.replace("provider: Anthropic", "provider: OpenAI"), encoding="utf-8")
            assert elo_mod.is_index_stale() is True

            # Реестр с agent, а кэш — старого формата (без agent) → устарел
            mp.write_text(models_yaml, encoding="utf-8")
            old_cache = dict(cache)
            old_cache["models"] = {
                "m": {k: v for k, v in cache["models"]["m"].items() if k != "agent"},
            }
            ip.write_text(json.dumps(old_cache, ensure_ascii=False), encoding="utf-8")
            assert elo_mod.is_index_stale() is True
    finally:
        elo_mod.MODELS_PATH, elo_mod.INDEX_PATH = old_models, old_index
    print("is_index_stale agent/provider: OK")


def test_elo_dist_scale():
    # Полный пул 895..1520: обе половины, пивот 1200
    anchors = build_elo_scale([895, 1520])
    assert anchors == [
        (895.0, 0), (1047.5, 1), (1200.0, 2), (1360.0, 3), (1520.0, 4),
    ], anchors
    # Контрольные значения: 895 -> s0/0%, 1218 -> сегмент s2-s3,
    # 1360 -> сегмент s3-s4, 1520 -> s4/1.0
    assert scale_segment(895, anchors) == (0, 0.0)
    seg, frac = scale_segment(1218, anchors)
    assert seg == 2 and abs(frac - 0.1125) < 1e-9, (seg, frac)
    assert scale_segment(1360, anchors) == (3, 0.0)
    assert scale_segment(1520, anchors) == (3, 1.0)
    # 1200 — всегда опора s2 (левая граница сегмента s2-s3)
    assert scale_segment(1200, anchors) == (2, 0.0)
    # Непрерывность на стыке: доля слева ~1 при том же цвете опоры s3
    seg_l, frac_l = scale_segment(1359.999, anchors)
    assert seg_l == 2 and frac_l > 0.9999, (seg_l, frac_l)
    # За краями пула доля зажата в 0/1
    assert scale_segment(700, anchors) == (0, 0.0)
    assert scale_segment(2000, anchors) == (3, 1.0)
    # Пул целиком выше 1200 — только холодная половина (без красного)
    anchors_hi = build_elo_scale([1250, 1400])
    assert [a[1] for a in anchors_hi] == [2, 3, 4], anchors_hi
    # Пул целиком ниже 1200 — только тёплая половина (без зелёного)
    anchors_lo = build_elo_scale([895, 1100])
    assert [a[1] for a in anchors_lo] == [0, 1, 2], anchors_lo
    # Вырожденный пул: одно значение расширяется на +-10 и не падает
    anchors_one = build_elo_scale([1234])
    assert anchors_one[0][0] < 1234 < anchors_one[-1][0], anchors_one
    seg, frac = scale_segment(1234, anchors_one)
    assert 0.0 <= frac <= 1.0, (seg, frac)
    print("elo dist scale: OK")


def _write_models(path: Path, ids) -> None:
    """Минимальный models.yaml для tmp-хранилища."""
    lines = ["models:"]
    for mid in ids:
        lines += [f"  - id: {mid}", f'    name: "{mid}"', "    status: active"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@contextlib.contextmanager
def _temp_storage(tmp: Path, model_ids=("A", "B")):
    """Подмена путей elo.py на tmp-хранилище; пути возвращаются на выходе."""
    import elo as elo_mod

    saved = (elo_mod.JOURNAL_PATH, elo_mod.MODELS_PATH,
             elo_mod.SETTINGS_PATH, elo_mod.INDEX_PATH)
    elo_mod.JOURNAL_PATH = tmp / "journal.jsonl"
    elo_mod.MODELS_PATH = tmp / "models.yaml"
    elo_mod.SETTINGS_PATH = tmp / "settings.yaml"
    elo_mod.INDEX_PATH = tmp / "index.json"
    _write_models(elo_mod.MODELS_PATH, list(model_ids))
    elo_mod.SETTINGS_PATH.write_text(
        "current_task: T-001\ntasks:\n  T-001: active\n", encoding="utf-8"
    )
    try:
        yield elo_mod
    finally:
        (elo_mod.JOURNAL_PATH, elo_mod.MODELS_PATH,
         elo_mod.SETTINGS_PATH, elo_mod.INDEX_PATH) = saved


def test_journal_roundtrip():
    """read_journal: порядок по seq, _matchup_id из matchup, следующий id/seq."""
    import json
    import tempfile
    import elo as elo_mod

    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / "journal.jsonl"
        saved = elo_mod.JOURNAL_PATH
        elo_mod.JOURNAL_PATH = journal
        try:
            assert elo_mod.load_matchups() == []
            events = [
                {"seq": 2, "task": "T-001", "matchup": "T-001/002",
                 "recorded_at": "2026-09-05T10:00:02+03:00"},
                {"seq": 1, "task": "T-001", "matchup": "T-001/001",
                 "recorded_at": "2026-09-05T10:00:01+03:00"},
            ]
            journal.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
                encoding="utf-8",
            )
            loaded = elo_mod.load_matchups()
            assert [e["seq"] for e in loaded] == [1, 2], loaded
            assert loaded[0]["_matchup_id"] == "T-001/001"
            assert loaded[0]["_file"] == "data/matchups/journal.jsonl"
            assert elo_mod.next_matchup_id("T-001", loaded) == "T-001/003"
        finally:
            elo_mod.JOURNAL_PATH = saved
    print("journal roundtrip: OK")


def test_journal_torn_last_line():
    """Оборванная последняя строка пропускается; предыдущие события применяются."""
    import json
    import tempfile
    import elo as elo_mod

    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / "journal.jsonl"
        saved = elo_mod.JOURNAL_PATH
        elo_mod.JOURNAL_PATH = journal
        try:
            valid = json.dumps(
                {"seq": 1, "task": "T-001", "matchup": "T-001/001",
                 "recorded_at": "2026-09-05T10:00:01+03:00"},
                ensure_ascii=False,
            )
            journal.write_text(valid + "\n" + '{"seq": 2, "task": "T-001", "matchu',
                               encoding="utf-8")
            events, problems = elo_mod.read_journal()
            assert [e["seq"] for e in events] == [1], events
            assert len(problems) == 1, problems
            assert "оборванная последняя строка" in problems[0], problems
        finally:
            elo_mod.JOURNAL_PATH = saved
    print("journal torn last line: OK")


def test_journal_check_problems():
    """Проверки журнала: дубликат seq, отсутствие matchup, висячий void_of."""
    import json
    import tempfile
    import elo as elo_mod

    lines = [
        {"seq": 1, "task": "T-001", "matchup": "T-001/001",
         "model_a_id": "A", "model_b_id": "B", "winner": "a",
         "recorded_at": "2026-09-05T10:00:01+03:00"},
        {"seq": 1, "task": "T-001", "matchup": "T-001/002",
         "void_of": "T-001/999", "recorded_at": "2026-09-05T10:00:02+03:00"},
        {"seq": 3, "task": "T-001", "recorded_at": "2026-09-05T10:00:03+03:00"},
    ]
    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / "journal.jsonl"
        saved = elo_mod.JOURNAL_PATH
        elo_mod.JOURNAL_PATH = journal
        try:
            journal.write_text(
                "\n".join(json.dumps(e, ensure_ascii=False) for e in lines) + "\n",
                encoding="utf-8",
            )
            events, problems = elo_mod.read_journal()
            assert not problems, problems
            vp = elo_mod.verify_snapshots(events, ["A", "B"])
            assert any("дубликат seq" in p for p in vp), vp
            assert any("отсутствует поле matchup" in p for p in vp), vp
            warnings = elo_mod.recalculate(events, ["A", "B"])["warnings"]
            assert any("несуществующее событие" in w for w in warnings), warnings
        finally:
            elo_mod.JOURNAL_PATH = saved
    print("journal check problems: OK")


def test_run_check_reports_journal_problems():
    """run_check: exit 1 и проблема в выводе для каждого вида порчи журнала."""
    import io
    import json
    import tempfile

    good = {
        "seq": 1, "task": "T-001", "matchup": "T-001/001",
        "model_a_id": "A", "model_b_id": "B", "winner": "a",
        "recorded_at": "2026-09-05T10:00:01+03:00",
    }
    good3 = dict(good, seq=3, matchup="T-001/003",
                 recorded_at="2026-09-05T10:00:03+03:00")

    def run(lines):
        with tempfile.TemporaryDirectory() as td:
            with _temp_storage(Path(td)) as elo_mod:
                elo_mod.JOURNAL_PATH.write_text(
                    "\n".join(
                        ln if isinstance(ln, str) else json.dumps(ln, ensure_ascii=False)
                        for ln in lines
                    ) + "\n",
                    encoding="utf-8",
                )
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    code = elo_mod.run_check()
                return code, buf.getvalue()

    # Невалидная строка (не последняя)
    code, out = run([good, '{"seq": 2, извините', good3])
    assert code == 1 and "невалидный JSON" in out and "строка 2" in out, out
    # Дубликат seq
    code, out = run([good, dict(good, matchup="T-001/00X")])
    assert code == 1 and "дубликат seq" in out, out
    # Висячая void_of-ссылка
    tomb = {"seq": 2, "task": "T-001", "matchup": "T-001/002",
            "void_of": "T-001/999", "recorded_at": "2026-09-05T10:00:02+03:00"}
    code, out = run([good, tomb])
    assert code == 1 and "несуществующее событие" in out, out
    # Монотонность recorded_at
    late = dict(good, seq=2, matchup="T-001/002",
                recorded_at="2026-09-05T09:00:00+03:00")
    code, out = run([good, late])
    assert code == 1 and "раньше предыдущего" in out, out
    print("run_check journal problems: OK")


def test_record_verdict_journal():
    """record_verdict/void_matchup пишут события в journal.jsonl (append)."""
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        with _temp_storage(tmp) as elo_mod:
            from elo import record_verdict, void_matchup, load_matchups

            r1 = record_verdict("T-001", "A", "B", "a", regenerate_index=False)
            v1 = r1["verdict"]
            assert v1["seq"] == 1 and v1["matchup"] == "T-001/001", v1
            assert v1["elo"]["A"] == {"before": 1200, "after": 1220, "delta": 20}, v1["elo"]
            assert v1["elo"]["B"] == {"before": 1200, "after": 1180, "delta": -20}
            assert v1["recorded_at"], v1

            r2 = record_verdict("T-001", "A", "B", "b", regenerate_index=False)
            assert r2["verdict"]["seq"] == 2 and r2["verdict"]["matchup"] == "T-001/002"

            events = load_matchups()
            assert len(events) == 2, events
            assert not (tmp / "state.json").exists()
            raw = (tmp / "journal.jsonl").read_text(encoding="utf-8")
            assert len([ln for ln in raw.splitlines() if ln.strip()]) == 2

            void = void_matchup("T-001/001", reason="ошибка записи")
            assert void["matchup_id"] == "T-001/003", void
            tombstones = [e for e in load_matchups() if e.get("void_of")]
            assert len(tombstones) == 1 and tombstones[0]["void_of"] == "T-001/001"
            assert tombstones[0]["seq"] == 3

            try:
                void_matchup("T-001/999")
                raise AssertionError("должен быть ValueError для несуществующей цели")
            except ValueError:
                pass
    print("record_verdict journal: OK")


def test_record_verdict_date():
    """record_verdict: verdict_date попадает в событие; невалидная дата — ValueError."""
    import json
    import tempfile
    from datetime import date as date_cls

    with tempfile.TemporaryDirectory() as td:
        with _temp_storage(Path(td)) as elo_mod:
            r1 = elo_mod.record_verdict(
                "T-001", "A", "B", "a", verdict_date="2026-09-04",
                regenerate_index=False,
            )
            assert r1["verdict"]["date"] == "2026-09-04", r1["verdict"]
            first = json.loads(
                elo_mod.JOURNAL_PATH.read_text(encoding="utf-8").splitlines()[0]
            )
            assert first["date"] == "2026-09-04", first

            # Пустое значение эквивалентно «сегодня»
            r2 = elo_mod.record_verdict(
                "T-001", "A", "B", "b", verdict_date="", regenerate_index=False,
            )
            assert r2["verdict"]["date"] == date_cls.today().isoformat()

            # Невалидные значения отклоняются до записи
            before = len(elo_mod.load_matchups())
            for bad in ("2026/09/04", "04.09.2026", "2026-9-4", "2026-02-30", "вчера"):
                try:
                    elo_mod.record_verdict(
                        "T-001", "A", "B", "a", verdict_date=bad,
                        regenerate_index=False,
                    )
                    raise AssertionError(f"ожидался ValueError для {bad!r}")
                except ValueError:
                    pass
            assert len(elo_mod.load_matchups()) == before
    print("record_verdict date: OK")


def test_void_rejections():
    """Повторное аннулирование и аннулирование tombstone отклоняются без записи."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        with _temp_storage(Path(td)) as elo_mod:
            elo_mod.record_verdict("T-001", "A", "B", "a", regenerate_index=False)
            elo_mod.void_matchup("T-001/001", reason="ошибка записи")
            assert len(elo_mod.load_matchups()) == 2

            # Повторное аннулирование уже аннулированного вердикта
            try:
                elo_mod.void_matchup("T-001/001", reason="ещё раз")
                raise AssertionError("ожидался ValueError для повторного аннулирования")
            except ValueError:
                pass

            # Аннулирование самого tombstone-события
            try:
                elo_mod.void_matchup("T-001/002", reason="удалить аудит")
                raise AssertionError("ожидался ValueError для аннулирования tombstone")
            except ValueError:
                pass

            assert len(elo_mod.load_matchups()) == 2
    print("void rejections: OK")


def test_voided_history():
    """voided_history: поля, порядок по seq цели, первый tombstone, пустота."""
    from elo import matchup_sort_key

    def verdict(seq, mid, a, b, winner, with_elo=True):
        ev = {
            "seq": seq, "task": "T-001", "matchup": mid,
            "model_a_id": a, "model_b_id": b, "winner": winner,
            "date": "2026-09-05", "recorded_at": f"2026-09-05T10:00:0{seq}+03:00",
            "_matchup_id": mid,
        }
        if with_elo:
            ev["elo"] = {a: {"before": 1200, "after": 1220, "delta": 20},
                         b: {"before": 1200, "after": 1180, "delta": -20}}
        return ev

    def tomb(seq, mid, void_of, reason):
        return {
            "seq": seq, "task": "T-001", "matchup": mid, "void_of": void_of,
            "reason": reason, "date": "2026-10-18",
            "recorded_at": f"2026-10-18T10:00:0{seq}+03:00", "_matchup_id": mid,
        }

    matchups = [
        verdict(1, "T-001/001", "A", "B", "a"),
        verdict(2, "T-001/002", "A", "C", "b"),
        verdict(3, "T-001/003", "B", "C", "draw"),
        verdict(4, "T-001/004", "A", "B", "a", with_elo=False),
        tomb(5, "T-001/005", "T-001/001", "ошибка записи"),
        tomb(6, "T-001/006", "T-001/001", "повторный tombstone"),
        tomb(7, "T-001/007", "T-001/002", "дубль матча"),
        tomb(8, "T-001/008", "T-001/004", ""),
    ]
    matchups.sort(key=matchup_sort_key)
    result = recalculate(matchups, ["A", "B", "C"])

    # elo_history и счётчики не затронуты аннулированными
    assert [h["matchup"] for h in result["elo_history"]] == ["T-001/003"], \
        result["elo_history"]
    assert result["voided"] == ["T-001/001", "T-001/002", "T-001/004"]
    assert len(result["tombstones"]) == 4

    vh = result["voided_history"]
    assert [e["matchup"] for e in vh] == ["T-001/001", "T-001/002", "T-001/004"], vh
    first = vh[0]
    assert first["seq"] == 1 and first["task"] == "T-001"
    assert first["model_a_id"] == "A" and first["model_b_id"] == "B"
    assert first["winner"] == "a" and first["date"] == "2026-09-05"
    assert first["elo_a"] == {"before": 1200, "after": 1220, "delta": 20}
    # при дублях tombstone аудит — первый по seq
    assert first["void"]["reason"] == "ошибка записи"
    assert first["void"]["matchup"] == "T-001/005"
    assert first["void"]["recorded_at"] == "2026-10-18T10:00:05+03:00"
    # legacy-вердикт без снэпшота — нулевой fallback
    legacy = vh[2]
    assert legacy["matchup"] == "T-001/004"
    assert legacy["elo_a"] == {"before": 1200, "after": 1200, "delta": 0}
    assert legacy["elo_b"] == {"before": 1200, "after": 1200, "delta": 0}

    # Пустая секция без аннулированных
    plain = recalculate([verdict(1, "T-001/001", "A", "B", "a")], ["A", "B"])
    assert plain["voided_history"] == []
    print("voided_history: OK")


def test_generate_index_voided_history():
    """generate_index кладёт voided_history в index.json на диск."""
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        with _temp_storage(Path(td)) as elo_mod:
            elo_mod.record_verdict("T-001", "A", "B", "a", regenerate_index=False)
            elo_mod.void_matchup("T-001/001", reason="дубль записи")
            idx = elo_mod.generate_index()
            elo_mod.save_index(idx)

            assert idx["voided_history"][0]["matchup"] == "T-001/001"
            assert idx["voided_history"][0]["void"]["reason"] == "дубль записи"
            assert idx["matchups_summary"]["voided"] == 1
            assert all(h["matchup"] != "T-001/001" for h in idx["elo_history"])

            saved = json.loads(elo_mod.INDEX_PATH.read_text(encoding="utf-8"))
            assert saved["voided_history"][0]["void"]["reason"] == "дубль записи"
    print("generate_index voided_history: OK")


_CHILD_WRITER = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "sys.path.insert(0, sys.argv[2])\n"
    "import elo\n"
    "elo.JOURNAL_PATH = Path(sys.argv[1])\n"
    "with elo.journal_lock() as f:\n"
    "    seq = elo._next_seq(elo.load_matchups())\n"
    "    time.sleep(0.2)\n"
    "    elo.append_event(f, {'seq': seq, 'task': 'T-001',\n"
    "                         'matchup': 'T-001/%03d' % seq,\n"
    "                         'recorded_at': '2026-09-05T10:00:00+03:00'})\n"
)


def test_journal_parallel_writes():
    """Два процесса пишут одновременно: обе строки целы, seq различны."""
    import json
    import subprocess
    import tempfile

    tools_dir = str(Path(__file__).resolve().parent)
    with tempfile.TemporaryDirectory() as td:
        journal = Path(td) / "journal.jsonl"
        procs = [
            subprocess.Popen([sys.executable, "-c", _CHILD_WRITER, str(journal), tools_dir])
            for _ in range(2)
        ]
        codes = [p.wait(timeout=60) for p in procs]
        assert codes == [0, 0], codes

        lines = [ln for ln in journal.read_text(encoding="utf-8").splitlines() if ln.strip()]
        parsed = [json.loads(ln) for ln in lines]
        assert len(parsed) == 2, parsed
        assert sorted(e["seq"] for e in parsed) == [1, 2], parsed
        assert sorted(e["matchup"] for e in parsed) == ["T-001/001", "T-001/002"]
    print("journal parallel writes: OK")


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
    test_settings_roundtrip()
    test_known_tasks()
    test_active_and_current_task()
    test_get_coverage()
    test_get_coverage_answer_aware()
    test_format_model_roundtrip()
    test_index_stale_agent_provider()
    test_elo_dist_scale()
    test_journal_roundtrip()
    test_journal_torn_last_line()
    test_journal_check_problems()
    test_run_check_reports_journal_problems()
    test_record_verdict_journal()
    test_record_verdict_date()
    test_void_rejections()
    test_voided_history()
    test_generate_index_voided_history()
    test_journal_parallel_writes()
    print("\nALL ELO TESTS PASSED")
