## 1. Вычисление `recommended_task` в `pairing-algorithm`

- [x] 1.1 В `tools/server.py::get_recommendations` построить множество вердиктов пары по таскам на основе `load_matchups()` и `resolve_matchup_models`. **Verification:** `get_recommendations` возвращает пары с корректным `pair_games` и новым полем `task_verdicts`.
- [x] 1.2 Добавить список активных тасок (от `elo.active_tasks`) и для каждой пары выбрать первый по порядку `T-NNN` активный таск, для которого у пары нет неаннулированного вердикта; если все заполнены — первый активный. **Verification:** unit-проверка: при `T-001`, `T-002` активных и вердикте только в `T-001` для пары `A-B` возвращается `recommended_task: T-002`.
- [x] 1.3 Добавить поле `recommended_task` в возвращаемый `dict` рекомендации. **Verification:** `format_reason` и `leaderboard()` могут читать `rec["recommended_task"]`.

## 2. Проверка наличия ответов

- [x] 2.1 Добавить в `tools/server.py` вспомогательную функцию `has_answer(model_id, task_id, index_data)` на основе `index_data["tasks"][task_id]["answers"]`. **Verification:** функция возвращает `True` для существующего `data/answers/T-001/<model-id>.md`, `False` — если файла нет.
- [x] 2.2 Добавить в `get_recommendations` (или в `leaderboard()`) вычисление `missing_answers` — список моделей пары без ответа на `recommended_task`. **Verification:** `leaderboard()` передаёт в шаблон поля `has_answer_a` и `has_answer_b`.

## 3. UI и подстановка формы

- [x] 3.1 В HTML-шаблоне `INDEX_TEMPLATE` (`tools/server.py`) добавить строку «таск: `{{ rec.recommended_task }}`» под парой и пометку «· нужны ответы», если `has_answer_a` или `has_answer_b` — `False`. **Verification:** в браузере блок рекомендации показывает `таск: T-001` и/или пометку.
- [x] 3.2 Изменить JS `usePair(a, b)` → `usePair(a, b, task)` и выставлять `document.getElementById('taskField').value = task`. **Verification:** при нажатии «Прогнать» select «Таск» формы принимает значение `recommended_task`.
- [x] 3.3 Обновить `onclick` кнопки «Прогнать» в шаблоне: `usePair('{{ rec.model_a }}', '{{ rec.model_b }}', '{{ rec.recommended_task }}')`. **Verification:** в исходном коде сервера передаётся три аргумента.

## 4. Валидация и регрессионные проверки

- [x] 4.1 Запустить `python tools/elo.py --check` и убедиться, что журнал вердиктов и `index.json` целостны. **Verification:** exit code 0, нет warnings.
- [x] 4.2 Запустить `python tools/test_elo.py` и убедиться, что ELO-тесты проходят. **Verification:** все тесты passed.
- [x] 4.3 Запустить `python tools/server.py`, открыть главную страницу и проверить: отображается `recommended_task`, кнопка «Прогнать» подставляет модели и таск в форму. **Verification:** ручная проверка в браузере на `localhost:5000`.
- [x] 4.4 Запустить `openspec validate --all` и убедиться, что планирующие артефакты и существующие спеки валидны. **Verification:** exit code 0.
