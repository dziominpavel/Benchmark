---
task: T-001
model: modelA
date: 2026-09-05
---

# Ответ на задачу T-001

## Анализ

Рассмотрены два файла:
- `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt` (80 строк) — вычисление ближайшего срабатывания для DAILY/WEEKDAYS/WEEKENDS/WEEKLY/MONTHLY.
- `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt` (69 строк) — модель правила, `toLabel()`, `serialize()`, `parse()`.

Особое внимание уделено: контракту «строго после `fromMillis`», граничным значениям `interval` (0, отрицательные), `dayOfWeek`/`dayOfMonth` вне диапазона, переходам через месяц (31 → 28 февраля), DST-переходам (spring-forward gap, fall-back overlap), сериализации/парсингу, согласованности `toLabel`/`serialize`/`parse`.

Найдено **11 находок** (8 багов + 3 замечания низкого уровня). Главные проблемы: отсутствие валидации `interval` (0 и отрицательные значения нарушают контракт «строго после»), DST-проблема в `withSameTime`, неконсистентность `toLabel` для `null`-полей, отсутствие валидации в `parse()`.

---

## Находки

### 1. `interval = 0` нарушает контракт «строго после `fromMillis`» во всех интервальных типах

**Файл:** `RecurrenceCalculator.kt:29-31` (`nextDaily`), `:49-59` (`nextWeekly`), `:61-72` (`nextMonthly`)
**Критичность:** критичный

**Описание:** Контракт `nextOccurrence` (строка 10) обещает «ближайшее будущее срабатывание **строго после** `fromMillis`». При `interval = 0`:

- `nextDaily`: `from.plusDays(0)` = `from`, `withSameTime(from)` = `from`. Возвращает `from` — не строго после.
- `nextWeekly` при `dayOfWeek == from.dayOfWeek`: `candidate = from.plusWeeks(0) = from`, `delta = 0`, `candidate = from`, `!isAfter(from)` = true, `candidate = from.plusWeeks(0) = from`. Возвращает `from`.
- `nextMonthly` при `dayOfMonth == from.dayOfMonth`: `candidate = from.plusMonths(0) = from`, `withDayOfMonth(target) = from`, `!isAfter(from)` = true, retry `plusMonths(0)` = `from`. Возвращает `from`.

`RecurrenceRule` не валидирует `interval` ни в конструкторе, ни в `parse()` — `interval = 0` легко попадает в систему (например, из повреждённой сериализации `DAILY:0`).

**Пример:**
```
rule = RecurrenceRule(DAILY, interval = 0)
fromMillis = 2026-09-05T09:00 (понедельник)
nextOccurrence → 2026-09-05T09:00 (та же дата, не строго после)
```
Reminder перезапланируется на то же мгновение → бесконечный цикл перепланирования / немедленный повторный fire.

**Исправление:**

В `RecurrenceRule` добавить валидацию в `init` (или в `parse`):

```kotlin
data class RecurrenceRule(
    val type: RecurrenceType,
    val interval: Int = 1,
    val dayOfWeek: Int? = null,
    val dayOfMonth: Int? = null,
) {
    init {
        require(interval >= 1) { "interval must be >= 1, got $interval" }
        dayOfWeek?.let { require(it in 1..7) { "dayOfWeek must be 1..7, got $it" } }
        dayOfMonth?.let { require(it in 1..31) { "dayOfMonth must be 1..31, got $it" } }
    }
    // ...
}
```

А в `parse()` — отбрасывать невалидные значения вместо тихого `?: 1`:

