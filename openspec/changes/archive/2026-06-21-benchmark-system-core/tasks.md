## 1. Структура папок и шаблоны

- [x] 1.1 Создать папки `judges/`, `verdicts/`, `tasks/_drafts/`, `meta-analysis/`, `generators/`
- [x] 1.2 Создать `judges/_PROMPT.md` — промпт для судьи (что получает, как оценивает, формат вердикта)
- [x] 1.3 Создать `judges/_RUBRIC.md` — детальный рубрикатор с баллами 0–5 и индикаторами уровня (7 пунктов для feature/bugfix/refactor + 6 пунктов для review)
- [x] 1.4 Создать `generators/_PROMPT.md` — промпт для модели-генератора (тема → черновик, не решает задачу)
- [x] 1.5 Создать `tasks/_drafts/_TEMPLATE.md` — шаблон черновика генератора
- [x] 1.6 Обновить `tasks/_TEMPLATE.md` — добавить поле `projects` (массив) в front matter для multi-project задач
- [x] 1.7 Обновить `tasks/_CHECKLIST.md` — убрать баллы, оставить только критерии (двухслойный рубрикатор: чек-лист без баллов для участника)
- [x] 1.8 Создать шаблоны `waves/<wave>/participants.yaml`, `judges.yaml`, `anonymization.yaml` (в `waves/_TEMPLATES/`)
- [x] 1.9 Создать `verdicts/_TEMPLATE.md` — шаблон вердикта судьи (балл + обоснование по каждому пункту)
- [x] 1.10 Создать `tasks/<cat>/<id>/golden-answer/_TEMPLATE.md` — шаблон golden answer
- [x] 1.11 Обновить `waves/<wave>/summary.md` — добавить секции: состав волны с ролями (участники/судьи/генераторы/resolver'ы), привязка ролей к задачам, качество судей, спорные прогоны, рекомендации для следующей волны

## 2. Скрипты

- [x] 2.1 Создать `tools/register_model.py` — добавление модели в `models.yaml` по CLI (--id, --name, --provider, --version, --released). Проверка уникальности id.
- [x] 2.2 Создать `tools/isolate.py` — команды `hide`/`restore` для прогонов и `hide-verdicts`/`restore-verdicts` для вердиктов. Перемещение в `.isolation-stash/` и `.isolation-stash-verdicts/`.
- [x] 2.3 Создать `tools/assign_judges.py` — распределение 3 судей по прогонам с проверкой конфликта интересов (судья ≠ участник). Создание `anonymization.yaml` и анонимизированных копий прогонов.
- [x] 2.4 Расширить `tools/aggregate.py` — чтение `verdicts/` вместо `runs/`, медиана судей, деанонимизация через `anonymization.yaml`, пометка `disputed` при разбросе > 2, разбивка по категориям и волнам, вычисление качества судей (средний разброс с другими), генерация карты назначений (задача × участник × 3 судьи × оценки × медиана)

## 3. Обновление AGENTS.md

- [x] 3.1 Добавить раздел «Роли моделей» (генератор, resolver, участник, судья) с правилом запрета совмещения ролей в одном прогоне
- [x] 3.2 Обновить «Перед началом прогона» — добавить шаг `isolate.py hide`, проверку в `participants.yaml`
- [x] 3.3 Обновить «Создание файла прогона» — новый путь `runs/<wave>/<model-id>/<task-id>/{run.md, diff.patch}`, секция «Вопросы по задаче»
- [x] 3.4 Добавить раздел «Очистка проекта» — `git checkout . && git clean -fd` после прогона
- [x] 3.5 Добавить раздел «Судья» — протокол для модели-судьи: что получает, как оценивает, формат вердикта с обоснованием
- [x] 3.6 Добавить раздел «Генератор» — протокол для модели-генератора: тема → черновик в `_drafts/<gen>/`, не знает ответа
- [x] 3.7 Добавить раздел «Resolver» — протокол: решает до участников, golden answer как baseline, оценка сложности

## 4. Обновление README.md

- [x] 4.1 Обновить диаграмму структуры папок (добавить `judges/`, `verdicts/`, `generators/`, `tasks/_drafts/`, `meta-analysis/`, вложенную структуру `runs/`)
- [x] 4.2 Обновить «Как это работает» — 6 фаз волны (подготовка → генерация → resolve → выполнение → оценка → агрегация) + мета-анализ
- [x] 4.3 Добавить раздел «Роли моделей» с таблицей (генератор, resolver, участник, судья)
- [x] 4.4 Обновить «Быстрый старт» — `register_model.py`, `isolate.py`, `assign_judges.py`, `aggregate.py`
- [x] 4.5 Добавить раздел «Workflow волны» — подробное пошаговое руководство с примером 3 моделей (из design.md), сводная таблица сессий на волну

## 5. Обновление .gitignore

- [x] 5.1 Добавить `.isolation-stash/` и `.isolation-stash-verdicts/`
- [x] 5.2 Добавить `tasks/_drafts/` (черновики генераторов не коммитятся)

## 6. Миграция существующей структуры

- [x] 6.1 Удалить старый `runs/_TEMPLATE.md` (плоский формат) и создать новый под вложенную структуру `runs/<wave>/<model-id>/<task-id>/run.md`
- [x] 6.2 Удалить `runs/wave-01-2026Q3/.gitkeep` (папка будет содержать подпапки моделей)
- [x] 6.3 Обновить `snapshots/_TEMPLATE.yaml` — добавить поля `participants_ref`, `judges_ref` (ссылки на `waves/<wave>/`)
- [x] 6.4 Очистить `models.yaml` от примеров в комментариях (теперь заполняется через `register_model.py`)

## 7. Проверка

- [x] 7.1 `openspec validate --all` проходит без ошибок
- [x] 7.2 `python tools/aggregate.py` работает на пустых `verdicts/` (генерирует «Нет вердиктов»)
- [x] 7.3 `python tools/register_model.py --id test --name Test --provider Test --version 1` добавляет запись в `models.yaml`
- [x] 7.4 `python tools/isolate.py hide --wave test --except test-model` перемещает чужие папки (синтетический тест)
- [x] 7.5 `python tools/isolate.py restore` возвращает перемещённые папки
- [x] 7.6 `python tools/assign_judges.py --wave test` назначает 3 судей без конфликта интересов (синтетический тест)
- [x] 7.7 Все шаблоны (`_TEMPLATE.md`, `_PROMPT.md`, `_RUBRIC.md`) соответствуют спекам
