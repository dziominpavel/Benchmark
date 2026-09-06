# data-storage Specification

## MODIFIED Requirements

### Requirement: .gitignore

`.gitignore` SHALL исключать: `__pycache__/`, `*.pyc`, окружения, IDE-кэши,
ОС-мусор. `index.json` MUST NOT игнорироваться (коммитится). Статичный
`leaderboard.html` более не генерируется, поэтому `.gitignore` не SHALL
содержать специальных правил для него.

#### Scenario: Проверка .gitignore

- **WHEN** выполняется `git status`
- **THEN** `index.json` виден (не игнорируется)
- **AND** `__pycache__/` игнорируется
- **AND** `leaderboard.html` не упоминается в `.gitignore`
