## Why

Текущая система бенчмарка (4 категории задач, кодописательство, 3 судьи × рубрикатор с баллами, 13 сессий на прогон) — слишком тяжёлая и не отвечает на главный вопрос: **какая модель сильнее для моих реальных задач**. Абсолютные баллы (0–5 по рубрикатору) субъективны и плохо сравнимы между судьями. Попарное сравнение через ELO (как в LMSYS Chatbot Arena) даёт объективный относительный рейтинг, требует меньше сессий и естественнее для выбора «какая модель лучше для меня».

## What Changes

- **BREAKING**: Удалена система 4 категорий (feature/bugfix/refactor/review) → единый формат задач (аналитика + код в MD-ответе)
- **BREAKING**: Удалена система балльного оценивания (рубрикатор 0–5, 3 судьи) → попарное сравнение через ELO
- **BREAKING**: Удалена система прогонов с diff.patch, isolate.py, golden-answer → модели пишут MD-ответ (анализ + код в блоках)
- **BREAKING**: Удалена система skills 00–06 → 2 skills (gen-task, run) + локальный веб-сервер для записи вердиктов
- **NEW**: ELO-движок с адаптивным K-factor (40/32/24 по числу игр)
- **NEW**: Локальный веб-сервер (Flask) — leaderboard + форма записи вердикта + предложение пар
- **NEW**: Хранение: файлы (git-friendly) + index.json (кэш для быстрого поиска)
- **NEW**: Архивация моделей (status: active/archived) — заморозка ELO, скрытие из новых пар, фильтр в UI
- **NEW**: Механизм предложения пар — приоритет: новые модели (калибровка) > близкий ELO > мало голосов
- **NEW**: Судья работает в любом чате с LLM (без skill, без файлов) — промпт-шаблон в docs/
- Удалены: generators/, judges/_RUBRIC.md, anonymization.yaml, leaderboard.md, meta-analysis/, tools/isolate.py, tools/assign_judges.py, tools/aggregate.py, tools/check_stale.py, tools/generate_checklist.py
- Оставлены: models.yaml, tools/register_model.py, .devin/rules/git.md, openspec-скиллы

## Capabilities

### New Capabilities

- `elo-engine`: ELO-движок — пересчёт рейтингов из попарных вердиктов, адаптивный K-factor, история изменений
- `matchup-management`: Запись и хранение попарных вердиктов (задача × модель A × модель B × победитель), веб-UI для ввода
- `pairing-algorithm`: Алгоритм предложения пар для сравнения — приоритизация по новизне модели, близости ELO, недооценённости пары
- `leaderboard-ui`: Веб-интерфейс leaderboard — таблица рейтинга, сортировка, фильтр архивных моделей, статистика W/L/D
- `task-management`: Создание и хранение задач (единый формат, аналитика + код), baseline_commit (опционально)
- `answer-management`: Хранение MD-ответов моделей, шаблон ответа (анализ + код в блоках)
- `model-registry`: Реестр моделей с status (active/archived), саморегистрация, архивация
- `benchmark-workflow`: Сквозной workflow — gen-task → run → судья (вручную) → запись вердикта → leaderboard
- `data-storage`: Гибридное хранение — файлы (source of truth в git) + index.json (генерируемый кэш)

### Modified Capabilities

(нет — все старые спеки удаляются, создаются новые)

## Impact

- **Удаляемые файлы**: tasks/{feature,bugfix,refactor,review}/, tasks/_TEMPLATE/, tasks/_CHECKLIST.md, tasks/_drafts/, runs/, verdicts/, generators/, judges/_RUBRIC.md, meta-analysis/, anonymization.yaml, leaderboard.md, tools/{isolate,assign_judges,aggregate,check_stale,generate_checklist}.py, .devin/skills/benchmark-{00,02,03,04,05,06}-*, openspec/specs/* (старые), docs/workflow-guide.md
- **Новые файлы**: tools/{elo,server,generate_html,archive_model}.py, answers/, matchups/, index.json, leaderboard.html, docs/{architecture,elo-mechanics,workflow-guide,judge-prompt}.md, .devin/skills/benchmark-{01-gen-task,02-run}/, openspec/specs/* (новые)
- **Зависимости**: Flask (локальный веб-сервер), PyYAML (уже используется)
- **Git**: index.json коммитится (быстрый просмотр без сервера); answers/ и matchups/ — source of truth
- **Skills**: 6 → 2 (gen-task, run); судья и leaderboard — через веб-сервер, не через skills
