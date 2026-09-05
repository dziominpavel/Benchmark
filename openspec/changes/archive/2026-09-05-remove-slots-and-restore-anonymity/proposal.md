## Why

Текущий workflow с `answers/<task>/slots.json` нарушает анонимность судьи: run-скиллы пишут mapping `modelA`/`modelB` → реальный `id` в файл рядом с ответами, а `record_verdict.py` читает этот файл и возвращает реальные названия моделей в той же сессии, где работал судья. Мы обсудили, что судья не должен знать, какие модели он оценивает. Файл `slots.json` не нужен: реальные `id` вводятся на этапе записи вердикта координатором (UI/CLI), а участники и судья работают только с анонимными слотами `modelA`/`modelB`.

## What Changes

- **BREAKING**: Удалена концепция `answers/<task>/slots.json`. Участники больше не создают и не обновляют этот файл.
- **BREAKING**: `record_verdict.py` и `elo.py` больше не разрешают слоты `modelA`/`modelB`. Для записи вердикта требуются явные реальные `id` моделей (`--model-a`, `--model-b` в CLI; dropdown в UI).
- **BREAKING**: `benchmark-judge` skill больше не вызывает `record_verdict.py` и не видит реальные `id`. Он только оценивает ответы и объявляет `winner` (`a` | `b` | `draw`).
- Обновлены `benchmark-run-a`/`benchmark-run-b` skills: убрана запись `slots.json` и саморегистрация; участник пишет `answers/<task>/modelA.md` / `modelB.md`.
- Обновлена документация и спецификации: `AGENTS.md`, `README.md`, `docs/workflow-guide.md`, `docs/judge-prompt.md`, `docs/architecture.md`, `docs/elo-mechanics.md`, `openspec/specs/answer-management`, `benchmark-workflow`, `matchup-management`, `data-storage`.
- Тесты `tools/test_elo.py` приведены в соответствие: verdict с неразрешёнными идентификаторами использует `unknown-X` вместо `modelA`/`modelB`.

## Capabilities

### New Capabilities

(нет)

### Modified Capabilities

- `answer-management`: убрать упоминания `slots.json`; участник пишет `modelA.md`/`modelB.md` без сохранения реального `id`.
- `benchmark-workflow`: судья (skill/ручной) только определяет `winner`; запись вердикта выполняется отдельно с реальными `id`.
- `matchup-management`: `record_verdict.py` не разрешает слоты; вердикт записывается с реальными `model_a_id`/`model_b_id`.
- `data-storage`: убрать `answers/<task>/slots.json` из списка source-of-truth файлов.

## Impact

- Код: `tools/elo.py`, `tools/record_verdict.py`, `tools/test_elo.py`, `tools/server.py` (minor: help text/defaults).
- Skills: `.devin/skills/benchmark-run-a/SKILL.md`, `.devin/skills/benchmark-run-b/SKILL.md`, `.devin/skills/benchmark-judge/SKILL.md`, плюс зеркала в `.cursor/skills/`, `.opencode/skills/`.
- Документация: `AGENTS.md`, `README.md`, `docs/workflow-guide.md`, `docs/judge-prompt.md`, `docs/architecture.md`, `docs/elo-mechanics.md`.
- Спецификации: `openspec/specs/answer-management/spec.md`, `openspec/specs/benchmark-workflow/spec.md`, `openspec/specs/matchup-management/spec.md`, `openspec/specs/data-storage/spec.md`.
- Данные: существующие `matchups/general/*.json` и `answers/T-001/modelA.md` не затрагиваются. `slots.json` в репозитории нет.
