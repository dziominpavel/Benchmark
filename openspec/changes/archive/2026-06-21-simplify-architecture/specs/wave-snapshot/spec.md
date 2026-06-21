## REMOVED Requirements

### Requirement: Git-тег волны в проекте
**Reason**: Концепция wave устранена. Задача содержит `baseline_commit` в front matter, участник делает `git checkout <commit>`. Никаких git-тегов в чужих проектах.
**Migration**: Удалить `snapshots/` папку. Удалить git-теги `benchmark-wave-NN` из проектов (опционально). Использовать `baseline_commit` в `task.md`.

### Requirement: Снапшот проекта на волну
**Reason**: Снапшоты больше не нужны. `baseline_commit` в `task.md` заменяет снапшот.
**Migration**: Удалить `snapshots/` папку и все `*.yaml` файлы в ней.

### Requirement: Состав участников волны
**Reason**: Нет волн. `models.yaml` — глобальный реестр. Участники не привязаны к волне.
**Migration**: Удалить `waves/<wave>/participants.yaml`. Использовать `models.yaml` как источник участников.

### Requirement: Состав судей волны
**Reason**: Нет волн. `judges.yaml` — глобальный pool судей.
**Migration**: Удалить `waves/<wave>/judges.yaml`. Создать `judges.yaml` в корне репозитория.

### Requirement: Карта анонимизации волны
**Reason**: Нет волн. Анонимизация глобальная, `anonymization.yaml` в корне.
**Migration**: Удалить `waves/<wave>/anonymization.yaml`. Создать `anonymization.yaml` в корне.

### Requirement: Сводный отчёт волны с ролями
**Reason**: Нет волн. Отчёт — кумулятивный `leaderboard.md`, не привязан к волне.
**Migration**: Удалить `waves/<wave>/summary.md`. Использовать `leaderboard.md` как сводный отчёт.
