## MODIFIED Requirements

### Requirement: Изоляция через skill

Изоляция прогонов SHALL выполняться автоматически через skill `benchmark-03-run`
(не вручную). Skill запускает `isolate.py hide --task all --except <model-id>`
перед сессией и `isolate.py restore` после подтверждения пользователя.
Пользователь не запускает `isolate.py` напрямую.

#### Scenario: Skill управляет изоляцией

- **WHEN** пользователь говорит "run claude-sonnet-4.5"
- **THEN** skill `benchmark-03-run` запускает `isolate.py hide --task all --except claude-sonnet-4.5`
- **AND** готовит промпт для участника
- **WHEN** пользователь говорит "готово"
- **THEN** skill запускает `isolate.py restore`
- **AND** пользователь не запускал `isolate.py` напрямую

### Requirement: Саморегистрация участника

Участник SHALL саморегистрироваться в `models.yaml` при старте через
`register_model.py --auto`. AGENTS.md инструктирует модель сделать это
первым шагом (не "попроси пользователя").

#### Scenario: Участник саморегистрируется

- **WHEN** модель `claude-sonnet-4.5` начинает выполнение
- **THEN** она запускает `register_model.py --auto --id claude-sonnet-4.5 --name "Claude Sonnet 4.5"`
- **AND** НЕ просит пользователя сделать это

### Requirement: Скрытие golden-answer от участников

`isolate.py hide --task all --except <model-id>` SHALL также скрывать
папку `tasks/bugfix/<id>/golden-answer/` от участника. Golden answer
содержит эталонное решение bugfix-задачи — участник не должен его видеть
во время выполнения. Это позволяет использовать любую модель как resolver
без конфликта ролей (resolver может быть участником той же задачи,
если golden answer скрыт).

#### Scenario: Golden answer скрыт от участника

- **WHEN** `isolate.py hide --task all --except claude-sonnet-4.5` запущен
- **THEN** папки `tasks/bugfix/*/golden-answer/` перемещаются в сташ
- **AND** участник `claude-sonnet-4.5` не видит golden answer во время выполнения
- **WHEN** `isolate.py restore` запущен
- **THEN** папки `golden-answer/` возвращаются на место

#### Scenario: Resolver = участник той же задачи (разрешено)

- **WHEN** Claude была resolver'ом B-001 (создала golden answer)
- **AND** Claude выполняет B-001 как участник
- **THEN** `isolate.py hide` скрывает `tasks/bugfix/B-001/golden-answer/`
- **AND** Claude не видит свой собственный golden answer в новом чате
- **AND** прогон честный (Claude решает задачу заново, не помня решение)

## REMOVED Requirements

### Requirement: Изоляция по задаче (ручная)

~~Перед выполнением участник MUST быть изолирован от чужих прогонов.
`isolate.py hide --task all --except <model-id>` перемещает чужие папки...~~

**Reason:** Заменено на автоматическую изоляцию через skill. Скрипт
`isolate.py` остаётся, но вызывается skill'ом, не пользователем.
