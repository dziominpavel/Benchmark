## MODIFIED Requirements

### Requirement: Формат ответа

Каждый ответ SHALL храниться в `data/answers/<task-id>/<name>.md`, где `<name>` —
`modelA` / `modelB` для skills прогонов либо `<model-id>` из `data/models.yaml`
для ручных прогонов. Файл SHALL содержать YAML front matter (`task`, `model`,
`date`) и тело ответа. Файл ответа участника skill-прогона MUST NOT содержать
реальный `model-id`; связь слота с реальным `id` устанавливается координатором
при записи вердикта.

#### Scenario: Ответ skill прогона

- **WHEN** `@benchmark-run-a T-001` завершает работу
- **THEN** создаётся `data/answers/T-001/modelA.md`
- **AND** front matter: `{task: "T-001", model: "modelA", date: "YYYY-MM-DD"}`
- **AND** `data/answers/T-001/slots.json` не создаётся

#### Scenario: Ответ произвольной модели вручную

- **WHEN** модель `opencode-mimo-v2-5-free` отвечает на T-001 вручную
- **THEN** создаётся `data/answers/T-001/opencode-mimo-v2-5-free.md`
- **AND** front matter: `{task: "T-001", model: "opencode-mimo-v2-5-free", date: "YYYY-MM-DD"}`
- **AND** `data/answers/T-001/slots.json` не создаётся

### Requirement: Уникальность ответа

На одну задачу один слот/модель SHALL иметь один файл ответа. Повторный прогон
SHALL перезаписывать файл; вердикты со старым ответом сохраняются, ELO
пересчитывается при следующем обновлении (связи вердикт↔версия ответа нет).

#### Scenario: Повторный прогон

- **WHEN** `@benchmark-run-a T-001` запускается повторно
- **THEN** `data/answers/T-001/modelA.md` перезаписывается
- **AND** существующие вердикты остаются в силе

### Requirement: Шаблон ответа

Файл `data/answers/_TEMPLATE.md` SHALL содержать пустой шаблон с front matter
и секциями (Анализ, Находки с примером структуры, План, Дополнительные находки).
Skills прогонов используют собственный (более детальный) формат из SKILL.md,
совместимый с шаблоном по front matter.

#### Scenario: Ручной ответ из шаблона
- **WHEN** модель отвечает вручную
- **THEN** структура берётся из `data/answers/_TEMPLATE.md`
- **AND** секции заполняются находками

### Requirement: Анонимность ответа участника

Файл ответа участника skill-прогона SHALL содержать только слот `modelA` или `modelB` в поле `model` front matter. Участник MUST NOT записывать свой реальный `model-id` внутрь ответа, во вспомогательные файлы рядом с ответом (например, `slots.json`) или в имя файла ответа, если это skill-прогон. Связь слота с реальным `id` устанавливается координатором позже, при записи вердикта.

#### Scenario: Ответ участника A

- **WHEN** `@benchmark-run-a T-001` завершает работу
- **THEN** создаётся `data/answers/T-001/modelA.md`
- **AND** front matter содержит `model: modelA`
- **AND** в `data/answers/T-001/` не создаётся `slots.json`
- **AND** участник не знает и не записывает реальный `id`

#### Scenario: Ответ участника B

- **WHEN** `@benchmark-run-b T-001` завершает работу
- **THEN** создаётся `data/answers/T-001/modelB.md`
- **AND** front matter содержит `model: modelB`
- **AND** файл `data/answers/T-001/slots.json` отсутствует
