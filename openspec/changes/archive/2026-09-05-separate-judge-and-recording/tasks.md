## 1. Обновить нормативные спецификации

- [x] 1.1 Перенести дельта-спеку `benchmark-workflow` в `openspec/specs/benchmark-workflow/spec.md` и убедиться, что `openspec validate --all` проходит без ошибок.
- [x] 1.2 Перенести дельта-спеку `matchup-management` в `openspec/specs/matchup-management/spec.md` и убедиться, что `openspec validate --all` проходит.
- [x] 1.3 Перенести дельта-спеку `leaderboard-ui` в `openspec/specs/leaderboard-ui/spec.md` и убедиться, что `openspec validate --all` проходит.

## 2. Обновить документацию

- [x] 2.1 Отредактировать `docs/workflow-guide.md`: убрать описание, по которому `@benchmark-judge` сам пишет `matchups/` и запускает `elo.py`; описать отдельный шаг вызова `record_verdict.py`. Проверить: `grep -n 'matchups' docs/workflow-guide.md` не содержит устаревших формулировок у судьи.
- [x] 2.2 Отредактировать `README.md`: уточнить, что вердикт записывается через `record_verdict.py` или веб-UI. Проверить: `grep -n 'record_verdict' README.md` содержит актуальную команду.

## 3. Обновить skills судьи

- [x] 3.1 Проверить и при необходимости обновить `SKILL.md` в `.devin/skills/benchmark-judge/`, `.cursor/skills/benchmark-judge/`, `.opencode/skills/benchmark-judge/`: убрать упоминания ручной записи `matchups/*.json` и `elo.py` отдельно; оставить только вызов `record_verdict.py`. Проверить: `grep -R 'elo.py' .*/skills/benchmark-judge/SKILL.md .devin/skills/benchmark-judge/SKILL.md` не возвращает устаревшие инструкции.
- [x] 3.2 Проверить `docs/judge-prompt.md`: убедиться, что шаблон судьи не предполагает доступ к `slots.json` или ELO. Проверить: `grep -n 'slots\|ELO\|рейтинг' docs/judge-prompt.md` не содержит запрещённых ссылок.

## 4. Реализовать отображение истории ELO на UI

- [x] 4.1 Изменить `tools/server.py`: в `INDEX_TEMPLATE` в блоке «История» добавить имя соперника и ELO до/после. Проверить: `python tools/server.py`, открыть `http://localhost:5000`, записать тестовый вердикт и убедиться, что в истории видны «против <соперник>», «<ELO до> → <ELO после> (<дельта>)».
- [x] 4.2 Обновить `tools/generate_html.py`: в статичном `leaderboard.html` в блоке истории (если он там есть) добавить те же поля. Проверить: `python tools/generate_html.py` и `grep -n 'opponent\|elo_before' leaderboard.html`.

## 5. Интеграционная проверка

- [x] 5.1 Запустить `python tools/test_elo.py` и `python tools/elo.py --check` — оба должны пройти.
- [x] 5.2 Прогнать ручной путь: `@benchmark-run-a T-001`, `@benchmark-run-b T-001`, `@benchmark-judge T-001` (только выбор победителя), `record_verdict.py --task T-001 --winner <a|b|draw>`, убедиться, что `matchups/T-001/NNN.json` содержит `elo.before`/`elo.after` и `model_a_id`/`model_b_id`.
- [x] 5.3 Прогнать веб-UI: записать вердикт через `localhost:5000` и убедиться, что в истории видны реальные модели, соперник и ELO до/после.