```kotlin
fun parse(serialized: String?): RecurrenceRule? {
    if (serialized.isNullOrBlank()) return null
    val parts = serialized.split(":")
    return try {
        when (parts[0]) {
            "DAILY" -> RecurrenceRule(
                type = RecurrenceType.DAILY,
                interval = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it >= 1 } ?: 1,
            )
            "WEEKLY" -> RecurrenceRule(
                type = RecurrenceType.WEEKLY,
                dayOfWeek = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it in 1..7 } ?: 1,
                interval = parts.getOrNull(2)?.toIntOrNull()?.takeIf { it >= 1 } ?: 1,
            )
            "MONTHLY" -> RecurrenceRule(
                type = RecurrenceType.MONTHLY,
                dayOfMonth = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it in 1..31 } ?: 1,
                interval = parts.getOrNull(2)?.toIntOrNull()?.takeIf { it >= 1 } ?: 1,
            )
            "WEEKDAYS" -> RecurrenceRule(type = RecurrenceType.WEEKDAYS)
            "WEEKENDS" -> RecurrenceRule(type = RecurrenceType.WEEKENDS)
            else -> null
        }
    } catch (e: IllegalArgumentException) {
        null
    }
}
```

Дополнительно — защитный `coerceAtLeast(1)` в калькуляторе как defence-in-depth:

```kotlin
private fun nextDaily(from: ZonedDateTime, interval: Int): ZonedDateTime {
    val safeInterval = interval.coerceAtLeast(1).toLong()
    return from.plusDays(safeInterval).withSameTime(from)
}
```

---

### 2. Отрицательный `interval` возвращает дату в прошлом

**Файл:** `RecurrenceCalculator.kt:30, 50, 62`
**Критичность:** критичный

**Описание:** `interval = -1` (или любое отрицательное) → `plusDays(-1)` / `plusWeeks(-1)` / `plusMonths(-1)` сдвигают кандидата в прошлое. В `nextWeekly` и `nextMonthly` есть проверка `if (!candidate.isAfter(from))`, но она только **один раз** добавляет `interval` (тоже отрицательный) — усугубляет ситуацию, а не исправляет. Возврат прошлого `fireAt` приводит к немедленному срабатыванию alarm’а и перепланированию в прошлое → цикл.

**Пример:**
```
rule = RecurrenceRule(WEEKLY, dayOfWeek = 2, interval = -1)
from = 2026-09-08 (вторник)
candidate = from.plusWeeks(-1) = 2026-09-01 (прошлый вторник)
delta = 0 → candidate = 2026-09-01
!isAfter(from) → true → candidate = 2026-09-01.plusWeeks(-1) = 2026-08-25
return 2026-08-25 (далеко в прошлом)
```

**Исправление:** та же валидация `interval >= 1` в `RecurrenceRule` (см. находку 1) + `coerceAtLeast(1)` в калькуляторе.

---

### 3. DST spring-forward: `withSameTime` создаёт невалидное время

**Файл:** `RecurrenceCalculator.kt:74-79` (`withSameTime`)
**Критичность:** средний

**Описание:** `withSameTime` делает `withHour(h).withMinute(m).withSecond(s).withNano(n)`. В день перехода на летнее время (spring forward, например 2:00 → 3:00 в Европе) время 2:30 не существует. `ZonedDateTime.withHour(2)` на эту дату автоматически сдвигается до 3:30 — напоминание сработает на час позже. Это касается **всех** путей: `nextDaily`, `nextWeekdays`, `nextWeekends`, `nextWeekly`, `nextMonthly` — все вызывают `withSameTime`.

Дополнительно, при fall-back (overlap) 2:30 существует дважды — `withHour` сохраняет текущий offset, что может дать не то повторение, которое ожидалось (но это менее критично).

**Пример:**
```
zone = Europe/Moscow (раньше был DST; для Европы/Берлина актуально)
from = 2026-03-29T01:30 (воскресенье, в 02:00 → 03:00)
rule = DAILY, interval = 1
candidate = 2026-03-30 + withSameTime(01:30) = 2026-03-30T01:30 (OK)
но если from = 2026-03-29T02:30 (уже не существует) — Java поднимет до 03:30
```
Более реальный сценарий: пользователь ставит «каждый день в 2:30», и в день spring-forward напоминание срабатывает в 3:30.

