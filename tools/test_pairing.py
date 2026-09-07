#!/usr/bin/env python3
"""test_pairing.py — проверка, что get_recommendations исключает архивные модели."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from elo import generate_index, save_index, load_models_yaml, REPO_ROOT, MODELS_PATH, INDEX_PATH
import server
from server import get_recommendations


def test_rematch_recommendations() -> None:
    """Все пары сыграны → рекомендуются рематчи с min pair_games."""
    index_data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    models = index_data.get("models", {})
    active_ids = sorted(
        mid for mid, m in models.items()
        if m.get("status", "active") != "archived"
    )
    if len(active_ids) < 2:
        print("rematch: меньше двух активных моделей — пропуск")
        return

    # Подменяем статистику: все пары сыграли по 2 раза, одна — 1 раз
    fake_stats = {}
    for i in range(len(active_ids)):
        for j in range(i + 1, len(active_ids)):
            a_id, b_id = active_ids[i], active_ids[j]
            fake_stats[frozenset({a_id, b_id})] = {
                "games": 2,
                "wins": {a_id: 1, b_id: 1},
            }
    min_pair = frozenset({active_ids[0], active_ids[1]})
    fake_stats[min_pair] = {
        "games": 1,
        "wins": {active_ids[0]: 1, active_ids[1]: 0},
    }

    real_fn = server.get_pair_stats
    server.get_pair_stats = lambda: fake_stats
    try:
        recs = get_recommendations(index_data, top_n=3)
    finally:
        server.get_pair_stats = real_fn

    assert recs, "рекомендации пусты при полном покрытии"
    assert all(r["pair_games"] >= 1 for r in recs), (
        f"ожидались только рематчи, получено: {recs}"
    )
    first = recs[0]
    assert first["pair_games"] == 1, (
        f"первой должна идти пара с min pair_games=1, получено: {first}"
    )
    assert frozenset({first["model_a"], first["model_b"]}) == min_pair
    assert "reason" not in first, f"поле reason должно быть удалено: {first}"
    assert first["h2h_label"].startswith("личные встречи:"), (
        f"ожидалась строка личных встреч: {first}"
    )
    print(f"rematch OK: первая рекомендация — рематч "
          f"{first['model_a']} vs {first['model_b']} ({first['h2h_label']})")


def find_archiveable_model() -> str:
    """Находит активную модель, которую можно заархивировать."""
    for m in load_models_yaml():
        if m.get("status", "active") == "active":
            return m["id"]
    raise RuntimeError("Нет активных моделей для архивации")


def run_archive(model_id: str, restore: bool = False) -> None:
    cmd = [sys.executable, str(REPO_ROOT / "tools" / "archive_model.py")]
    if restore:
        cmd.extend(["--restore", model_id])
    else:
        cmd.append(model_id)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"archive_model.py failed: {result.stderr}")


def main() -> int:
    models_backup = MODELS_PATH.with_suffix(".yaml.bak")
    index_backup = INDEX_PATH.with_suffix(".json.bak")
    shutil.copy2(MODELS_PATH, models_backup)
    if INDEX_PATH.exists():
        shutil.copy2(INDEX_PATH, index_backup)

    model_id = find_archiveable_model()
    print(f"Тест: архивируем {model_id}, проверяем рекомендации")

    try:
        run_archive(model_id)

        # Пересчитываем index, чтобы status архивной попал в index.json
        save_index(generate_index())

        index_data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        recs = get_recommendations(index_data, top_n=10)

        for r in recs:
            assert model_id not in (r["model_a"], r["model_b"]), (
                f"Архивная модель {model_id} попала в рекомендации: {r}"
            )

        print(f"pairing filter OK: архивная {model_id} исключена, рекомендаций: {len(recs)}")

        test_rematch_recommendations()
        return 0
    finally:
        run_archive(model_id, restore=True)
        if index_backup.exists():
            shutil.copy2(index_backup, INDEX_PATH)
        models_backup.unlink(missing_ok=True)
        index_backup.unlink(missing_ok=True)
        # Восстанавливаем index.json из актуального состояния
        save_index(generate_index())


if __name__ == "__main__":
    sys.exit(main())
