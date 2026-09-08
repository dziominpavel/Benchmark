# Tasks: progress-status-bar

## 1. Данные для шаблона

- [x] 1.1 В `leaderboard()` (`tools/server.py`) заменить сборку `progress_label` на передачу структурного покрытия: `coverage` (`filled`, `total`, `percent`) и `remaining = total - filled`; проверка — `python -c "import server"` (или компиляция `python -m py_compile tools/server.py`) проходит без ошибок

## 2. Вёрстка статус-бара

- [x] 2.1 В блок `CSS` добавить стили плашки: `.progress-card`, `.progress-head`, `.progress-title`, `.progress-pct`, `.progress-track`, `.progress-fill` (градиент indigo→emerald, страйпы с `@keyframes`, `transition: width`, `prefers-reduced-motion`), модификаторы `.progress-card--empty` (приглушённая, `—`) и `.progress-card--done` (заливка emerald); проверка — классы присутствуют в `CSS`
- [x] 2.2 В `INDEX_TEMPLATE` после блока алертов и перед `<div class="controls">` добавить разметку плашки: заголовок «Прогресс прогона», процент, трек с `role="progressbar"` и aria-атрибутами, подписи «закрыто X из Y» / «осталось N», состояния `None` (`—`, пустой бар) и 100% («Все пары закрыты»); проверка — главная рендерится, в HTML есть `role="progressbar"`
- [x] 2.3 Из `<div class="stats">` убрать фрагмент «Прогресс: {{ progress_label }}» (остаются «Моделей», «Вердиктов», «Обновлено»); проверка — в строке статистики нет слова «Прогресс»

## 3. Проверка

- [x] 3.1 Запустить `python tools/server.py` (или существующий способ запуска из start.bat) и открыть `/`: плашка показывает процент, заполненный бар, «закрыто X из Y» и «осталось N», соответствующие `get_coverage()`; строка статистики без «Прогресс»
- [x] 3.2 Прогнать `openspec validate progress-status-bar --strict` — без ошибок
