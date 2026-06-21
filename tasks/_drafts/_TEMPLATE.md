---
# Черновик задачи от генератора.
# Этот файл пишет модель-генератор в tasks/_drafts/<generator-id>/<task-id>.md
# Пользователь потом выбирает лучший черновик (или сливает) → tasks/<cat>/<task-id>/task.md

id: <PREFIX>-NNN-<slug>
title: "<Краткое название задачи>"
category: feature  # feature | bugfix | refactor | review
difficulty: 2      # 1 (простая) | 2 (средняя) | 3 (сложная)
project: voicemind # gymprogress | voicemind | wishlot | или projects: [a, b]
estimated_minutes: 60
tags: [compose, ui]
generator: <generator-id>  # кто написал этот черновик
---

# <Краткое название задачи>

## Контекст

Опиши, в каком состоянии находится проект/модуль.
Сошлись на спеки/docs проекта:
- `C:/projects/<Project>/AGENTS.md`
- `C:/projects/<Project>/docs/<file>.md`
- `C:/projects/<Project>/openspec/specs/<capability>/spec.md`

## Постановка

Чётко и однозначно: что нужно сделать.
Для bugfix — модуль и количество багов (НЕ перечисляй конкретные баги).
Для review — что разобрать и что вернуть.

## Критерии приёмки

- [ ] Критерий 1 (проверимый)
- [ ] Критерий 2
- [ ] Критерий 3

## Ограничения

Что НЕ нужно делать.

## Подсказки (опц.)

Наводки, ссылки на похожие места в коде.
