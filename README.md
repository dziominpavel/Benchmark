# Benchmark

Репозиторий для сравнения LLM-моделей через **попарные сравнения и ELO-рейтинг**.
Модели отвечают на аналитические задачи (анализ проекта, поиск багов, планирование),
судья сравнивает два ответа и выбирает победителя, ELO пересчитывается.

## Зачем

Подобрать LLM-модель под свои задачи, опираясь на воспроизводимые сравнения
в реальном коде. Модели соревнуются на одних и тех же задачах, оцениваются
попарно (как в LMSYS Chatbot Arena), рейтинг — по системе ELO.

## Архитектура

**ELO вместо баллов.** Нет рубрикатора с баллами 0–5. Судья сравнивает два
ответа и выбирает победителя. ELO пересчитывается из всех вердиктов.
Один глобальный рейтинг — кто сильнее в целом.

**Минимальный прогон:** 1 задача + 2 ответа + 1 вердикт = валидный ELO
(победитель 1220, проигравший 1180 от стартовых 1200).

## Workflow (5 шагов)

```
① Создать задачу          python tools/register_task.py --title "..." [--slug ...]
                          (или вручную из tasks/_TEMPLATE.md)
② Прогнать модели         @benchmark-run-a T-001, @benchmark-run-b T-001
③ Судья                   @benchmark-judge T-001 (или вручную по docs/judge-prompt.md)
                          → только выбор победителя
④ Записать вердикт        координатор: веб-UI localhost:5000 или record_verdict.py
                          с явным --task T-NNN и --model-a/--model-b → matchups/T-NNN/NNN.json
⑤ Leaderboard             веб-UI (localhost:5000) или leaderboard.html
```

Подробная инструкция: **[docs/workflow-guide.md](docs/workflow-guide.md)**

## Skills

| Skill | Что делает |
|-------|-----------|
| `@benchmark-run-a T-NNN` | Прогон слота A: читает task.md, изучает код, пишет `answers/T-NNN/modelA.md` |
| `@benchmark-run-b T-NNN` | Прогон слота B: то же самое → `answers/T-NNN/modelB.md` |
| `@benchmark-judge T-NNN` | Судья: оценивает оба ответа (5 критериев, /50), выбирает победителя; не вызывает `record_verdict.py` |

Skills продублированы для трёх сред: `.opencode/skills/`, `.cursor/skills/`, `.devin/skills/`.
Ручное судейство без skill — по шаблону [docs/judge-prompt.md](docs/judge-prompt.md),
запись результата — через веб-сервер.

## Структура

```
Benchmark/
├── AGENTS.md              # Протокол модели-участницы (слоты modelA/modelB)
├── README.md              # Этот файл
├── models.yaml            # Реестр моделей (status: active/archived)
├── judges.yaml            # Резерв пула судей (пока пуст, судейство — skill/вручную)
├── index.json             # Кэш ELO + сводки (генерируется tools/elo.py, коммитится)
├── leaderboard.html       # Статичный экспорт (генерируется, в git не коммитится)
├── start.bat              # Запуск сервера в Windows (открывает localhost:5000)
│
├── tasks/
│   ├── _TEMPLATE.md       # Шаблон задачи (создание — register_task.py или вручная копия)
│   └── T-NNN-<slug>/
│       └── task.md        # Описание + критерии + baseline_commit (опц.)
│
├── answers/               # Ответы: modelA.md / modelB.md (skills) или <model-id>.md (вручную)
│   ├── _TEMPLATE.md
│   └── T-NNN/
│       ├── modelA.md
│       └── modelB.md
│
├── matchups/              # Вердикты (попарные сравнения)
│   └── T-NNN/
│       └── NNN.json       # От record_verdict.py: task, model_a/b, winner, date, elo
│
├── docs/
│   ├── architecture.md    # Полная архитектура
│   ├── elo-mechanics.md   # Математика ELO
│   ├── workflow-guide.md  # Пошаговая инструкция
│   └── judge-prompt.md    # Шаблон промпта судьи (ручное судейство)
│
├── tools/
│   ├── elo.py             # ELO-движок (пересчёт из matchups → index.json) + --check
│   ├── test_elo.py        # Юнит-тесты движка
│   ├── server.py          # Flask: leaderboard + рекомендации пар + ввод вердиктов + управление тасками
│   ├── generate_html.py   # Статичный leaderboard.html
│   ├── register_model.py  # Регистрация модели (в т.ч. --auto для саморегистрации)
│   ├── register_task.py   # Регистрация задачи T-NNN
│   ├── archive_model.py   # Архивация/разархивация модели (--restore)
│   └── migrate_general_to_t001.py  # Одноразовая миграция вердиктов из general → T-001
│
└── openspec/              # Спецификации системы (по факту кода MVP)
    ├── config.yaml
    ├── specs/             # 9 capabilities: benchmark-workflow, task/answer/matchup-management,
    │                      # elo-engine, pairing-algorithm, leaderboard-ui, model-registry, data-storage
    └── changes/archive/   # История принятых изменений (активных changes нет)
```

## Запуск

```bash
# Запустить веб-сервер (leaderboard + рекомендации + ввод вердиктов + добавление модели)
python tools/server.py
# → http://localhost:5000 (при занятом порте — следующий свободный, см. вывод в консоли)
# Windows: start.bat (открывает браузер на localhost:5000)

# Сгенерировать статичный HTML (без сервера, только чтение)
python tools/generate_html.py
# → leaderboard.html

# Пересчитать ELO вручную / проверить свежесть кэша
python tools/elo.py
python tools/elo.py --check

# Юнит-тесты движка
python tools/test_elo.py

# Зарегистрировать модель
python tools/register_model.py --auto --id gpt-5 --name "GPT-5"

# Зарегистрировать задачу
python tools/register_task.py --title "Bug Hunt — NewModule" --project VoiceMind --baseline abc123

# Заархивировать / разархивировать модель
python tools/archive_model.py gpt-5
python tools/archive_model.py --restore gpt-5
```

## Документация

- [docs/architecture.md](docs/architecture.md) — полная архитектура системы
- [docs/elo-mechanics.md](docs/elo-mechanics.md) — математика ELO
- [docs/workflow-guide.md](docs/workflow-guide.md) — пошаговая инструкция
- [docs/judge-prompt.md](docs/judge-prompt.md) — шаблон промпта судьи
- [openspec/specs/](openspec/specs/) — нормативные спеки по факту кода MVP (9 capabilities)
- [AGENTS.md](AGENTS.md) — протокол модели-участницы
