# Workflow Guide — пошаговая инструкция

## Минимальный прогон (1 задача, 2 модели, 1 вердикт)

### Шаг 1: Создать задачу

В IDE-чате:
```
@benchmark-01-gen-task
создай задачу: проанализируй модуль WorkoutScoreCalculator в GymProgress,
найди баги и граничные случаи
```

Skill предложит формулировку → "добро" → файл `tasks/T-001-<slug>/task.md` создан.

### Шаг 2: Прогнать модели

Для каждой модели (по одной):

```
@benchmark-02-run claude-sonnet-4.5 T-001
```

Skill готовит промпт → вставляешь в чат с Claude → Claude пишет
`answers/T-001/claude-sonnet-4.5.md` → "готово".

Повторить:
```
@benchmark-02-run gpt-5 T-001
```

### Шаг 3: Судья (вручную)

1. Открыть чат с любой LLM (судья).
2. Скопировать промпт из [judge-prompt.md](judge-prompt.md).
3. Дать судье:
   - `tasks/T-001-<slug>/task.md` (задача)
   - `answers/T-001/claude-sonnet-4.5.md` (ответ 1)
   - `answers/T-001/gpt-5.md` (ответ 2)
4. Судья отвечает: "Победитель: Answer 1 (8/10 vs 6/10). Причина: ..."

### Шаг 4: Записать вердикт

```bash
python tools/server.py
# → http://localhost:5000
```

В браузере:
1. В форме "Записать вердикт":
   - Задача: T-001
   - Модель A: claude-sonnet-4.5
   - Модель B: gpt-5
   - Победитель: Модель A
2. Нажать "Записать"
3. ELO обновится, leaderboard перерисуется

### Шаг 5: Leaderboard

Тот же `localhost:5000` — таблица рейтинга:
```
#  Модель              ELO   W  L  D  Игры
1  Claude Sonnet 4.5   1216  1  0  0  1
2  GPT-5               1184  0  1  0  1
```

Или статичный экспорт:
```bash
python tools/generate_html.py
# → leaderboard.html (открыть в браузере)
```

## Добавление новой модели

1. Зарегистрировать:
   ```bash
   python tools/register_model.py --auto --id gemini-3-pro --name "Gemini 3 Pro"
   ```

2. Прогнать на существующей задаче:
   ```
   @benchmark-02-run gemini-3-pro T-001
   ```

3. Сравнить с уже оценёнными моделями (калибровка):
   - Судья: gemini-3-pro vs claude-sonnet-4.5 → записать вердикт
   - Судья: gemini-3-pro vs gpt-5 → записать вердикт
   - Веб-UI подсказывает следующую пару

## Архивация модели

Если модель устарела (вышла новая версия, отключена в IDE):

```bash
python tools/archive_model.py claude-sonnet-4.5
# → status: archived
# ELO заморожен, новые пары не предлагаются
# В leaderboard: серым, скрыта по умолчанию
```

Разархивировать:
```bash
python tools/archive_model.py --restore claude-sonnet-4.5
```

## Новая версия модели

Когда выходит Claude Sonnet 4.6:
1. Зарегистрировать новый id:
   ```bash
   python tools/register_model.py --auto --id claude-sonnet-4.6 --name "Claude Sonnet 4.6"
   ```
2. Заархивировать старую:
   ```bash
   python tools/archive_model.py claude-sonnet-4.5
   ```
3. Прогнать новую на текущей задаче, сравнить с active-моделями.

## Новая задача

Когда текущая задача исчерпана (все модели прогнаны, достаточно вердиктов):

```
@benchmark-01-gen-task
создай задачу: ...
```

Модели **не сбрасывают ELO** — рейтинг переносится. Новая задача
продолжает обновлять тот же глобальный ELO.