**Исправление:** использовать `with(LocalTime)` через `ZonedDateTime.with(other.toLocalTime())` не помогает — поведение то же. Корректное решение — явно проверять gap и сдвигать на следующее валидное время:

```kotlin
private fun ZonedDateTime.withSameTime(other: ZonedDateTime): ZonedDateTime {
    var result = withHour(other.hour)
        .withMinute(other.minute)
        .withSecond(other.second)
        .withNano(other.nano)
    // Защита от DST gap: если время было сдвинуто автоматически, вернуть следующий валидный момент.
    if (result.hour != other.hour || result.minute != other.minute) {
        // Java уже сдвинула вперёд до валидного времени — оставляем как есть,
        // но логируем/помечаем, что время скорректировано.
        // Альтернатива — перенести на следующий день, если важна строгая точность.
    }
    return result
}
```

Более чистый вариант — хранить время как `LocalTime` и применять через `atTime` с `strict`-проверкой через `zone.rules.getValidOffset`, но это выходит за рамки точечного исправления. Минимально: документировать поведение и гарантировать, что `isAfter(from)` всё ещё выполняется (он выполняется, т.к. дата больше).

---

### 4. `toLabel()` формирует некорректные строки для `null`-полей

**Файл:** `RecurrenceRule.kt:23-30`
**Критичность:** средний

**Описание:**
- `WEEKLY` с `dayOfWeek = null`: `when (null) { ... }` попадает в `else -> ""`, итог — `"еженедельно ()"` (пустые скобки).
- `MONTHLY` с `dayOfMonth = null`: строка 30 использует `$dayOfMonth` напрямую → интерполяция `null` → `"ежемесячно (null)"`. Пользователь увидит буквальное слово «null» в UI.

**Пример:**
```
rule = RecurrenceRule(MONTHLY, dayOfMonth = null, interval = 1)
toLabel() → "ежемесячно (null)"
rule = RecurrenceRule(WEEKLY, dayOfWeek = null, interval = 1)
toLabel() → "еженедельно ()"
```

**Исправление:**

```kotlin
RecurrenceType.WEEKLY -> {
    val dayName = when (dayOfWeek) {
        1 -> "пн"; 2 -> "вт"; 3 -> "ср"; 4 -> "чт"
        5 -> "пт"; 6 -> "сб"; 7 -> "вс"
        else -> "—"
    }
    if (interval == 1) "еженедельно ($dayName)" else "каждые $interval нед. ($dayName)"
}
RecurrenceType.MONTHLY -> {
    val day = dayOfMonth?.toString() ?: "—"
    if (interval == 1) "ежемесячно ($day)" else "каждые $interval мес. ($day)"
}
```

---

### 5. `parse()` не валидирует значения и тихо принимает `interval = 0` / отрицательные / `dayOfWeek` вне 1–7

**Файл:** `RecurrenceRule.kt:45-67`
**Критичность:** критичный (связан с находками 1 и 2)

**Описание:** `parse` использует `?: 1` только когда поле **отсутствует или не парсится в Int**. Но если поле есть и парсится в `0`, `-3`, `99` — оно принимается как есть:
- `"DAILY:0"` → `interval = 0` → баг из находки 1.
- `"DAILY:-2"` → `interval = -2` → баг из находки 2.
- `"WEEKLY:99:1"` → `dayOfWeek = 99` → `toLabel` покажет `""`, `nextWeekly` тихо сожмёт до 7 (несогласованность).
- `"MONTHLY:0:1"` → `dayOfMonth = 0` → `nextMonthly` сделает `coerceIn(1, maxDay) = 1` (тихая подмена), `toLabel` покажет `(0)`.

**Пример:**
```
serialized = "DAILY:0"
parse → RecurrenceRule(DAILY, interval = 0)
nextOccurrence → возвращает fromMillis (не строго после)
```

**Исправление:** см. находку 1 — фильтровать невалидные через `takeIf { ... } ?: 1`.

---

