---
name: benchmark-02-resolve
description: "Шаг 2 из 5. Golden answer для bugfix-задачи. Готовит промпт для resolver-модели и проверяет результат. Используй после @benchmark-01-gen-task для bugfix задач. Дальше: @benchmark-03-run."
license: MIT
---

Golden answer для bugfix-задачи. Resolver решает задачу до участников,
создаёт эталонный ответ для судьи.

**Когда использовать:** после генерации bugfix-задачи (B-NNN).
Для feature/refactor/review — этот шаг НЕ нужен.

## Шаги

1. **Прочитай задачу:**
   - `tasks/bugfix/<task-id>/task.md`
   - Извлеки `baseline_commit`, `project`, описание

2. **Проверь что golden-answer ещё нет:**
   - Если `tasks/bugfix/<task-id>/golden-answer/answer.md` существует —
     сообщи "уже resolved" и остановись

3. **Подготовь промпт для resolver-модели:**
   ```
   Ты — resolver. Прочитай AGENTS.md → раздел "Resolver".

   Реши задачу <task-id> в C:/projects/<Project>
   на baseline_commit <hash> (из tasks/bugfix/<task-id>/task.md).

   Сохрани:
     tasks/bugfix/<task-id>/golden-answer/answer.md (по шаблону)
     tasks/bugfix/<task-id>/golden-answer/diff.patch (git diff)

   В answer.md:
   - Что сделано — какие файлы изменены
   - Список находок (для bugfix) — файл:строка, описание, критичность
   - Сложность (1-3) и время в минутах

   После: git checkout . && git clean -fd
   ```

4. **Покажи промпт пользователю:**
   ```
   ПРОМПТ ДЛЯ RESOLVER (скопируй в новый чат с любой моделью):

   <промпт>

   Когда resolver закончит — напиши "готово".
   ```

5. **Жди подтверждения "готово" от пользователя.**

6. **Проверь результат:**
   - `tasks/bugfix/<task-id>/golden-answer/answer.md` существует?
   - `tasks/bugfix/<task-id>/golden-answer/diff.patch` существует?
   - Если нет — сообщи что не хватает, попроси повторить

7. **Сообщи:**
   ```
   ✓ <task-id> resolved (golden answer готов)
   Дальше: @benchmark-03-run <model-id>
   ```

## Правила

- **Только для bugfix** — для feature/refactor/review этот шаг пропускается
- **Resolver ≠ участник этой же задачи** — если не уверен, выбери модель
  не из будущих участников (golden-answer скрыт изоляцией, но лучше перестраховаться)
- **Не решай задачу сам** — ты только готовишь промпт и проверяешь результат
