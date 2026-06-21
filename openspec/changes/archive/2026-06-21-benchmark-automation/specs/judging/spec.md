## MODIFIED Requirements

### Requirement: Изоляция судей через skill

Изоляция вердиктов SHALL выполняться автоматически через skill
`benchmark-04-judge` (не вручную). Skill запускает `isolate.py hide-verdicts
--task all --except <judge-id>` перед сессией и `isolate.py restore-verdicts`
после подтверждения. Пользователь не запускает `isolate.py` напрямую.

#### Scenario: Skill управляет изоляцией судей

- **WHEN** пользователь говорит "judge qwen-3-coder"
- **THEN** skill `benchmark-04-judge` запускает `isolate.py hide-verdicts --task all --except qwen-3-coder`
- **AND** готовит промпт для судьи
- **WHEN** пользователь говорит "готово"
- **THEN** skill запускает `isolate.py restore-verdicts`

### Requirement: Саморегистрация судьи

Судья SHALL саморегистрироваться в `judges.yaml` при старте через
`assign_judges.py --add-judge <model-id>`. `judges/_PROMPT.md` инструктирует
судью сделать это первым шагом (не "попроси пользователя").

#### Scenario: Судья саморегистрируется

- **WHEN** модель `qwen-3-coder` начинает оценку
- **THEN** она запускает `assign_judges.py --add-judge qwen-3-coder`
- **AND** добавляется в `judges.yaml`
- **AND** НЕ просит пользователя сделать это

### Requirement: Промпт для судьи через skill

Промпт для судьи SHALL готовиться skill `benchmark-04-judge` (не через
`generate_checklist.py --phase 3`). Skill читает задачи, анонимизированные
прогоны, готовит промпт для копипаста.

#### Scenario: Skill готовит промпт судьи

- **WHEN** пользователь говорит "judge qwen-3-coder"
- **THEN** skill `benchmark-04-judge` читает `tasks/`, `.anon-copies/`
- **AND** готовит промпт с задачами и прогонами для оценки
- **AND** показывает пользователю для копипаста в чат с qwen-3-coder

## REMOVED Requirements

### Requirement: Изоляция судей (ручная)

~~Перед оценкой судья MUST быть изолирован от чужих вердиктов.
`isolate.py hide-verdicts --task all --except <judge-id>` перемещает...~~

**Reason:** Заменено на автоматическую изоляцию через skill.