### 6. `dayOfMonth = 31` в коротком месяце тихо сдвигается — неконсистентный день срабатывания

**Файл:** `RecurrenceCalculator.kt:61-72` (`nextMonthly`)
**Критичность:** средний

**Описание:** `coerceIn(1, maxDay)` сжимает 31 → 28/29/30. Это приводит к «плавающему» дню:
- 31 января → 28 февраля (сработает 28.02).
- Следующий вызов с `from = 2026-02-28` → `plusMonths(1) = 2026-03-28` → `withDayOfMonth(31) = 2026-03-31` (вернёмся к 31).
- 31 марта → `plusMonths(1) = 2026-04-30` (plusMonths уже сжимает) → `withDayOfMonth(31.coerceIn(1,30)) = 30` → 30 апреля.
- 30 апреля → `plusMonths(1) = 2026-05-30` → `withDayOfMonth(31) = 2026-05-31` → снова 31.

Итог: пользователь видит напоминание то 31, то 28, то 30 числа. Это известная проблема recurrence-логики, но текущая реализация не документирована и не использует стандартный подход «last day of month if overflow».

Дополнительно, в retry-ветке (строка 69) используется `dayOfMonth.coerceIn(1, newMaxDay)` — берёт **оригинальный** `dayOfMonth` (например, 31), а не сжатый. Это правильно само по себе, но вся ветка `if (!candidate.isAfter(from))` в `nextMonthly` **фактически недостижима** при `interval >= 1` (см. отдельную находку 9) — она срабатывает только при `interval = 0`/отрицательном, т.е. является маскировкой бага из находки 1.

**Пример:**
```
rule = RecurrenceRule(MONTHLY, dayOfMonth = 31, interval = 1)
from = 2026-01-31T09:00
next → 2026-02-28T09:00 (не 31!)
next (from=2026-02-28) → 2026-03-31T09:00
next (from=2026-03-31) → 2026-04-30T09:00
```

**Исправление (точечное):** документировать поведение как «если день не существует, берётся последний день месяца», и сделать его **детерминированным** — всегда использовать последний день месяца, если целевой день больше `lengthOfMonth`:

```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    val safeInterval = interval.coerceAtLeast(1).toLong()
    var candidate = from.plusMonths(safeInterval).withSameTime(from)
    val maxDay = candidate.toLocalDate().lengthOfMonth()
    val targetDay = dayOfMonth.coerceIn(1, 31).coerceAtMost(maxDay)
    candidate = candidate.withDayOfMonth(targetDay)
    // При interval >= 1 candidate всегда в будущем месяце → isAfter(from) гарантированно true.
    // Защитный guard оставлен для defence-in-depth.
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusMonths(safeInterval)
        val newMaxDay = candidate.toLocalDate().lengthOfMonth()
        candidate = candidate.withDayOfMonth(dayOfMonth.coerceIn(1, 31).coerceAtMost(newMaxDay))
    }
    return candidate
}
```

---

### 7. `nextWeekly` и `nextMonthly` молча сжимают `dayOfWeek`/`dayOfMonth` через `coerceIn` — несогласованность с `toLabel`

**Файл:** `RecurrenceCalculator.kt:51` (`targetDow = dayOfWeek.coerceIn(1, 7)`), `:64` (`targetDay = dayOfMonth.coerceIn(1, maxDay)`)
**Критичность:** низкий

**Описание:** Калькулятор тихо сжимает невалидные значения, тогда как `toLabel` для `dayOfWeek = 99` возвращает `""`, а для `dayOfMonth = 0` — `(0)`. Один и тот же `RecurrenceRule` отображается некорректно в UI, но «работает» в калькуляторе. Это нарушает принцип единого источника валидации.

**Пример:**
```
rule = RecurrenceRule(WEEKLY, dayOfWeek = 99, interval = 1)
toLabel() → "еженедельно ()"
nextWeekly → targetDow = 99.coerceIn(1,7) = 7 → срабатывает по воскресеньям
```
Пользователь видит пустые скобки, но напоминалка работает по воскресеньям.

