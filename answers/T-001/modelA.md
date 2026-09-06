---
task: T-001
model: modelA
date: 2026-09-05
---

# Ответ на задачу T-001

## Анализ

Проанализированы `RecurrenceCalculator.kt` (80 строк) и `RecurrenceRule.kt` (69 строк) на коммите `ce2d3f66`. Изучены все ветки `when` в `nextOccurrence`, вспомогательный `withSameTime`, сериализация/парсинг правил и существующие unit-тесты (`RecurrenceCalculatorTest.kt`). Проверены контракт «строго после `fromMillis`», поведение при `interval=0`/отрицательном interval, DST, переходы месяцев и граничные значения `dayOfWeek`/`dayOfMonth`.

## Находки

### 1. `interval=0` нарушает контракт «строго после fromMillis» (DAILY)

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:29-31`
**Критичность:** критичный
**Описание:** `nextDaily` при `interval=0` вызывает `from.plusDays(0)`, что возвращает ту же метку времени, что и `from`. Документация `nextOccurrence` (стр. 10–11) обещает срабатывание **строго после** `fromMillis`. При повторном вызове после срабатывания будильника (как в `ReminderAlarmReceiver`, где `fromMillis = System.currentTimeMillis()`) напоминание может зациклиться на том же `fireAt` или не продвинуться вперёд.

**Пример:**
- `from` = 2026-06-19 08:00 (Europe/Moscow)
- `rule` = `RecurrenceRule(DAILY, interval = 0)`
- Результат: 2026-06-19 08:00 (равно `from`, не `>`)

**Исправление:**
```kotlin
private fun nextDaily(from: ZonedDateTime, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1)
    return from.plusDays(step.toLong()).withSameTime(from)
}
```

### 2. `interval=0` нарушает контракт «строго после» (WEEKLY, тот же день недели)

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:49-58`
**Критичность:** критичный
**Описание:** При `interval=0` и `dayOfWeek`, совпадающем с текущим днём, `delta=0`, кандидат равен `from`. Ветка коррекции `plusWeeks(interval.toLong())` при `interval=0` ничего не меняет — метод возвращает `from`.

**Пример:**
- `from` = пятница 2026-06-19 07:00
- `rule` = `RecurrenceRule(WEEKLY, dayOfWeek = 5, interval = 0)`
- Результат: 2026-06-19 07:00 (не строго после)

**Исправление:**
```kotlin
private fun nextWeekly(from: ZonedDateTime, dayOfWeek: Int, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1)
    var candidate = from.plusWeeks(step.toLong()).withSameTime(from)
    val targetDow = dayOfWeek.coerceIn(1, 7)
    val currentDow = candidate.dayOfWeek.value
    val delta = (targetDow - currentDow + 7) % 7
    candidate = candidate.plusDays(delta.toLong())
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusWeeks(step.toLong())
    }
    return candidate
}
```

### 3. `interval=0` нарушает контракт «строго после» (MONTHLY, тот же день месяца)

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:61-71`
**Критичность:** критичный
**Описание:** При `interval=0` и `dayOfMonth`, совпадающем с текущим днём, `plusMonths(0)` + `withDayOfMonth(targetDay)` даёт ту же дату. Коррекция `plusMonths(0)` снова не продвигает кандидата.

**Пример:**
- `from` = 2026-06-15 10:00
- `rule` = `RecurrenceRule(MONTHLY, dayOfMonth = 15, interval = 0)`
- Результат: 2026-06-15 10:00

**Исправление:**
```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1)
    var candidate = from.plusMonths(step.toLong()).withSameTime(from)
    val maxDay = candidate.toLocalDate().lengthOfMonth()
    val targetDay = dayOfMonth.coerceIn(1, maxDay)
    candidate = candidate.withDayOfMonth(targetDay)
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusMonths(step.toLong()).withSameTime(from)
        val newMaxDay = candidate.toLocalDate().lengthOfMonth()
        candidate = candidate.withDayOfMonth(dayOfMonth.coerceIn(1, newMaxDay))
    }
    return candidate
}
```

### 4. Отрицательный `interval` возвращает прошлое время

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:29-31, 49-50, 61-62`
**Критичность:** критичный
**Описание:** `plusDays(-1)`, `plusWeeks(-1)`, `plusMonths(-1)` сдвигают кандидата в прошлое относительно `from`. Метод обещает ближайшее **будущее** срабатывание. Отрицательный interval может попасть в систему через `parse()` (см. находку 8) или повреждённую БД.

**Пример:**
- `from` = 2026-06-19 08:00
- `rule` = `RecurrenceRule(DAILY, interval = -1)`
- Результат: 2026-06-18 08:00 (< `from`)

**Исправление:** валидировать interval при создании/парсинге (≥ 1) и/или `coerceAtLeast(1)` в калькуляторе.

