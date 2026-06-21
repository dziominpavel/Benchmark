---
# Front matter прогона. Модель-участник заполняет после выполнения задачи.
# Имя файла: runs/<wave>/<task-id>__<model-id>.md

task_id: F-NNN-<slug>
model_id: <slug из models.yaml>
wave: wave-NN-YYYYQn
date: 2026-06-21
status: completed  # completed | partial | failed | blocked

# Результаты проверок: yes | no | unknown
build_pass: yes
tests_pass: yes
openspec_validate_pass: yes  # или N/A если проект без OpenSpec

# Баллы по чек-листу tasks/_CHECKLIST.md (0–5 или N/A)
score_correctness: 5
score_build_tests: 5
score_project_rules: 4
score_code_quality: 4
score_architecture: 5
score_completeness: 4
score_notes: 4

# Итог = сумма применимых баллов
total_score: 31
# Максимальный возможный = 5 × число применимых пунктов
max_score: 35
# Нормализованный средний (total / max × 5) — для leaderboard
normalized_score: 4.43

# Ссылка на diff/коммит (если есть). Для review — N/A.
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
