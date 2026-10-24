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
                           (или вручную из data/tasks/_TEMPLATE.md)
② Прогнать модели         @benchmark-run-a T-001, @benchmark-run-b T-001
③ Судья                   @benchmark-judge T-001 (или вручную по docs/judge-prompt.md)
                          → только выбор победителя
④ Записать вердикт        координатор: веб-UI localhost:5000 или record_verdict.py
                           с явным --task T-NNN и --model-a/--model-b → событие в data/matchups/journal.jsonl
⑤ Leaderboard             веб-UI (localhost:5000)
```

Подробная инструкция: **[docs/workflow-guide.md](docs/workflow-guide.md)**

## Skills

| Skill | Что делает |
|-------|-----------|
| `@benchmark-run-a T-NNN` | Прогон слота A: читает task.md, изучает код, пишет `data/answers/T-NNN/modelA.md` |
| `@benchmark-run-b T-NNN` | Прогон слота B: то же самое → `data/answers/T-NNN/modelB.md` |
| `@benchmark-judge T-NNN` | Судья: оценивает оба ответа (5 критериев, /50), выбирает победителя; не вызывает `record_verdict.py` |
| `@benchmark-batch-judge [N] [T-NNN]` | Батч-судейство: N пар из очереди, параллельные судьи, автозапись через `record_verdict` (по умолчанию N=10) |

Три основных skill продублированы для трёх сред: `.opencode/skills/`,
`.cursor/skills/`, `.devin/skills/`. `benchmark-batch-judge` — в OpenCode
и в Cursor (скилл; без отдельной `.cursor/commands/`, иначе `/` дублирует
пункт); параллельные судейские сессии, координатор сам пишет вердикты.
Ручное судейство без skill — по шаблону [docs/judge-prompt.md](docs/judge-prompt.md),
запись результата — через веб-сервер.

## Структура

```
Benchmark/
├── AGENTS.md              # Протокол модели-участницы (слоты modelA/modelB)
├── README.md              # Этот файл
├── start.bat              # Запуск сервера в Windows (открывает localhost:5000)
├── stop.bat               # Остановка сервера
├── launch.vbs             # Скрытый запуск сервера (вызывается из start.bat)
│
├── data/                  # Все данные прогонов
│   ├── models.yaml        # Реестр моделей (agent, provider, status: active/archived)
│   ├── judges.yaml        # Резерв пула судей (пока пуст, судейство — skill/вручную)
│   ├── settings.yaml      # Статусы тасок и текущая таска
│   ├── index.json         # Кэш ELO + сводки (генерируется tools/elo.py, коммитится)
│   ├── logs/              # server.log, server.pid (создаются запуском)
│   │
│   ├── tasks/
│   │   ├── _TEMPLATE.md   # Шаблон задачи (создание — register_task.py или вручная копия)
│   │   └── T-NNN-<slug>/
│   │       └── task.md    # Описание + критерии + baseline_commit (опц.)
│   │
│   ├── answers/           # Ответы (не в git): modelA.md / modelB.md (skills) или <model-id>.md (вручную)
│   │   ├── _TEMPLATE.md
│   │   └── T-NNN/
│   │       ├── modelA.md
│   │       └── modelB.md
│   │
│   └── matchups/          # Вердикты (попарные сравнения)
│       └── journal.jsonl  # Append-only журнал: строка = событие (вердикт / tombstone)
│
├── docs/
│   ├── architecture.md    # Полная архитектура
│   ├── elo-mechanics.md   # Математика ELO
│   ├── workflow-guide.md  # Пошаговая инструкция
│   └── judge-prompt.md    # Шаблон промпта судьи (ручное судейство)
│
├── tools/
│   ├── elo.py             # ELO-движок (реплей журнала data/matchups/journal.jsonl → data/index.json) + --check
│   ├── test_elo.py        # Юнит-тесты движка
│   ├── server.py          # Flask: leaderboard + рекомендации пар + ввод вердиктов + управление тасками
│   ├── register_model.py  # Регистрация модели (+ --agent/--provider; --auto для саморегистрации)
│   ├── register_task.py   # Регистрация задачи T-NNN
│   ├── archive_model.py   # Архивация/разархивация модели (--restore)
│   ├── data_cache.py      # Memo-слой сервера: кэш дайджестов и производных данных
│   ├── migrate_journal.py # Одноразовая миграция вердиктов в единый журнал journal.jsonl
│   ├── migrate_general_to_t001.py  # Одноразовая миграция вердиктов из general → T-001
│   ├── export_web.py      # Статический слепок консоли для витрины (read-only, относительные ссылки)
│   └── test_export.py     # Тесты слепка: read-only режим, состав, ссылки, клиентский слой
│
└── openspec/              # Спецификации системы (по факту кода MVP)
    ├── config.yaml
    ├── specs/             # 13 capabilities: benchmark-workflow, task/answer/
    │                      # matchup-management, answer-coverage, elo-engine,
    │                      # pairing-algorithm, leaderboard-ui, console-shell,
    │                      # static-mirror, model-registry, data-storage,
    │                      # run-progress
    └── changes/archive/   # История принятых изменений (активных changes нет)
