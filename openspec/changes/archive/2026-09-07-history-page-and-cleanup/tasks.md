## 1. Роут `/history` и шаблон

- [x] 1.1 Добавить в `tools/server.py` роут `/history` с пагинацией по 20 записей и передачей `elo_history` в шаблон; убедиться, что страница открывается по `http://localhost:5000/history`.
- [x] 1.2 Добавить `HISTORY_TEMPLATE` в `tools/server.py` с заголовком, ссылкой «Назад», фильтром `model`, чекбоксом `include_inactive`, списком истории и пагинацией; убедиться, что страница рендерится без ошибок.
- [x] 1.3 Реализовать серверную фильтрацию: при `model=` оставлять записи, где `model_a_id` или `model_b_id` равны выбранному id; убедиться, что при `model=devin-swe-1-7-max` показываются только матчи с этой моделью.
- [x] 1.4 Реализовать чекбокс `include_inactive`: когда он включён, в выпадайку добавляются модели со статусом `archived`; убедиться, что по умолчанию (выключен) в списке только `active`.
- [x] 1.5 Сохранять `model` и `include_inactive` в URL пагинации и при сабмите формы; убедиться, что переход по страницам не сбрасывает фильтр.
- [x] 1.6 Добавить в `HISTORY_TEMPLATE` пустое состояние, когда `elo_history` пуст; убедиться, что отображается «Нет истории».

## 2. Главная страница

- [x] 2.1 Убрать блок `<details class="history-details">` из `INDEX_TEMPLATE` в `tools/server.py`; убедиться, что на главной (`/`) история не отображается.
- [x] 2.2 Добавить в шапку главной страницы кнопку/ссылку «История» рядом с «Настройками»; убедиться, что клик ведёт на `/history`.

## 3. Удаление статичного экспорта

- [x] 3.1 Удалить файл `tools/generate_html.py`; убедиться, что `python tools/generate_html.py` больше не выполняется.
- [x] 3.2 Удалить строку `leaderboard.html` из `.gitignore`; убедиться, что в `.gitignore` нет упоминания `leaderboard.html`.
- [x] 3.3 Вычистить упоминания `leaderboard.html` и `generate_html.py` из `README.md`; убедиться, что `grep leaderboard.html README.md` ничего не находит.
- [x] 3.4 Вычистить упоминания `leaderboard.html` и `generate_html.py` из `docs/workflow-guide.md`; убедиться, что `grep leaderboard.html docs/workflow-guide.md` ничего не находит.
- [x] 3.5 Удалить сгенерированный `leaderboard.html` в корне репозитория, если он есть; убедиться, что `ls leaderboard.html` возвращает «не найден».
- [x] 3.6 (доп.) Убрать неиспользуемую `render_history_html` из `tools/render_helpers.py`.

## 4. Спеки и валидация

- [x] 4.1 Убедиться, что delta-спека `openspec/changes/history-page-and-cleanup/specs/leaderboard-ui/spec.md` и `data-storage/spec.md` оформлены корректно.
- [x] 4.2 Запустить `openspec validate --all` и убедиться, что ошибок нет.
- [x] 4.3 При архивации change синхронизировать основные спеки `openspec/specs/leaderboard-ui/spec.md` и `openspec/specs/data-storage/spec.md`; убедиться, что в Purpose не осталось `leaderboard.html`.

## 5. Ручное тестирование

- [x] 5.1 Запустить `python tools/server.py`, открыть главную, нажать «История» и убедиться, что открывается `/history` с пагинацией.
- [x] 5.2 Выбрать модель в выпадайке и убедиться, что показываются только её матчи; URL содержит `model=`.
- [x] 5.3 Включить чекбокс, выбрать archived-модель (например, `devin-kimi-k3-max`) и убедиться, что фильтр работает.
- [x] 5.4 Перейти на вторую страницу истории и убедиться, что пагинация сохраняет фильтр.
