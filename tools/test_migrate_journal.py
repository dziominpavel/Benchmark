#!/usr/bin/env python3
"""test_migrate_journal.py — миграция legacy-файлов в журнал (tmp-фикстуры).

Проверяет (задача 3.1):
  * успешную миграцию синтетического хранилища: журнал из тех же
    событий, legacy-файлы/каталоги/`state.json` удалены, `--check` и
    сравнение реплея до/после проходят;
  * сценарий расхождения реплея: журнал удаляется, legacy-файлы целы,
    exit 1;
  * abort-условия: существующий журнал, файл без `seq`, дубликат `seq`;
  * `--dry-run` ничего не пишет и не удаляет.

Запуск: python tools/test_migrate_journal.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import elo  # noqa: E402
import migrate_journal  # noqa: E402

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
"""

SETTINGS_YAML = """\
current_task: T-001
tasks:
  T-001: active
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    _write(path, json.dumps(data, ensure_ascii=False, indent=2))


@contextmanager
def _temp_storage():
    """tmp-хранилище с подменой путей elo на время теста."""
    with tempfile.TemporaryDirectory(prefix="bench_migr_") as tmp_str:
        tmp = Path(tmp_str)
        paths = {
            "tmp": tmp,
            "matchups": tmp / "matchups",
            "journal": tmp / "matchups" / "journal.jsonl",
            "models": tmp / "models.yaml",
            "settings": tmp / "settings.yaml",
            "flags": tmp / "answer_flags.yaml",
            "index": tmp / "index.json",
            "tasks": tmp / "tasks",
        }
        _write(paths["models"], MODELS_YAML)
        _write(paths["settings"], SETTINGS_YAML)
        paths["tasks"].mkdir(parents=True, exist_ok=True)

        saved = {
            "JOURNAL_PATH": elo.JOURNAL_PATH,
            "MATCHUPS_DIR": elo.MATCHUPS_DIR,
            "MODELS_PATH": elo.MODELS_PATH,
            "SETTINGS_PATH": elo.SETTINGS_PATH,
            "ANSWER_FLAGS_PATH": elo.ANSWER_FLAGS_PATH,
            "INDEX_PATH": elo.INDEX_PATH,
            "TASKS_DIR": elo.TASKS_DIR,
        }
        elo.JOURNAL_PATH = paths["journal"]
        elo.MATCHUPS_DIR = paths["matchups"]
        elo.MODELS_PATH = paths["models"]
        elo.SETTINGS_PATH = paths["settings"]
        elo.ANSWER_FLAGS_PATH = paths["flags"]
        elo.INDEX_PATH = paths["index"]
        elo.TASKS_DIR = paths["tasks"]
        try:
            yield paths
        finally:
            elo.JOURNAL_PATH = saved["JOURNAL_PATH"]
            elo.MATCHUPS_DIR = saved["MATCHUPS_DIR"]
            elo.MODELS_PATH = saved["MODELS_PATH"]
            elo.SETTINGS_PATH = saved["SETTINGS_PATH"]
            elo.ANSWER_FLAGS_PATH = saved["ANSWER_FLAGS_PATH"]
            elo.INDEX_PATH = saved["INDEX_PATH"]
            elo.TASKS_DIR = saved["TASKS_DIR"]


def _ev(seq: int, winner: str = "a", **extra) -> dict:
    ev = {
        "version": 2,
        "seq": seq,
        "task": "T-001",
        "model_a": "alpha",
        "model_b": "beta",
        "winner": winner,
        "date": "2026-01-02",
        "recorded_at": f"2026-01-02T10:00:{seq:02d}+00:00",
    }
    ev.update(extra)
    return ev


def _snapshot_after_win() -> dict:
    """Снэпшот ELO для вердикта alpha–beta (оба 1200, победа alpha)."""
    e_a = elo.expected_score(1200, 1200)
    k = elo.k_factor(0)
    new_a, new_b = elo.update_elo(1200, k, 1.0, e_a, 1200, k, 0.0, 1.0 - e_a)
    return {
        "alpha": {"before": 1200, "after": new_a, "delta": new_a - 1200},
        "beta": {"before": 1200, "after": new_b, "delta": new_b - 1200},
    }


def _seed_legacy(paths) -> None:
    """Синтетическое legacy-хранилище: вердикт, вердикт со снэпшотом,
    tombstone и state.json."""
    _write_json(paths["matchups"] / "T-001" / "001.json",
                _ev(1, winner="b"))
    _write_json(paths["matchups"] / "T-001" / "002.json",
                _ev(2, winner="a", model_a_id="alpha", model_b_id="beta",
                    elo=_snapshot_after_win()))
    _write_json(paths["matchups"] / "T-001" / "003.json",
                _ev(3, void_of="T-001/001", reason="тест"))
    _write_json(paths["matchups"] / "state.json", {"next_seq": 4})


def test_successful_migration():
    with _temp_storage() as paths:
        _seed_legacy(paths)
        rc = migrate_journal.migrate(dry_run=False)
        assert rc == 0, f"миграция вернула {rc}"

        lines = paths["journal"].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3, f"строк в журнале: {len(lines)}"
        events = [json.loads(line) for line in lines]
        assert [e["seq"] for e in events] == [1, 2, 3]
        assert [e["matchup"] for e in events] == [
            "T-001/001", "T-001/002", "T-001/003",
        ]
        assert events[0]["model_a"] == "alpha", events[0]
        assert events[0].get("model_a_id") is None, (
            "поля legacy-файла без id не должны появляться"
        )
        assert events[1]["model_a_id"] == "alpha", events[1]
        assert events[1]["elo"]["alpha"]["before"] == 1200, events[1]
        assert events[2]["void_of"] == "T-001/001", events[2]

        # Legacy-раскладка удалена только после верификации
        assert not paths["journal"].parent.joinpath("T-001").exists()
        assert not paths["journal"].parent.joinpath("state.json").exists()
        assert list(paths["matchups"].glob("T-NNN")) == []

        # Продуктовый reader и полный --check
        recovered, problems = elo.read_journal()
        assert not problems, f"журнал читается с проблемами: {problems}"
        assert elo.run_check() == 0, "elo --check после миграции не прошёл"
        assert paths["index"].exists(), "index.json не пересобран"
    print("3.1 успешная миграция: OK")


def test_replay_mismatch_aborts():
    with _temp_storage() as paths:
        _seed_legacy(paths)
        real = elo.recalculate
        calls: list[int] = []

        def flaky(matchups, model_ids):
            result = real(matchups, model_ids)
            calls.append(1)
            if len(calls) == 1:
                # Ломаем «до»-реплей, чтобы поймать расхождение
                result = dict(result)
                result["models"] = dict(result["models"])
                result["models"]["alpha"] = dict(
                    result["models"]["alpha"], elo=9999,
                )
            return result

        elo.recalculate = flaky
        try:
            rc = migrate_journal.migrate(dry_run=False)
        finally:
            elo.recalculate = real
        assert rc == 1, f"расхождение не поймано (rc={rc})"
        assert not paths["journal"].exists(), "журнал не удалён при расхождении"
        assert paths["matchups"].joinpath("T-001", "001.json").exists()
        assert paths["matchups"].joinpath("state.json").exists()
    print("3.1 расхождение реплея: OK")


def test_abort_existing_journal():
    with _temp_storage() as paths:
        _seed_legacy(paths)
        _write(paths["journal"], "")
        rc = migrate_journal.migrate(dry_run=False)
        assert rc == 1, "повторная миграция не отклонена"
        assert paths["matchups"].joinpath("T-001", "001.json").exists()
    print("3.1 abort при существующем журнале: OK")


def test_abort_file_without_seq():
    with _temp_storage() as paths:
        _seed_legacy(paths)
        bad = _ev(4)
        bad.pop("seq")
        _write_json(paths["matchups"] / "T-001" / "004.json", bad)
        rc = migrate_journal.migrate(dry_run=False)
        assert rc == 1, "файл без seq не отклонён"
        assert not paths["journal"].exists()
        assert paths["matchups"].joinpath("T-001", "004.json").exists()
    print("3.1 abort при файле без seq: OK")


def test_abort_duplicate_seq():
    with _temp_storage() as paths:
        _write_json(paths["matchups"] / "T-001" / "001.json", _ev(7))
        _write_json(paths["matchups"] / "T-001" / "002.json", _ev(7))
        rc = migrate_journal.migrate(dry_run=False)
        assert rc == 1, "дубликат seq не отклонён"
        assert not paths["journal"].exists()
    print("3.1 abort при дубликате seq: OK")


def test_dry_run_changes_nothing():
    with _temp_storage() as paths:
        _seed_legacy(paths)
        rc = migrate_journal.migrate(dry_run=True)
        assert rc == 0, f"dry-run вернул {rc}"
        assert not paths["journal"].exists(), "dry-run записал журнал"
        assert paths["matchups"].joinpath("T-001", "001.json").exists()
        assert paths["matchups"].joinpath("state.json").exists()
    print("3.1 dry-run ничего не меняет: OK")


if __name__ == "__main__":
    test_successful_migration()
    test_replay_mismatch_aborts()
    test_abort_existing_journal()
    test_abort_file_without_seq()
    test_abort_duplicate_seq()
    test_dry_run_changes_nothing()
    print("\nALL MIGRATE JOURNAL TESTS PASSED")