### 5. DST: `withSameTime` задаёт несуществующее локальное время (весенний переход)

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:74-79`
**Критичность:** средний
**Описание:** `withSameTime` копирует wall-clock (час/минуту/секунду) через `withHour`/`withMinute`. При переходе на летнее время некоторые локальные моменты не существуют (gap). `java.time` разрешает их сдвигом вперёд (например, 02:30 → 03:30), и напоминание срабатывает на другом времени, чем ожидал пользователь.

**Пример:**
- Зона: `America/New_York`
- Напоминание: ежедневно в 02:30
- `from` = 2024-03-09 02:30 EST
- `nextDaily` → 2024-03-10: `plusDays(1)` + `withSameTime(02:30)` → 2024-03-10 **03:30** EDT (02:30 в этот день не существует)

**Исправление:**
```kotlin
private fun ZonedDateTime.withSameTime(other: ZonedDateTime): ZonedDateTime {
    val target = this.toLocalDate().atTime(other.toLocalTime())
    return try {
        ZonedDateTime.of(target, this.zone)
    } catch (e: java.time.DateTimeException) {
        // gap: взять следующий валидный момент после желаемого времени
        ZonedDateTime.of(target, this.zone.rules.getValidOffsets(target).last().let { offset ->
            java.time.ZoneOffset.ofTotalSeconds(offset.totalSeconds)
        }).let { /* fallback */ this.withHour(other.hour).withMinute(other.minute) }
    }
}
```
Практичнее: хранить `LocalTime` отдельно и при gap использовать `ZoneRules.getTransition` / `withLaterOffsetAtOverlap`, либо документировать поведение и тестировать для целевых зон.

### 6. DST: неоднозначное время при осеннем переходе (fall-back)

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:74-79`
**Критичность:** средний
**Описание:** При переходе на зимнее время одно и то же локальное время (например, 01:30) существует дважды (разные offset). `withHour(1).withMinute(30)` выбирает один из offset'ов по правилам `java.time` (обычно более ранний), что может расходиться с ожиданием пользователя и давать сдвиг на 1 час относительно предыдущих срабатываний.

**Пример:**
- Зона: `Europe/Berlin`
- Ежедневно в 01:30; `from` = дата осеннего перехода 02:30 CEST
- Следующий день попадает в overlap 01:30 CET/CEST — выбор offset неочевиден

**Исправление:** при построении кандидата использовать `withZoneSameInstant` + фиксированный offset предыдущего срабатывания, либо `LocalTime` + явный `ZoneOffset` из предыдущего `ZonedDateTime`.

### 7. MONTHLY: `dayOfMonth=31` в коротком месяце — clamp вместо «следующего 31-го»

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:63-65`
**Критичность:** средний
**Описание:** `dayOfMonth.coerceIn(1, maxDay)` подставляет последний день месяца, если 31-го нет. Пользователь «каждое 31-е» после 31 января получит 28 февраля, а не 31 марта. Тест `monthly_31st_coerces` закрепляет текущее поведение, но для голосовой напоминалки это семантическая ошибка: напоминание срабатывает «не в тот день».

**Пример:**
- `from` = 2026-01-31 10:00, `dayOfMonth = 31`, `interval = 1`
- Результат: 2026-02-28 10:00
- Ожидание многих календарей: 2026-03-31 10:00

**Исправление (вариант «только существующий день»):**
```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1)
    var candidate = from.plusMonths(step.toLong()).withSameTime(from)
    if (dayOfMonth > candidate.toLocalDate().lengthOfMonth()) {
        candidate = candidate.plusMonths(step.toLong()).withSameTime(from)
    }
    val maxDay = candidate.toLocalDate().lengthOfMonth()
    candidate = candidate.withDayOfMonth(dayOfMonth.coerceIn(1, maxDay))
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusMonths(step.toLong()).withSameTime(from)
        if (dayOfMonth > candidate.toLocalDate().lengthOfMonth()) {
            candidate = candidate.plusMonths(step.toLong()).withSameTime(from)
        }
        val newMaxDay = candidate.toLocalDate().lengthOfMonth()
        candidate = candidate.withDayOfMonth(dayOfMonth.coerceIn(1, newMaxDay))
    }
    return candidate
}
```

### 8. MONTHLY: порядок `plusMonths` + `withDayOfMonth` даёт неверный месяц для end-of-month дат

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:61-65`
**Критичность:** средний
**Описание:** Сначала сдвигается месяц от **текущей** даты `from`, затем выставляется день. Если `from` — 30 января, а правило «31-е число», `plusMonths(1)` даёт 28 февраля (end-of-month adjustment в `java.time`), и `withDayOfMonth(28)` оставляет февраль вместо марта с 31-м.

**Пример:**
- `from` = 2026-01-30 10:00, `dayOfMonth = 31`, `interval = 1`
- Результат: 2026-02-28 10:00
- Ожидание: 2026-03-31 10:00

