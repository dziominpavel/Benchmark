## MODIFIED Requirements

### Requirement: Source of truth — файлы

Исходные данные SHALL храниться в файлах: `models.yaml` (реестр), `tasks/T-NNN-<slug>/task.md` (задачи), `answers/T-NNN/*.md` (ответы: `modelA.md` / `modelB.md` от skills либо `<model-id>.md` вручную), `matchups/T-NNN/NNN.json` (вердикты skill судьи) и `matchups/general/NNN.json` (вердикты веб-формы). `answers/<task>/slots.json` MUST NOT использоваться как source of truth и MUST NOT существовать. Эти файлы SHALL коммититься в git.

#### Scenario: Git diff ответа

- **WHEN** модель пишет ответ
- **THEN** git diff показывает добавленный Markdown-файл в `answers/T-NNN/`
- **AND** не создаётся `answers/T-NNN/slots.json`

#### Scenario: Git diff вердикта

- **WHEN** записывается новый вердикт
- **THEN** git diff показывает один добавленный JSON-файл
- **AND** `slots.json` не появляется
