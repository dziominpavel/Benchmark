## 1. Саморегистрация моделей

- [x] 1.1 Добавить флаг `--auto` в `register_model.py` — не требует `--provider`/`--version` (опциональны), если модель уже есть — exit 0 (не ошибка)
- [x] 1.2 Добавить флаг `--add-judge <model-id>` в `assign_judges.py` — добавляет модель в `judges.yaml`, если уже есть — exit 0
- [x] 1.3 Обновить `isolate.py hide` — также скрывать `tasks/bugfix/*/golden-answer/` в `.isolation-stash-golden/`; `restore` — возвращает
- [x] 1.4 Обновить `AGENTS.md` раздел "Перед началом" — шаг 1: "зарегистрируйся сама через `register_model.py --auto`" (вместо "попроси пользователя")
- [x] 1.5 Обновить `judges/_PROMPT.md` — добавить шаг: "судья саморегистрируется через `assign_judges.py --add-judge <model-id>`"
- [x] 1.6 Проверить: `register_model.py --auto --id test-model --name "Test"` создаёт запись; повторный вызов — exit 0
- [x] 1.7 Проверить: `assign_judges.py --add-judge test-model` добавляет в `judges.yaml`; повторный вызов — exit 0
- [x] 1.8 Проверить: `isolate.py hide --task all --except test` скрывает `golden-answer/`; `restore` — возвращает

## 2. Skills — пронумерованные по порядку использования

Скиллы именуются `benchmark-NN-<action>` где NN — порядковый номер шага в workflow.
Пользователь вызывает их по порядку: 01 → 02 → 03 → ... → 99.
`benchmark-00-status` — вне порядка, доступен всегда.

- [x] 2.1 Создать `.windsurf/skills/benchmark-00-status/SKILL.md` — показывает текущий шаг workflow, прогресс, что делать дальше. Доступен ВСЕГДА, вне нумерации. Помогает не запутаться.
- [x] 2.2 Создать `.windsurf/skills/benchmark-01-gen-task/SKILL.md` — ШАГ 1: диалоговая генерация задачи (по одной). Определяет `baseline_commit`, предлагает формулировку, утверждение, создание `tasks/<cat>/<id>/task.md`. Поддерживает feature/bugfix/refactor/review.
- [x] 2.3 Создать `.windsurf/skills/benchmark-02-resolve/SKILL.md` — ШАГ 2: golden answer для bugfix. Принимает `<task-id>`, готовит промпт для resolver-модели, после "готово" проверяет `golden-answer/answer.md` + `diff.patch`.
- [x] 2.4 Создать `.windsurf/skills/benchmark-03-run/SKILL.md` — ШАГ 3: запуск участника. Принимает `<model-id>`, запускает `isolate.py hide --task all --except <model-id>` (включая скрытие golden-answer), готовит промпт участника, ждёт "готово", `isolate.py restore`, проверяет `runs/<task-id>/<model-id>/`.
- [x] 2.5 Создать `.windsurf/skills/benchmark-04-judge/SKILL.md` — ШАГ 4: запуск судьи. Принимает `<judge-id>`, запускает `assign_judges.py --distribute`, `isolate.py hide-verdicts --task all --except <judge-id>`, готовит промпт судьи, ждёт "готово", `isolate.py restore-verdicts`, проверяет `verdicts/`.
- [x] 2.6 Создать `.windsurf/skills/benchmark-05-aggregate/SKILL.md` — ШАГ 5: агрегация. Запускает `aggregate.py`, показывает `leaderboard.md`, подсвечивает disputed.
- [x] 2.7 Создать `.windsurf/skills/benchmark-06-stale/SKILL.md` — опционально: проверка устаревания задач. Запускает `check_stale.py`, показывает отчёт. Вне основного порядка (по запросу).
- [x] 2.8 В каждом SKILL.md указать в `description`: "Шаг N из 5. Используй после `benchmark-(N-1)-*`. Дальше: `benchmark-(N+1)-*`." — для подсказки пользователю и авто-вызова.
- [x] 2.9 В `benchmark-00-status` включить логику: читает `tasks/`, `runs/`, `verdicts/`, показывает на каком шаге пользователь, что сделано, что осталось, какую команду вызвать следующей.
- [x] 2.10 Проверить: все 7 skills обнаруживаются в `.windsurf/skills/` через `@benchmark-*`
- [x] 2.11 Проверить: `benchmark-00-status` корректно показывает прогресс
- [x] 2.12 Проверить: `benchmark-01-gen-task` создаёт валидный `task.md` с `baseline_commit`
- [x] 2.13 Проверить: `benchmark-03-run` корректно изолирует (включая golden-answer) и восстанавливает
- [x] 2.14 Проверить: `benchmark-04-judge` корректно изолирует вердикты и восстанавливает
- [x] 2.15 Проверить: `benchmark-05-aggregate` запускается и показывает leaderboard

## 3. Документация

- [x] 3.1 Обновить `README.md` — workflow через пронумерованные skills (01→02→03→04→05), примеры команд, таблица "команда → шаг → что делает"
- [x] 3.2 Обновить `AGENTS.md` — саморегистрация, ссылка на skills
- [x] 3.3 Обновить `.gitignore` — `.windsurf/skills/` НЕ игнорируется (коммитится с репо)
- [x] 3.4 Создать `.windsurf/skills/README.md` — обзор всех skills с номерами и порядком

## 4. Финальная проверка

- [x] 4.1 `openspec validate --all` — все спеки валидны
- [x] 4.2 Проверить что все 7 skills обнаруживаются в `.windsurf/skills/`
- [x] 4.3 `register_model.py --auto --id test --name "Test"` — работает
- [x] 4.4 `assign_judges.py --add-judge test` — работает
- [x] 4.5 `isolate.py hide` скрывает golden-answer — работает
- [x] 4.6 Проверить что `AGENTS.md` содержит инструкцию саморегистрации
- [x] 4.7 Проверить что `judges/_PROMPT.md` содержит инструкцию саморегистрации
- [x] 4.8 Удалить test-модель из `models.yaml` и `judges.yaml` после проверки
- [x] 4.9 Финальный `openspec validate --all`
