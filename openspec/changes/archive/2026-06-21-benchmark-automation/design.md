## Context

Change `simplify-architecture` сократил сессии с 184 до 13, но пользователь
всё ещё вручную запускает python-скрипты и редактирует конфиги. Текущий workflow:

```
Пользователь:                Руки:
1. register_model.py         × вручную
2. edit judges.yaml          × вручную
3. assign_judges.py --init   × вручную
4. generate_checklist.py     × вручную
5. isolate.py hide           × вручную
6. копипаст промпта          × вручную
7. isolate.py restore        × вручную
8. aggregate.py              × вручную
```

Целевой workflow:

```
Пользователь:                Devin (IDE agent):
1. "сгенерируй задачу про X"  → диалог, формулировка, "добро?" → файл
2. "run claude-sonnet"        → isolate + промпт готов
3. [копипаст в чат с Claude]  → ждёт
4. "готово"                   → restore + проверка
5. "judge qwen"               → isolate + промпт готов
6. [копипаст в чат с Qwen]    → ждёт
7. "готово"                   → restore
8. "aggregate"                → leaderboard
```

Платформа: Windsurf/Devin Desktop IDE. Skills живут в `.windsurf/skills/`.
Модели в чатах IDE имеют доступ к файловой системе — могут сами регистрироваться,
создавать файлы, запускать git.

## Goals / Non-Goals

**Goals:**
- Пользователь не запускает python-скрипты напрямую
- Пользователь не редактирует `models.yaml`, `judges.yaml`, `anonymization.yaml` руками
- Модели сами себя регистрируют при старте роли
- Генерация задач — диалоговая (по одной), не батч
- Изоляция — автоматическая через skill
- Агрегация — автоматическая через skill
- Промпты для копипаста — готовит skill

**Non-Goals:**
- Не заменяем python-скрипты — skills обёртывают их
- Не убираем `register_model.py` — остаётся для опционального ручного режима
- Не строим UI/веб-интерфейс — только IDE skills
- Не автоматизируем открытие чатов с моделями — пользователь сам открывает
- Не валидируем корректность ответов моделей автоматически — это делает судья

## Decisions

### Decision 1: Skills в `.windsurf/skills/`

**Выбор:** `.windsurf/skills/benchmark-*/` (workspace scope)

**Альтернативы:**
- `.devin/skills/` — стандарт Devin, но Windsurf IDE читает `.windsurf/`
- `.agents/skills/` — cross-agent, но менее нативный для Windsurf
- `~/.codeium/windsurf/skills/` — global, но не коммитится с репо

**Рationale:** Windsurf/Devin Desktop нативно читает `.windsurf/skills/`.
Workspace scope = коммитится с репо, доступно всем кто клонирует.
Devin Desktop также поддерживает `.agents/skills/` для cross-agent
совместимости — можем скопировать туда при необходимости.

### Decision 2: Саморегистрация через AGENTS.md + скрипт

**Выбор:** Модель при старте роли вызывает `register_model.py --auto`
(новый флаг), который читает `model_id` из окружения чата или из
первой строки ответа модели. AGENTS.md обновляется: вместо "попроси
пользователя" — "зарегистрируйся сама через register_model.py --auto".

**Альтернативы:**
- Модель напрямую редактирует `models.yaml` — рискованно (формат)
- Devin-skill регистрирует модель — требует, чтобы пользователь
  сообщил Devin кто модель (лишний шаг)

**Rationale:** Модель в чате IDE знает свой `model_id` (выбрана
пользователем). `register_model.py --auto --id <slug> --name <name>`
— безопасный путь через существующий скрипт. Для судьи —
дополнительно `judges.yaml` обновляется (через `assign_judges.py --add-judge`).

### Decision 3: Диалоговая генерация вместо батч

**Выбор:** Skill `benchmark-gen-task` ведёт диалог с пользователем:
1. Пользователь: "хочу задачу про баги в WorkoutScoreCalculator"
2. Skill: определяет `baseline_commit` (`git rev-parse HEAD`)
3. Skill: предлагает формулировку задачи (категория, сложность, критерии)
4. Пользователь: "добро" / "измени X"
5. Skill: создаёт `tasks/<cat>/<id>/task.md`

**Альтернативы:**
- Сохранить батч-генерацию (4 задачи за 1 сессию) — пользователь
  сказал что хочет диалог, по одной задаче
- Внешняя модель-генератор — пользователь сказал "не важно какая
  модель генерирует", значит Devin (IDE agent) может сам генерировать

**Rationale:** Пользователь хочет контроль над каждой задачей.
Диалог = утверждение перед созданием файла. Батч = постфактум проверка.

### Decision 4: Skill `benchmark-run` управляет изоляцией

**Выбор:** Skill `benchmark-run <model-id>`:
1. Запускает `isolate.py hide --task all --except <model-id>`
2. Готовит промпт для участника (читает задачи, `AGENTS.md`)
3. Показывает промпт пользователю для копипаста
4. Ждёт подтверждения "готово"
5. Запускает `isolate.py restore`
6. Проверяет что файлы прогонов созданы

**Альтернативы:**
- Автоматически открывать чат с моделью — IDE не поддерживает
  программное открытие чатов с конкретной моделью
- Не изолировать — нарушает spec task-execution

**Rationale:** Пользователь копипастит промпт в отдельный чат —
это единственный ручной шаг. Всё остальное — skill.

### Decision 5: Skill `benchmark-judge` управляет оценкой

**Выбор:** Skill `benchmark-judge <judge-id>`:
1. Запускает `assign_judges.py --distribute` (если ещё не запущено)
2. Запускает `isolate.py hide-verdicts --task all --except <judge-id>`
3. Готовит промпт для судьи (читает задачи, анонимизированные прогоны)
4. Показывает промпт
5. Ждёт "готово"
6. Запускает `isolate.py restore-verdicts`
7. Проверяет что вердикты созданы

### Decision 6: Skill `benchmark-status` показывает прогресс

**Выбор:** Skill `benchmark-status` читает `runs/`, `verdicts/`, `tasks/`
и показывает:
- Сколько задач создано
- Сколько участников выполнили (по задачам)
- Сколько вердиктов написано (по судьям)
- Что осталось (сколько сессий)

### Decision 7: Skill `benchmark-aggregate` запускает агрегацию

**Выбор:** Skill `benchmark-aggregate`:
1. Запускает `aggregate.py`
2. Показывает `leaderboard.md`
3. Подсвечивает disputed прогоны

## Risks / Trade-offs

- **[Skill не вызывается автоматически]** → Mitigation: ясные `description`
  в frontmatter, пользователь может `@benchmark-run` явно
- **[Модель не саморегистрируется]** → Mitigation: AGENTS.md обновлён с
  чёткой инструкцией, `register_model.py --auto` простой вызов
- **[Слишком много skills]** → Mitigation: 6-7 skills, каждый с чёткой
  ответственностью. Не плодить микроскиллы.
- **[Windsurf-only]** → Mitigation: `.windsurf/skills/` — стандарт для
  Windsurf/Devin Desktop. При переходе на другую IDE — копируем в
  соответствующую папку.
- **[Диалог генерации медленнее батча]** → Mitigation: пользователь явно
  попросил диалог. Батч-режим остаётся через `generate_checklist.py --phase 1`
  (опционально).