**Исправление:** сначала выровнять день в целевом месяце (или искать следующий месяц, где `dayOfMonth` существует), затем проверять `isAfter(from)`.

### 9. `nextWeekly`: `dayOfWeek` вне 1–7 молча приводится через `coerceIn`

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:51`
**Критичность:** средний
**Описание:** `dayOfWeek = 0` → понедельник, `8` → воскресенье без ошибки. Парсер/пользователь не узнает об ошибке; напоминание сработает не в тот день.

**Пример:**
- `rule` = `RecurrenceRule(WEEKLY, dayOfWeek = 0, interval = 1)` (или `WEEKLY:0:1` из БД)
- Фактически используется понедельник (`coerceIn(1,7)`)

**Исправление:** валидировать в `parse()` и конструкторе:
```kotlin
require(dayOfWeek == null || dayOfWeek in 1..7) { "dayOfWeek must be 1..7" }
```

### 10. `RecurrenceRule.parse()` не валидирует `interval`, `dayOfWeek`, `dayOfMonth`

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:45-66`
**Критичность:** средний
**Описание:** Строки `DAILY:0`, `DAILY:-3`, `WEEKLY:9:1`, `MONTHLY:0:1` успешно парсятся. Нулевой/отрицательный interval и некорректные дни попадают в калькулятор и ломают контракт (находки 1–4, 9).

**Пример:**
- `RecurrenceRule.parse("DAILY:0")` → `interval = 0`
- `RecurrenceRule.parse("MONTHLY:0:1")` → `dayOfMonth = 0` → в калькуляторе `coerceIn(1, maxDay)` → 1-е число

**Исправление:**
```kotlin
private fun parseInterval(value: String?): Int =
    (value?.toIntOrNull() ?: 1).also { require(it >= 1) { "interval must be >= 1" } }

private fun parseDayOfWeek(value: String?): Int =
    (value?.toIntOrNull() ?: 1).also { require(it in 1..7) { "dayOfWeek must be 1..7" } }

private fun parseDayOfMonth(value: String?): Int =
    (value?.toIntOrNull() ?: 1).also { require(it in 1..31) { "dayOfMonth must be 1..31" } }
```

### 11. Неиспользуемый импорт `ChronoUnit`

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:5`
**Критичность:** низкий
**Описание:** `import java.time.temporal.ChronoUnit` не используется ни в файле, ни косвенно.

**Исправление:** удалить строку импорта.

### 12. `toLabel()` для недопустимого `dayOfWeek` показывает пустое имя дня

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:23-27`
**Критичность:** низкий
**Описание:** При `dayOfWeek` вне 1–7 (если объект создан в обход `parse`) ветка `else -> ""` даёт подпись вида «еженедельно ()».

**Исправление:** валидировать при создании или использовать fallback `"?"` / не показывать день.

## Граничные случаи (проверено, не баг)

| Случай | Поведение | Почему OK |
|--------|-----------|-----------|
| **WEEKDAYS** с пятницы | +1 день → суббота → цикл до понедельника | Цикл `while (dow > 5)` завершается за ≤2 итерации, зацикливания нет |
| **WEEKENDS** с воскресенья | +1 → понедельник → … → суббота | Цикл `while (dow < 6)` завершается за ≤5 итераций |
| **WEEKLY** interval=1, тот же день | `plusWeeks(1)` + delta=0 | Следующая неделя строго после `from` (покрыто тестом `weekly_sameDay`) |
| **Високосный год** (29 фев) | `plusMonths` / `lengthOfMonth()` | Делегировано `java.time`, 2024→2025 корректно |
| **Конвертация UTC→zone** | `ZonedDateTime.ofInstant(..., zone)` | Instant абсолютен; при согласованной `zone` локальное время верное |
| **WEEKDAYS/WEEKENDS контракт «строго после»** | всегда `plusDays(1)` минимум | Кандидат минимум на следующий календарный день |
| **DAILY interval≥1** | `plusDays(interval)` | Строго после при положительном interval (тесты `daily_nextDay`, `daily_interval2`) |

## Дополнительные находки

- **`serialize()`/`parse()` round-trip** не гарантирует валидность: можно сериализовать `interval=0` через `RecurrenceRule(DAILY, interval=0).serialize()` → `"DAILY:0"`.
- **Дефолт `dayOfWeek ?: 1` и `dayOfMonth ?: 1`** в `nextOccurrence` (стр. 23–24) и `serialize()` скрывают отсутствие поля — для WEEKLY/MONTHLY без дня логичнее явная ошибка.
- **Второй `plusMonths` в `nextMonthly`** (стр. 67–69) не вызывает `withSameTime(from)` повторно; при редких DST-переходах на границе месяца время теоретически может «уплыть» (низкий риск для Europe/Moscow).
- Существующие тесты **не покрывают** `interval=0`, отрицательный interval, DST и семантику «31-е только когда есть».