**Исправление:** валидировать на уровне `RecurrenceRule` (см. находку 1) — тогда `coerceIn` в калькуляторе станет избыточным, но его можно оставить как defence-in-depth. В `toLabel` для `else` вернуть `"—"` вместо `""`.

---

### 8. Неиспользуемый импорт `ChronoUnit`

**Файл:** `RecurrenceCalculator.kt:5`
**Критичность:** низкий

**Описание:** `import java.time.temporal.ChronoUnit` присутствует, но ни один символ из него не используется в файле. Лишний импорт загрязняет пространство и может запутать читателя (кажется, что где-то есть `ChronoUnit.DAYS`).

**Исправление:**

```kotlin
package com.example.voicemind.data

import java.time.ZoneId
import java.time.ZonedDateTime

object RecurrenceCalculator {
    // ...
}
```

---

## Граничные случаи (проверено, не баг)

### `nextWeekdays` / `nextWeekends` — зацикливание

**Файл:** `RecurrenceCalculator.kt:33-47`

Циклы ограничены:
- `nextWeekdays`: максимум с пятницы → суббота → воскресенье → понедельник = 3 итерации.
- `nextWeekends`: максимум с воскресенья → понедельник → … → суббота = 6 итераций.

Условия `dayOfWeek.value > 5` и `dayOfWeek.value < 6` корректны (ISO: 1=Mon … 7=Sun). Зацикливания нет.

### `nextWeekly` — `delta = (targetDow - currentDow + 7) % 7`

Формула корректна для всех комбинаций `targetDow`, `currentDow` в 1..7. `+7` гарантирует неотрицательность, `% 7` даёт сдвиг в днях вперёд (0..6). Проверено для всех 49 комбинаций.

### `nextWeekly` — гарантия «строго после» при `interval >= 1`

При `interval >= 1` `candidate = from.plusWeeks(interval)` всегда в будущем. Если `delta = 0` (уже нужный день недели в будущей неделе), `candidate` остаётся в будущем. Если `delta > 0` — ещё дальше в будущем. Защитный `if (!candidate.isAfter(from))` срабатывает только при `interval = 0` (баг 1) или отрицательном (баг 2). При валидном `interval` он избыточен, но не вредит.

### `nextOccurrence` — конвертация `fromMillis` (UTC epoch) + локальная `zone`

`ZonedDateTime.ofInstant(Instant.ofEpochMilli(fromMillis), zone)` корректно интерпретирует `epoch millis` как абсолютный момент и показывает его в `zone`. Итерация дней/месяцев идёт в стеночном времени `zone`, а `toInstant().toEpochMilli()` возвращает абсолютный момент. Если `fromMillis` хранится в UTC (как рекомендует `architecture-guardrails.mdc` — `fireAt` epoch millis), а `zone` — локальная, конвертация **корректна**: epoch не зависит от зоны, зона влияет только на то, какой стеночный день считать «завтра». Это правильное поведение.

### `serialize` / `parse` — round-trip для валидных правил

Для валидных правил (`interval >= 1`, `dayOfWeek` 1..7, `dayOfMonth` 1..31) round-trip `serialize → parse` сохраняет все поля. Проверено для всех 5 типов. `parts.getOrNull` + `?: 1` безопасно обрабатывает отсутствующие поля.

### `parse` — лишние двоеточия / не-Int значения

`"WEEKLY:2:1:garbage"` → `parts[0]=WEEKLY, parts[1]=2, parts[2]=1`, лишнее игнорируется. `"DAILY:abc"` → `toIntOrNull() = null` → `interval = 1`. Не баг (defensive fallback), но см. находку 5 — для **валидных чисел вне диапазона** fallback не срабатывает.

### `nextMonthly` — `withSameTime` после `withDayOfMonth`

