# Benchmark

Репозиторий для сравнения LLM-моделей через **попарные сравнения и ELO-рейтинг**.
Модели отвечают на аналитические задачи (анализ проекта, поиск багов, планирование),
судья сравнивает два ответа и выбирает лучшего, ELO пересчитывается.

## Зачем

Подобрать LLM-модель под свои задачи, опираясь на воспроизводимые сравнения
в реальном коде. Модели соревнуются на одних и тех же задачах, оцениваются
попарно (как в LMSYS Chatbot Arena), рейтинг — по системе ELO.

## Архитектура

**ELO вместо баллов.** Нет рубрикатора с баллами 0–5. Судья сравнивает два
анонимных ответа и выбирает победителя. ELO пересчитывается из всех вердиктов.
Один глобальный рейтинг — кто сильнее в целом.

**Минимальный прогон:** 1 задача + 2 модели + 1 вердикт = валидный ELO.

## Workflow (5 шагов)

```
① Создать задачу          @benchmark-01-gen-task
② Прогнать модели         @benchmark-02-run <model-id>
③ Судья (вручную)         открыть чат с LLM, дать 2 ответа, выбрать победителя
④ Записать вердикт        веб-UI (localhost:5000)
⑤ Leaderboard             веб-UI (localhost:5000) или leaderboard.html
```

Подробная инструкция: **[docs/workflow-guide.md](docs/workflow-guide.md)**

## Skills

| Skill | Что делает |
|-------|-----------|
| `@benchmark-01-gen-task` | Диалоговая генерация задачи |
| `@benchmark-02-run <model>` | Промпт для модели → MD-ответ |

Судья и leaderboard — через локальный веб-сервер, не через skills.

## Структура

```
Benchmark/
├── AGENTS.md              # Протокол участника
├── README.md              # Этот файл
├── models.yaml            # Реестр моделей (status: active/archived)
├── index.json             # Кэш ELO + сводки (генерируется)
├── leaderboard.html       # Статичный экспорт (генерируется)
│
├── tasks/
│   ├── _TEMPLATE.md       # Шаблон задачи
│   └── T-NNN-<slug>/
│       └── task.md        # Описание + критерии + baseline_commit (опц.)
│
├── answers/               # MD-ответы моделей
│   ├── _TEMPLATE.md
│   └── T-NNN/
│       ├── model-a.md     # Анализ + код в блоках
│       └── model-b.md
│
├── matchups/              # Вердикты (попарные сравнения)
│   └── T-NNN/
│       └── NNN.json       # {task, model_a, model_b, winner, date}
│
├── judges/
│   └── _PROMPT.md         # Промпт судьи (если нужен)
│
├── docs/
│   ├── architecture.md    # Полная архитектура
│   ├── elo-mechanics.md   # Математика ELO
│   ├── workflow-guide.md  # Пошаговая инструкция
│   └── judge-prompt.md    # Шаблон промпта судьи
│
├── tools/
│   ├── elo.py             # ELO-движок (пересчёт из matchups)
│   ├── server.py          # Flask: leaderboard + ввод вердиктов
│   ├── generate_html.py   # Статичный leaderboard.html
│   ├── register_model.py  # Регистрация модели
│   └── archive_model.py   # Архивация модели
│
└── openspec/              # Спецификации системы
```

## Запуск

```bash
# Запустить веб-сервер (leaderboard + ввод вердиктов)
python tools/server.py
# → http://localhost:5000

# Сгенерировать статичный HTML (без сервера)
python tools/generate_html.py
# → leaderboard.html

# Пересчитать ELO вручную
python tools/elo.py

# Зарегистрировать модель
python tools/register_model.py --auto --id gpt-5 --name "GPT-5"

# Заархивировать модель
python tools/archive_model.py gpt-5
```

## Документация

- [docs/architecture.md](docs/architecture.md) — полная архитектура системы
- [docs/elo-mechanics.md](docs/elo-mechanics.md) — математика ELO
- [docs/workflow-guide.md](docs/workflow-guide.md) — пошаговая инструкция
- [docs/judge-prompt.md](docs/judge-prompt.md) — шаблон промпта судьи