```

## Запуск

Зависимости описаны в `pyproject.toml`, окружение — `.venv`, создаётся через `uv sync`
(требуется [uv](https://docs.astral.sh/uv/)). Далее команды запускаются через `uv run`
(сам активирует `.venv`) или напрямую `.venv\Scripts\python.exe`.

```bash
# Запустить веб-сервер (leaderboard + рекомендации + ввод вердиктов + добавление модели)
uv run python tools/server.py
# → http://localhost:5000 (при занятом порте — следующий свободный, см. вывод в консоли)
# Windows: start.bat (создаст .venv при первом запуске и откроет браузер на localhost:5000)

# Пересчитать ELO вручную / проверить свежесть кэша
uv run python tools/elo.py
uv run python tools/elo.py --check

# Собрать статический слепок консоли для витрины (полный, только просмотр;
# каталог вывода должен быть пуст, --catalog-depth — глубина от корня витрины)
uv run python tools/export_web.py --out <каталог>

# Юнит-тесты: движок, данные, экспорт, аналитика, миграции, рекомендации
uv run python tools/test_elo.py
uv run python tools/test_data_cache.py
uv run python tools/test_export.py
uv run python tools/test_analytics.py
uv run python tools/test_trends.py
uv run python tools/test_migrate_journal.py
uv run python tools/test_pairing.py

# Нагрузочные бюджеты (по умолчанию множитель 1.5; строгий замер: BENCH_PERF_FACTOR=1)
uv run python tools/test_perf.py

# Зарегистрировать модель (--agent/--provider опциональны)
uv run python tools/register_model.py --auto --id gpt-5 --name "GPT-5"
uv run python tools/register_model.py --id claude-sonnet-4.6 --name "Claude Sonnet 4.6" --version sonnet-4.6 --agent Cursor --provider Anthropic

# Зарегистрировать задачу
uv run python tools/register_task.py --title "Bug Hunt — NewModule" --project VoiceMind --baseline abc123

# Заархивировать / разархивировать модель
uv run python tools/archive_model.py gpt-5
uv run python tools/archive_model.py --restore gpt-5
```

## Документация

- [docs/architecture.md](docs/architecture.md) — полная архитектура системы
- [docs/elo-mechanics.md](docs/elo-mechanics.md) — математика ELO
- [docs/workflow-guide.md](docs/workflow-guide.md) — пошаговая инструкция
- [docs/judge-prompt.md](docs/judge-prompt.md) — шаблон промпта судьи
- [openspec/specs/](openspec/specs/) — нормативные спеки по факту кода MVP (13 capabilities)
- [AGENTS.md](AGENTS.md) — протокол модели-участницы
