## 1. Skills и AGENTS

- [x] 1.1 Обновить `AGENTS.md`: убрать раздел «Запиши маппинг слота» и `slots.json`; убрать саморегистрацию как обязательный шаг для run-скиллов. Проверить: `grep -n "slots" AGENTS.md` не даёт совпадений.
- [x] 1.2 Обновить `.devin/skills/benchmark-run-a/SKILL.md`: убрать шаг создания `slots.json` и саморегистрацию; путь ответа — `answers/<task-id>/modelA.md`. Проверить: `grep -n "slots" .devin/skills/benchmark-run-a/SKILL.md` пусто.
- [x] 1.3 Обновить `.devin/skills/benchmark-run-b/SKILL.md`: аналогично 1.2. Проверить: `grep -n "slots" .devin/skills/benchmark-run-b/SKILL.md` пусто.
- [x] 1.4 Обновить `.devin/skills/benchmark-judge/SKILL.md`: убрать шаг вызова `record_verdict.py` и упоминания `slots.json`; skill выводит только `winner`. Проверить: `grep -n "record_verdict\|slots" .devin/skills/benchmark-judge/SKILL.md` пусто.
- [x] 1.5 Синхронизировать `.cursor/skills/` и `.opencode/skills/` зеркала для `benchmark-run-a`, `benchmark-run-b`, `benchmark-judge`. Проверить: сравнить с `.devin/skills/` через `diff` или `fc`.

## 2. Код и инструменты

- [x] 2.1 Удалить из `tools/elo.py`: константу `SLOT_NAMES`, функцию `load_slots_map`, slot fallback в `resolve_matchup_models`, чтение `slots` в `record_verdict`. Проверить: `grep -n "slots\|SLOT_NAMES\|modelA\|modelB" tools/elo.py` пусто.
- [x] 2.2 Обновить `tools/record_verdict.py`: убрать default `modelA`/`modelB` для `--model-a`/`--model-b`; help text указывает, что требуются реальные id. Проверить: `python tools/record_verdict.py --task T-001 --winner a` завершается ошибкой без id.
- [x] 2.3 Обновить `tools/test_elo.py`: в `test_unknown_models_warn` заменить `modelA`/`modelB` на `unknown-A`/`unknown-B`. Проверить: `python tools/test_elo.py` проходит.
- [x] 2.4 Обновить `tools/server.py`: убрать упоминания `slots.json` (help/комментарии) и убедиться, что `record_verdict` вызывается с реальными id. Проверить: `grep -n "slots" tools/server.py` пусто.

## 3. Документация

- [x] 3.1 Обновить `README.md`: убрать `slots.json` из структуры и workflow; судья — оценка, запись — через UI/CLI. Проверить: `grep -n "slots" README.md` пусто.
- [x] 3.2 Обновить `docs/workflow-guide.md`: judge skill выдаёт только `winner`; запись вердикта — отдельно с реальными id. Проверить: `grep -n "slots\|record_verdict.*T-001" docs/workflow-guide.md` корректно.
- [x] 3.3 Обновить `docs/judge-prompt.md`: убрать упоминание `record_verdict.py`, `slots`, ELO из шаблона судьи. Проверить: `grep -n "slots\|record_verdict\|ELO\|рейтинг" docs/judge-prompt.md` пусто.
- [x] 3.4 Обновить `docs/architecture.md`: убрать `slots.json` из диаграмм и хранения. Проверить: `grep -n "slots" docs/architecture.md` пусто.
- [x] 3.5 Обновить `docs/elo-mechanics.md`: убрать фразу о разрешении через `slots.json`. Проверить: `grep -n "slots" docs/elo-mechanics.md` пусто.

## 4. OpenSpec спецификации

- [x] 4.1 Обновить `openspec/specs/answer-management/spec.md`: добавить требование анонимности ответа, запретить `slots.json`. Проверить: `openspec validate --all` проходит.
- [x] 4.2 Обновить `openspec/specs/benchmark-workflow/spec.md`: judge skill only winner; record requires real id. Проверить: `openspec validate --all` проходит.
- [x] 4.3 Обновить `openspec/specs/matchup-management/spec.md`: убрать разрешение слотов через `slots.json`. Проверить: `openspec validate --all` проходит.
- [x] 4.4 Обновить `openspec/specs/data-storage/spec.md`: убрать `slots.json` из source-of-truth. Проверить: `openspec validate --all` проходит.

## 5. Верификация

- [x] 5.1 Запустить `python tools/test_elo.py` — все тесты проходят.
- [x] 5.2 Запустить `python tools/elo.py --check` — нет предупреждений.
- [x] 5.3 Проверить, что `slots.json` не остался в рабочей копии: `find . -name slots.json` (или аналог) пуст.
- [x] 5.4 Проверить `git diff --stat`: изменения только в ожидаемых файлах; `answers/T-001/modelA.md` не затронут.
