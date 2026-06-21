## MODIFIED Requirements

### Requirement: Агрегация через skill

Агрегация SHALL запускаться через skill `benchmark-05-aggregate` (не вручную).
Skill запускает `aggregate.py`, показывает `leaderboard.md`, подсвечивает
disputed прогоны. Пользователь не запускает `aggregate.py` напрямую.

#### Scenario: Skill запускает агрегацию

- **WHEN** пользователь говорит "aggregate"
- **THEN** skill `benchmark-05-aggregate` запускает `python tools/aggregate.py`
- **AND** показывает содержимое `leaderboard.md`
- **AND** подсвечивает disputed прогоны (разброс > 2)

#### Scenario: Пользователь не запускает python

- **WHEN** пользователь хочет обновить leaderboard
- **THEN** он говорит "aggregate" (не запускает `python tools/aggregate.py`)
- **AND** skill вызывает скрипт
- **AND** пользователь не видит python-команды
