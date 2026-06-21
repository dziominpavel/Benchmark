---
# Front matter прогона. Модель-участник заполняет после выполнения задачи.
# Путь: runs/<task-id>/<model-id>/run.md
# + runs/<task-id>/<model-id>/diff.patch (для feature/bugfix/refactor)

task_id: F-NNN-<slug>
model_id: <slug из models.yaml>
date: 2026-06-21
status: completed  # completed | partial | failed | blocked

# Результаты проверок: yes | no | unknown
build_pass: yes
tests_pass: yes
openspec_validate_pass: yes  # или N/A если проект без OpenSpec

# Баллы самооценки по чек-листу (0–5 или N/A)
score_correctness: 5
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

diff_ref: "C:/projects/<Project> @ commit <hash>"
---

# Прогон: <task-id> / <model-id>

## Что сделано

Кратко: какие файлы изменены, что реализовано. Без воды.

## Что получилось хорошо

- ...

## Что не получилось / проблемы

- ...

## Trade-offs и решения

- ...

## Что бы я улучшила

- ...

## Препятствия

- ...

## Вопросы по задаче

(Clarifying questions — если были неоднозначности. Никто не ответит,
но судья оценит качество вопросов.)

- Неясно, должен ли парсер обрабатывать "через полчаса" — предполагаю да, реализую.
- Нужно ли покрывать тестами fallback STT? Предполагаю нет, MVP.