`withDayOfMonth` сохраняет время, последующий `withSameTime(from)` избыточен, но не вреден. Поведение корректно.

---

## Дополнительные находки

### A. Retry-ветка в `nextMonthly` — фактически мёртвый код при валидном `interval`

**Файл:** `RecurrenceCalculator.kt:66-70`
**Критичность:** низкий (стиль/читаемость)

При `interval >= 1` `candidate = from.plusMonths(interval)` всегда в месяце **позже** `from`, поэтому `candidate.isAfter(from)` всегда `true` независимо от `targetDay`. Ветка `if (!candidate.isAfter(from))` выполняется только при `interval = 0` или отрицательном — т.е. маскирует баг 1/2 вместо явной валидации. После исправления валидации `interval >= 1` эту ветку можно удалить или оставить как defence-in-depth с комментарием.

### B. `serialize` использует `?: 1` для `null`-полей, а `toLabel` — нет → неконсистентность

**Файл:** `RecurrenceRule.kt:39-40` vs `:23-30`

`serialize` для `WEEKLY` пишет `dayOfWeek ?: 1`, для `MONTHLY` — `dayOfMonth ?: 1`. После round-trip `null` превращается в `1` (понедельник / 1-е число). Но `toLabel` для `null` показывает `()` / `(null)`. Один и тот же объект до сериализации и после сериализации даёт **разные** метки в UI. Стоит привести к единообразию: либо `toLabel` тоже использует `?: 1` (но тогда пользователь увидит «пн» для правила без дня — некорректно), либо валидация в `init` запрещает `null` для `WEEKLY`/`MONTHLY` (предпочтительно).

### C. `nextOccurrence` — `dayOfWeek ?: 1` / `dayOfMonth ?: 1` тихо подменяет `null`

**Файл:** `RecurrenceCalculator.kt:23-24`

Если для `WEEKLY` правило создано без `dayOfWeek`, калькулятор тихо использует понедельник. Это скрывает ошибку конструирования правила. После добавления валидации в `init` (находка 1) эти `?: 1` станут недостижимыми для валидных правил — можно оставить как defence-in-depth или убрать.

---

## Сводка

| # | Баг | Файл | Критичность |
|---|-----|------|-------------|
| 1 | `interval = 0` нарушает «строго после» | RecurrenceCalculator.kt:29-72 | критичный |
| 2 | Отрицательный `interval` → прошлое | RecurrenceCalculator.kt:30,50,62 | критичный |
| 3 | DST spring-forward в `withSameTime` | RecurrenceCalculator.kt:74-79 | средний |
| 4 | `toLabel` для `null`-полей: `(null)` / `()` | RecurrenceRule.kt:23-30 | средний |
| 5 | `parse` не валидирует `interval`/`dayOfWeek`/`dayOfMonth` | RecurrenceRule.kt:45-67 | критичный |
| 6 | `dayOfMonth = 31` плавает по коротким месяцам | RecurrenceCalculator.kt:61-72 | средний |
| 7 | `coerceIn` в калькуляторе vs `toLabel` — неконсистентность | RecurrenceCalculator.kt:51,64 | низкий |
| 8 | Неиспользуемый импорт `ChronoUnit` | RecurrenceCalculator.kt:5 | низкий |
| A | Мёртвая retry-ветка в `nextMonthly` | RecurrenceCalculator.kt:66-70 | низкий |
| B | `serialize` vs `toLabel` неконсистентность для `null` | RecurrenceRule.kt:39-40 | низкий |
| C | Тихая подмена `null` → 1 в `nextOccurrence` | RecurrenceCalculator.kt:23-24 | низкий |

**Корневая причина большинства багов** — отсутствие валидации в `RecurrenceRule` (конструктор + `parse`). Точечное исправление находок 1, 2, 5 (валидация `interval >= 1`, `dayOfWeek in 1..7`, `dayOfMonth in 1..31`) устраняет сразу три критичные проблемы и делает `coerceIn` в калькуляторе избыточным.
