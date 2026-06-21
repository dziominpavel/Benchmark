---
# Вердикт судьи. Создаётся в verdicts/<task-id>/<participant-anon-id>/<judge-id>.md
# participant-anon-id = "Участник-X" (анонимизированный, НЕ реальный model_id)
# judge-id = реальный model_id судьи

task_id: F-NNN-<slug>
participant: "Участник X"  # анонимизированный (НЕ реальный model_id)
judge_id: <model-id судьи>
date: 2026-06-21

# Баллы по рубрикатору (0–5 или N/A)
# Для feature/bugfix/refactor — 7 пунктов
# Для review — 6 пунктов (review-рубрикатор)
score_correctness: 4
score_build_tests: 5
score_project_rules: 4
score_code_quality: 4
score_architecture: 5
score_completeness: 4
score_notes: 4

# Для review-задач (закомментируй неиспользуемые):
# score_depth: 4
# score_justification: 4
# score_completeness_review: 4
# score_specificity: 4
# score_prioritization: 4
# score_style: 4

total_score: 31
max_score: 35
normalized_score: 4.43

# Применял ли судья patch и запускал тесты сам?
patch_applied: yes
tests_run_by_judge: yes

# Находки вне golden (подтверждённые судьёй) — только для bugfix
out_of_golden:
  - "Описание находки 1 — подтверждено, реальный баг"
  - "Описание находки 2 — подтверждено"
---

# Вердикт: <task-id> / Участник X

## Корректность: 4/5
Обоснование: Участник нашёл 4 из 5 багов из golden answer. Пропущен критичный баг
с timezone в ReminderParser (строка 142, `Calendar.getInstance()` без явной TZ).
Найденные баги реальные, ложных срабатываний нет. Один баг вне golden
подтверждён (см. out_of_golden) — зачтён.

## Сборка и тесты: 5/5
Обоснование: Применил diff.patch к проекту на baseline_commit.
`./gradlew assembleDebug` — успешно. `./gradlew test` — все 42 теста прошли.
OpenSpec validate --all —passed.

## Соблюдение правил проекта: 4/5
Обоснование: Правила AGENTS.md в основном соблюдены. Один ViewModel не нарушен.
Токены дизайн-системы использованы. Мелкое нарушение: в одном месте
использован `RoundedCornerShape(8.dp)` вместо `CardShape` (файл FooScreen.kt, строка 67).

## Качество кода: 4/5
Обоснование: Код идиоматичный, корутины и StateFlow использованы правильно.
Мелкое замечание: избыточная вложенность в `when`-блоке (BarScreen.kt, строки 30–45).

## Архитектура: 5/5
Обоснование: Изменения локализованы в правильных пакетах. Слой данных не нарушен.
Новый код в `data/parse/` — соответствует структуре проекта.

## Полнота и самостоятельность: 4/5
Обоснование: Задача доведена до конца. Clarifying questions — 2 точных вопроса
по неоднозначностям в спеке (timezone handling, fallback STT coverage).
Разумные предположения сделаны. Одно TODO без обоснования (BarScreen.kt, строка 120).

## Заметки и объяснения: 4/5
Обоснование: Заметки полезные, trade-offs названы (выбрал Epley формулу вместо
Brzycki, обосновал). Что бы улучшила — конкретно. Не хватает описания препятствий.

## Итог

- total_score: 31/35
- normalized_score: 4.43
- Сильные стороны: корректность, архитектура, сборка
- Слабые стороны: мелкие нарушения дизайн-системы, одно TODO без обоснования
