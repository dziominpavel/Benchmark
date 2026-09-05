## ADDED Requirements

### Requirement: Анонимность ответа участника

Файл ответа участника skill-прогона SHALL содержать только слот `modelA` или `modelB` в поле `model` front matter. Участник MUST NOT записывать свой реальный `model-id` внутрь ответа, во вспомогательные файлы рядом с ответом (например, `slots.json`) или в имя файла ответа, если это skill-прогон. Связь слота с реальным `id` устанавливается координатором позже, при записи вердикта.

#### Scenario: Ответ участника A

- **WHEN** `@benchmark-run-a T-001` завершает работу
- **THEN** создаётся `answers/T-001/modelA.md`
- **AND** front matter содержит `model: modelA`
- **AND** в `answers/T-001/` не создаётся `slots.json`
- **AND** участник не знает и не записывает реальный `id`

#### Scenario: Ответ участника B

- **WHEN** `@benchmark-run-b T-001` завершает работу
- **THEN** создаётся `answers/T-001/modelB.md`
- **AND** front matter содержит `model: modelB`
- **AND** файл `answers/T-001/slots.json` отсутствует

## REMOVED Requirements

(нет — существующие требования answer-management не удаляются, уточняются добавленным выше)
