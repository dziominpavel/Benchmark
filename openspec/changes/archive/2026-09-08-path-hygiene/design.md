## Context

См. `proposal.md` (Why). Факты: все скрипты `tools/*.py` уже импортируют из `elo.py`, обратных импортов (`elo.py` → соседи) нет — значит, `elo.py` годится как единственное место объявления путей. Найденные дубли: `elo.py:554` (`REPO_ROOT / "models.yaml"`), `elo.py:599-601` (локальные `tasks_dir/answers_dir/matchups_dir`), `server.py:54-56` (собственные `ANSWERS_DIR/MATCHUPS_DIR/TASKS_DIR`), `server.py:68,272,1599` (`REPO_ROOT / "index.json"` / `"models.yaml"`), собственные `REPO_ROOT`/`MODELS_PATH`/`INDEX_PATH` в `register_model.py`, `archive_model.py`, `test_pairing.py`.

## Goals / Non-Goals

**Goals:**
- После change строковый литерал пути к данным существует ровно в одном месте — в блоке констант `elo.py`.
- Любой модуль получает пути только импортом из `elo.py`.

**Non-Goals:**
- Скрипты-миграции (`migrate_general_to_t001.py`, `migrate_recorded_at.py`) не трогаем: это замороженные одноразовые скрипты, правки в них — риск без выгоды.
- Значения путей не меняются (это задача шага 2, `data-dir-move`).

## Decisions

1. **Добавить недостающую константу `MODELS_PATH = REPO_ROOT / "models.yaml"` в `elo.py`.**
   Почему: `models.yaml` сейчас собирается инлайн в трёх местах, а константы под него нет. Альтернатива — оставить инлайн только для models (меньше дифф), отвергнута: именно `models.yaml` переедет в шаге 2, и пропущенный инлайн = рассинхрон.
2. **Заменить все дубли импортом, а не локальными копиями.**
   `elo.py:599-601` → использовать модульные `TASKS_DIR/ANSWERS_DIR/MATCHUPS_DIR`; `server.py:54-56` → удалить, расширить существующий `from elo import (...)` блок; `server.py:68,272,1599` → `INDEX_PATH` / `MODELS_PATH`; `register_model.py`, `archive_model.py`, `test_pairing.py` → импортировать `REPO_ROOT`/`MODELS_PATH`/`INDEX_PATH` из `elo.py` вместо собственных определений.
   Почему импорт, а не «каждый модуль определяет своё»: одна точка правки в шаге 2 вместо ~6 файлов.
3. **Проверка — текстовым grep, а не ревью глазами.**
   После правок `grep` по `tools/*.py` (исключая `migrate_*`) не должен находить литералы `"tasks"`, `"answers"`, `"matchups"`, `"index.json"`, `"models.yaml"`, `"settings.yaml"` вне блока констант `elo.py`.

## Risks / Trade-offs

- [Risk] Пропущенный инлайн в редко выполняемой ветке (обработчик формы) → шаг 2 уронит только эту ветку. Mitigation: grep-чеклист + ручной прогон основных страниц сервера после правок.
- [Risk] `test_pairing.py` сам находит `archive_model.py` через `REPO_ROOT` — замена константы на импорт не должна сломать `sys.path` манипуляции. Mitigation: прогнать оба теста до и после, сравнить вывод.

## Migration Plan

Не требуется (значения путей не меняются, поведение идентично). Откат — `git checkout -- tools/`.
