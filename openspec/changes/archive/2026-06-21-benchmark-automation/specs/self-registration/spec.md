## ADDED Requirements

### Requirement: Модель саморегистрируется при старте роли

Модель при старте роли (участник или судья) SHALL автоматически
регистрировать себя в `models.yaml` через `register_model.py --auto`.
Пользователь не редактирует `models.yaml` руками. AGENTS.md инструктирует
модель сделать это первым шагом.

#### Scenario: Участник саморегистрируется

- **WHEN** модель `claude-sonnet-4.5` начинает выполнение задачи
- **AND** её нет в `models.yaml`
- **THEN** она запускает `python tools/register_model.py --auto --id claude-sonnet-4.5 --name "Claude Sonnet 4.5" --provider Anthropic --version sonnet-4.5`
- **AND** запись добавляется в `models.yaml`

#### Scenario: Модель уже зарегистрирована

- **WHEN** модель `gpt-5` начинает выполнение
- **AND** она уже есть в `models.yaml`
- **THEN** саморегистрация пропускается (register_model.py сообщает "already exists")

### Requirement: Судья саморегистрируется в judges.yaml

Модель-судья при старте оценки SHALL автоматически добавлять себя в
`judges.yaml` через `assign_judges.py --add-judge <model-id>`. Пользователь
не редактирует `judges.yaml` руками.

#### Scenario: Судья добавлен в pool

- **WHEN** модель `qwen-3-coder` начинает оценку
- **AND** её нет в `judges.yaml`
- **THEN** она запускает `python tools/assign_judges.py --add-judge qwen-3-coder`
- **AND** запись добавляется в `judges.yaml`

#### Scenario: Судья уже в pool

- **WHEN** модель `qwen-3-coder` начинает оценку
- **AND** она уже есть в `judges.yaml`
- **THEN** добавление пропускается

### Requirement: register_model.py --auto флаг

`register_model.py` SHALL поддерживать флаг `--auto` для саморегистрации
моделей. При `--auto` скрипт не требует `--provider` и `--version` (опциональны),
достаточно `--id` и `--name`. Если модель уже есть — сообщает и завершает
успешно (не ошибка).

#### Scenario: Авто-регистрация без provider

- **WHEN** `register_model.py --auto --id glm-4.6 --name "GLM-4.6"` запущен
- **THEN** модель добавляется в `models.yaml` с пустым `provider` и `version`
- **AND** скрипт завершает успешно

#### Scenario: Авто-регистрация существующей модели

- **WHEN** `register_model.py --auto --id gpt-5 --name "GPT-5"` запущен
- **AND** `gpt-5` уже в `models.yaml`
- **THEN** скрипт сообщает "already exists" и завершает успешно (exit 0)

### Requirement: assign_judges.py --add-judge флаг

`assign_judges.py` SHALL поддерживать флаг `--add-judge <model-id>` для
добавления модели в `judges.yaml`. Если модель уже в pool — сообщает
и завершает успешно.

#### Scenario: Добавление судьи

- **WHEN** `assign_judges.py --add-judge qwen-3-coder` запущен
- **THEN** `qwen-3-coder` добавляется в `judges.yaml` в список `judges`
- **AND** если модель не в `models.yaml`, скрипт сообщает предупреждение

### Requirement: AGENTS.md инструктирует саморегистрацию

AGENTS.md SHALL обновить раздел "Перед началом прогона": вместо "попроси
пользователя добавить через register_model.py" — "зарегистрируйся сама через
`register_model.py --auto`". Аналогично для судьи в `judges/_PROMPT.md`.

#### Scenario: AGENTS.md обновлён

- **WHEN** модель читает AGENTS.md раздел "Перед началом"
- **THEN** шаг 1 говорит "зарегистрируйся сама через register_model.py --auto"
- **AND** НЕ говорит "попроси пользователя"
