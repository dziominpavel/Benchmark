## Context

См. `proposal.md`. Текущий `record_verdict.py` пытается разрешить `modelA`/`modelB` через `answers/<task>/slots.json`, а run-скиллы инструктируют участников создавать этот файл. Это создаёт persisted mapping между слотом и реальным `id`, который теоретически доступен судье в той же файловой системе.

## Goals / Non-Goals

**Goals:**
- Убрать `slots.json` из всех рабочих инструкций, skills, кода, спек и docs.
- Участники работают только с `modelA`/`modelB`; реальный `id` появляется только при записи вердикта.
- `benchmark-judge` skill остаётся read-only: оценивает и выдаёт `winner`, не вызывает `record_verdict`.
- `record_verdict.py` и `elo.py` принимают только реальные `id`.

**Non-Goals:**
- Добавлять автоматическую анонимизацию через отдельные сессии или skill permissions — это механизм Devin, не фиксируем в MVP.
- Менять формат `matchups/*.json` (version 2 с `model_a_id`/`model_b_id` и `elo` снэпшотами остаётся).
- Менять pairing algorithm или leaderboard UI, кроме удаления упоминаний `slots.json`.

## Decisions

1. **Никаких `slots.json`.**
   - Рационал: единственный способ гарантировать, что судья не узнает реальные `id`, — не хранить mapping в репозитории рядом с ответами.
   - Альтернатива: хранить mapping в `models.yaml` или `.git/config` — отклонена, потому что это всё равно persisted state, доступный в репозитории.

2. **`record_verdict.py` требует явные реальные `id`.**
   - Рационал: координатор (пользователь) знает, какая моделя была в слоте A/B, потому что он запускал run-скиллы. CLI/UI вводят эти id.
   - Альтернатива: оставить default `modelA`/`modelB` с auto-resolution — отклонена, так как требует `slots.json`.

3. **`benchmark-judge` skill только выдаёт `winner`.**
   - Рационал: судья не должен видеть реальные id. Запись — отдельный шаг, выполняемый координатором.
   - Альтернатива: skill судьи вызывает `record_verdict` — отклонена, так как возвращает реальные id и ELO в сессию судьи.

4. **Run-скиллы не саморегистрируются и не пишут `slots.json`.**
   - Рационал: участник пишет только `modelA.md`/`modelB.md`; реальная модель регистрируется пользователем через UI/`register_model.py` до или после прогона.
   - Альтернатива: участник сам регистрируется и пишет `slots.json` — отклонена.

5. **Тест `test_unknown_models_warn` использует `unknown-A`/`unknown-B` вместо `modelA`/`modelB`.**
   - Рационал: `modelA`/`modelB` больше не являются валидными fallback-именами, но проверка warning о неразрешённых моделях остаётся нужна.

## Risks / Trade-offs

- **[Пользователь должен помнить mapping A/B → real id]** → Mitigation: front matter ответа содержит `model: modelA`/`modelB`, что напоминает, какой слот; UI/CLI форма требует явного выбора.
- **[Старые скиллы в cursor/opencode/devin скажут создать slots.json]** → Mitigation: обновить все зеркала одновременно.
- **[Существующие вердикты без `model_a_id`/`model_b_id`]}** → Mitigation: все текущие `matchups/general/*.json` уже содержат реальные `id`; слотный fallback больше не нужен.
- **[Ручная запись вердикта стала длиннее]** → Mitigation: веб-UI остаётся основным recorder; CLI `--model-a`/`--model-b` требуются только при вызове вручную.

## Migration Plan

Миграция данных не требуется: `slots.json` в репозитории нет; существующие вердикты используют реальные `id`.

1. Обновить `AGENTS.md`, `docs/*`, `README.md`.
2. Обновить все зеркала `benchmark-run-a/b/judge` SKILLS.
3. Удалить из `elo.py`: `SLOT_NAMES`, `load_slots_map`, slot resolution в `resolve_matchup_models` и `record_verdict`.
4. Удалить default `modelA`/`modelB` из `record_verdict.py`; обновить help text.
5. Обновить `test_elo.py`.
6. Обновить OpenSpec main specs.
7. Запустить `python tools/test_elo.py`, `python tools/elo.py --check`.
