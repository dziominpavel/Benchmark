---
task: T-001
model: modelB
date: 2026-09-05
---

# Ответ на задачу T-001

## Анализ

Разобраны `RecurrenceCalculator.kt` и `RecurrenceRule.kt` на коммите `ce2d3f66`. Контракт `nextOccurrence`: одно ближайшее срабатывание **строго после** `fromMillis` (без «догоняющих» пропущенных слотов). `fromMillis` — UTC-instant, локальные поля считаются в переданном `zone`. Время суток в правиле **не хранится**: час/минута копируются с `from` через `withSameTime`.

Проверены: DAILY / WEEKDAYS / WEEKENDS / WEEKLY / MONTHLY, `interval` 0 и отрицательный, `dayOfWeek` вне 1–7, `dayOfMonth` 31 в коротком месяце, високосный февраль, DST-разрыв и overlap, конвертация instant↔зона, `parse`/`serialize`, циклы WEEKDAYS/WEEKENDS.

Главный дефект WEEKLY/MONTHLY: сначала делается `plusWeeks`/`plusMonths(interval)`, потом выравнивание по целевому дню. Из-за этого пропускается ближайший слот в текущей неделе/месяце. Для `interval >= 1` ветки `if (!candidate.isAfter(from))` почти мёртвые — компенсация «не после from» не срабатывает.

## Находки

### 1. WEEKLY пропускает ближайший целевой день недели

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:49`
**Критичность:** критичный
**Описание:** `nextWeekly` сначала сдвигает `from` на `interval` недель и только потом доводит дату до `dayOfWeek`. «Каждый вторник» с понедельника должно дать **ближайший** вторник, а не вторник через 8 дней. Дельта `(target - current + 7) % 7` считается уже от даты через N недель, поэтому к интервалу добавляется ещё 0–6 дней.

Ветка `isAfter` для `interval >= 1` не спасает: кандидат уже минимум на неделю впереди.

При `interval > 1` ошибка удваивается: с понедельника «каждые 2 недели во вторник» прыгает на вторник через ~15 дней, минуя ближайший вторник.

**Пример:**
- `from` = понедельник 2026-06-22 09:00 (`Europe/Moscow`)
- `RecurrenceRule(WEEKLY, dayOfWeek=2, interval=1)` — каждый вторник
- Ожидание: 2026-06-23 09:00 (завтра)
- Факт: `plusWeeks(1)` → 2026-06-29 (пн), `delta=1` → **2026-06-30 09:00** (вторник через 8 дней)

Ещё: среда 2026-06-24, цель понедельник (`dayOfWeek=1`) → должно быть 2026-06-29, код даёт 2026-07-06.

Совпадение дня недели работает случайно: пятница→пятница, `delta=0`, `plusWeeks(1)` — ровно следующая пятница.

**Исправление:** сначала выровнять на целевой DOW относительно `from`, и только если кандидат не строго после `from` — добавить `interval` недель.

```kotlin
private fun nextWeekly(from: ZonedDateTime, dayOfWeek: Int, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1).toLong()
    val targetDow = dayOfWeek.coerceIn(1, 7)
    val delta = (targetDow - from.dayOfWeek.value + 7) % 7
    var candidate = from.plusDays(delta.toLong()).withSameTime(from)
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusWeeks(step)
    }
    return candidate
}
```

После срабатывания во вторник (`from` уже вторник, то же локальное время) `delta=0`, `!isAfter` → `plusWeeks(step)` — интервал сохраняется.

---

### 2. MONTHLY пропускает ближайший день текущего месяца

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:61`
**Критичность:** критичный
**Описание:** Та же схема: `plusMonths(interval)` **до** `withDayOfMonth`. Если `from` ещё до целевого дня этого месяца, слот месяца пропускается.

`plusMonths` с 31-го числа сначала ужимает дату (31 янв → 28/29 фев), затем день ставится уже в **следующем** месяце. Для «31-е каждого месяца» с 10 января это даёт конец февраля вместо **31 января**.

`coerceIn(1, lengthOfMonth)` сам по себе корректен (короткий месяц не бросает `DateTimeException`), но применяется не к тому месяцу.

**Пример:**
- `from` = 2026-01-10 10:00, `MONTHLY, dayOfMonth=31, interval=1`
- Ожидание: 2026-01-31 10:00
- Факт: янв+1 мес → 10 фев, `31.coerceIn(1, 28)` → **2026-02-28 10:00**

Високос: `from` = 2024-02-10 10:00, `dayOfMonth=29` → должно быть 2024-02-29, код: март 10 + день 29 → **2024-03-29** (29 февраля високосного года пропущен).

`from` = 15-е, цель 15-е: `plusMonths(1)` совпадает с ожиданием — тесты `monthly_sameDay` / `monthly_31st_coerces` этот класс ошибок не ловят.

**Исправление:** поставить день в текущем месяце; если не строго после `from` — перенести на `interval` месяцев и снова ужать день.

```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1).toLong()
    fun atTargetDay(base: ZonedDateTime): ZonedDateTime {
        val maxDay = base.toLocalDate().lengthOfMonth()
        val targetDay = dayOfMonth.coerceIn(1, maxDay)
        return base.withSameTime(from).withDayOfMonth(targetDay)
    }
    var candidate = atTargetDay(from)
    if (!candidate.isAfter(from)) {
        candidate = atTargetDay(from.plusMonths(step))
    }
    return candidate
}
```

Цепочка 31 янв → 28 фев (2026) → 31 мар сохраняется: с `from`=31 янв кандидат января не после `from`, февраль ужимает 31→28; со `from`=28 фев и правилом 31 марта даёт 31 (берётся `dayOfMonth` правила, а не день кандидата).

---

### 3. `interval <= 0` ломает контракт «строго после»

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:29` (также 49, 61)
**Критичность:** критичный
**Описание:** Ни калькулятор, ни `parse` не требуют `interval >= 1`.

| Тип | `interval=0` | `interval < 0` |
|---|---|---|
| DAILY | `plusDays(0)` → тот же instant, **нет** проверки `isAfter` | дата в прошлом |
| WEEKLY | если сегодня уже целевой DOW: `plusWeeks(0)` дважды → тот же instant | уход в прошлое, `isAfter` добавляет ещё отрицательные недели |
| MONTHLY | тот же день месяца и время → тот же instant; если целевой день уже прошёл — кандидат **раньше** `from`, `plusMonths(0)` не лечит | то же |

Повторный `nextFireAt ≈ fromMillis` для будильника даёт немедленный повтор → риск цикла.

**Пример:**
- `DAILY:0`, `from` = 2026-06-19 08:00 → результат **2026-06-19 08:00** (не строго после)
- `WEEKLY:2:0` (вторник), `from` = вторник 09:00 → тот же вторник 09:00
- `MONTHLY:10:0`, `from` = 2026-06-20 10:00, цель 10-е → 2026-06-10 10:00 (**в прошлом**)
- `DAILY:-3` → 16 июня, сразу «просрочено»

**Исправление:** защитный шаг в каждом методе (`coerceAtLeast(1)`, см. фрагменты выше) плюс отсечение в `parse` (находка 4). Для DAILY:

```kotlin
private fun nextDaily(from: ZonedDateTime, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1).toLong()
    return from.plusDays(step).withSameTime(from)
}
```

Страховка на выходе `nextOccurrence`:

```kotlin
require(candidate.isAfter(from)) { "nextOccurrence must be strictly after from" }
```

---

### 4. `RecurrenceRule.parse` не валидирует interval / dayOfWeek / dayOfMonth

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:45`
**Критичность:** критичный
**Описание:** `toIntOrNull() ?: 1` подставляет дефолт только при нечисле. Нуль, отрицательные и выход за диапазон проходят в правило и в `serialize` (round-trip сохраняет мусор). Конструктор `data class` тоже без инвариантов.

**Пример:**
- `"DAILY:0"` → `interval=0` (находка 3)
- `"DAILY:-5"` → `interval=-5`
- `"WEEKLY:0:1"` → `dayOfWeek=0` → в калькуляторе `coerceIn` превратит в понедельник **без ошибки**
- `"WEEKLY:9:1"` → `dayOfWeek=9` → воскресенье
- `"MONTHLY:0:1"` / `"MONTHLY:32:1"` → 0 или 32, дальше тихое `coerceIn`
- `"DAILY:abc"` → 1 (скрытый fallback, не баг контракта, но маскирует опечатку)

**Исправление:** точечная проверка после сборки правила, без переписывания `when`:

```kotlin
fun parse(serialized: String?): RecurrenceRule? {
    if (serialized.isNullOrBlank()) return null
    val parts = serialized.split(":")
    val rule = when (parts[0]) {
        "DAILY" -> RecurrenceRule(
            type = RecurrenceType.DAILY,
            interval = parts.getOrNull(1)?.toIntOrNull() ?: 1,
        )
        "WEEKDAYS" -> RecurrenceRule(type = RecurrenceType.WEEKDAYS)
        "WEEKENDS" -> RecurrenceRule(type = RecurrenceType.WEEKENDS)
        "WEEKLY" -> RecurrenceRule(
            type = RecurrenceType.WEEKLY,
            dayOfWeek = parts.getOrNull(1)?.toIntOrNull() ?: 1,
            interval = parts.getOrNull(2)?.toIntOrNull() ?: 1,
        )
        "MONTHLY" -> RecurrenceRule(
            type = RecurrenceType.MONTHLY,
            dayOfMonth = parts.getOrNull(1)?.toIntOrNull() ?: 1,
            interval = parts.getOrNull(2)?.toIntOrNull() ?: 1,
        )
        else -> null
    } ?: return null
    if (rule.interval < 1) return null
    if (rule.type == RecurrenceType.WEEKLY && rule.dayOfWeek !in 1..7) return null
    if (rule.type == RecurrenceType.MONTHLY && rule.dayOfMonth !in 1..31) return null
    return rule
}
```

---

### 5. DST: `withSameTime` ставит несуществующий локальный час

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:74`
**Критичность:** средний
**Описание:** `withHour` / `withMinute` на `ZonedDateTime` в **gap** (перевод часов вперёд) сдвигает локальное время на длину разрыва. Напоминание «каждый день в 02:30» в день spring-forward превращается в 03:30.

Если следующий вызов берёт уже 03:30 как `from`, сдвиг **залипает** на все последующие дни: исходные 02:30 в правиле нигде не хранятся.

Overlap (перевод назад): 01:30 существует дважды; `withHour` обычно берёт **ранний** offset — одно срабатывание, но UTC-instant может быть не тем, который ждал пользователь.

`plusDays` сам по себе уже резолвит gap; последующий `withSameTime` снова навязывает исходный час и повторяет резолв.

**Пример:**
- `zone` = `America/New_York`, 2026-03-08 02:00 → 03:00 (разрыва нет 02:00–03:00)
- `from` = 2026-03-07 02:30 EST, `DAILY interval=1`
- `plusDays(1)` + `withHour(2).withMinute(30)` → **2026-03-08 03:30 EDT**, не 02:30 и не «пропустить день»

**Исправление:** собирать локальную дату+время явно; в gap брать первый валидный момент после перехода, в overlap — более ранний offset (одно срабатывание в календарные сутки):

```kotlin
private fun ZonedDateTime.withSameTime(other: ZonedDateTime): ZonedDateTime {
    val ldt = this.toLocalDate().atTime(other.toLocalTime())
    val rules = this.zone.rules
    val offsets = rules.getValidOffsets(ldt)
    return when {
        offsets.size == 1 -> ZonedDateTime.of(ldt, this.zone)
        offsets.size > 1 -> ZonedDateTime.ofLocal(ldt, this.zone, offsets.first())
        else -> {
            val gap = rules.getTransition(ldt)
            if (gap != null && gap.isGap) {
                gap.dateTimeAfter.atZone(this.zone)
            } else {
                ldt.atZone(this.zone)
            }
        }
    }
}
```

В gap 02:30 → 03:00 (`dateTimeAfter`), а не 03:30. Полностью убрать «залипание» 03:30 в следующих вызовах можно только храня `LocalTime` в правиле (находка 6).

---

### 6. В правиле нет времени суток — слот привязан к часам `fromMillis`

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:11` и `RecurrenceCalculator.kt:18`
**Критичность:** средний
**Описание:** Сценарий задачи — «каждый вторник в **9:00**». В `RecurrenceRule` есть тип, interval, день недели/месяца, но не `LocalTime`. Калькулятор берёт час из `from`. Тогда «ближайшее будущее после now» в 15:07 даёт вторник **15:07**, а не 09:00. Поздний/ранний вызов (doze, reschedule просроченного) сдвигает серию.

Конвертация `Instant.ofEpochMilli(fromMillis)` → `ZonedDateTime(..., zone)` при этом **корректна**: epoch всегда UTC, `zone` задаёт локальные поля. Баг не в UTC vs local, а в отсутствии времени в правиле.

**Пример:** правило `WEEKLY, dayOfWeek=2`, пользователь создал «вт 09:00». Вызов `nextOccurrence(rule, now)` в понедельник 15:07 → даже после фикса находки 1 получится вторник **15:07**.

**Исправление:** хранить время в правиле и применять его вместо часов `from`:

```kotlin
data class RecurrenceRule(
    val type: RecurrenceType,
    val interval: Int = 1,
    val dayOfWeek: Int? = null,
    val dayOfMonth: Int? = null,
    val hour: Int = 0,
    val minute: Int = 0,
)
```

Сериализация, например `WEEKLY:2:1:9:0`. В калькуляторе: `from.withHour(rule.hour).withMinute(rule.minute).withSecond(0).withNano(0)`, затем логика «строго после» из находок 1–2. Пока поля нет — вызывающая сторона должна передавать `fromMillis` с нужным локальным временем (предыдущий слот), а не «сейчас».

---

### 7. Невалидные `dayOfWeek` / `dayOfMonth` тихо ужимаются

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:51` и `:64`
**Критичность:** средний
**Описание:** `coerceIn(1, 7)` и `coerceIn(1, maxDay)` маскируют ошибки парсера/конструктора. `0` и отрицательные дни становятся 1-м; `8+` для недели — воскресеньем; `32` для месяца — последним днём **того** месяца, в котором оказался кандидат (ещё и не того, см. находку 2). Пользователь получает чужой день без сигнала.

`toLabel` для `dayOfWeek` вне 1–7 даёт пустое имя: `"еженедельно ()"`. Для `dayOfMonth=null` — `"ежемесячно (null)"`.

**Пример:** `WEEKLY, dayOfWeek=0` → понедельник; `MONTHLY, dayOfMonth=0` → 1-е число.

**Исправление:** валидация в `parse` (находка 4). В калькуляторе оставить `coerceIn` только как защиту от `DateTimeException` на коротком месяце для легального `dayOfMonth` 29–31.

Для подписи:

```kotlin
val dayName = when (dayOfWeek) {
    1 -> "пн"; 2 -> "вт"; 3 -> "ср"; 4 -> "чт"
    5 -> "пт"; 6 -> "сб"; 7 -> "вс"
    else -> dayOfWeek?.toString() ?: "?"
}
```

---

### 8. WEEKDAYS/WEEKENDS: в цикле не возвращается исходное локальное время

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:35` и `:43`
**Критичность:** средний
**Описание:** `withSameTime` вызывается один раз на `from.plusDays(1)`. Дальнейшие `plusDays(1)` в `while` оставляют время, уже сдвинутое DST. Пятница 02:30 перед воскресеньем с gap → понедельник может стать 03:30, хотя понедельник вне разрыва и 02:30 там валиден.

Зацикливания нет: `DayOfWeek.value` всегда 1–7; WEEKDAYS сходит с 6–7 максимум за 2 шага, WEEKENDS набирает 6–7 максимум за 6 шагов.

**Пример:** пятница 2026-03-06 02:30 `America/New_York`, WEEKDAYS → суббота 02:30 → воскресенье 03:30 (gap) → понедельник **03:30** вместо 02:30.

**Исправление:**

```kotlin
private fun nextWeekdays(from: ZonedDateTime): ZonedDateTime {
    var candidate = from.plusDays(1).withSameTime(from)
    while (candidate.dayOfWeek.value > 5) {
        candidate = candidate.plusDays(1).withSameTime(from)
    }
    return candidate
}

private fun nextWeekends(from: ZonedDateTime): ZonedDateTime {
    var candidate = from.plusDays(1).withSameTime(from)
    while (candidate.dayOfWeek.value < 6) {
        candidate = candidate.plusDays(1).withSameTime(from)
    }
    return candidate
}
```

---

## Граничные случаи (проверено, не баг)

- **Часовой пояс / UTC:** `ZonedDateTime.ofInstant(Instant.ofEpochMilli(fromMillis), zone)` и `toInstant().toEpochMilli()` корректны. `fromMillis` — epoch UTC; `zone` только проецирует локальные поля. Расхождение «millis посчитали как local, zone другая» — ошибка вызывающего кода, не этих двух файлов.
- **DAILY `interval=1`:** `from + 1` календарный день, то же локальное время. Контракт «строго после» выполняется (кроме DST-gap, находка 5).
- **DAILY `interval=2`:** через два календарных дня, без накопления пропущенных суток — соответствует «ближайшее будущее, не пачка слотов».
- **WEEKDAYS:** пт→пн, пн→вт, сб→пн, вс→пн. ISO: 1=пн … 5=пт. Цикл конечен.
- **WEEKENDS:** пт→сб, сб→вс, вс→следующая сб (серия сб+вс). Цикл конечен.
- **WEEKLY, `from` уже в целевой день, то же время:** следующая неделя — верно для «строго после» (после фикса находки 1 поведение на этом входе совпадает с текущим).
- **MONTHLY, `from` уже в целевой день:** следующий месяц — верно. 31 янв 2026 + правило 31 → 28 фев (`plusMonths` + `coerceIn`) — разумный clamp, `DateTimeException` нет. В марте 31 восстанавливается, потому что `withDayOfMonth` берёт `dayOfMonth` правила, а не 28.
- **Невисокосный февраль и `dayOfMonth=29/31` при `from` уже 31 янв / 28 фев:** ужим до 28. Баг — только если 29/31 **ещё впереди** в текущем месяце (находка 2).
- **`dayOfWeek ?: 1` / `dayOfMonth ?: 1`:** при `null` — пн / 1-е; согласовано с `serialize`.
- **`serialize`/`parse` для валидных значений:** `DAILY:2`, `WEEKLY:2:1`, `MONTHLY:15:1`, `WEEKDAYS`, `WEEKENDS` — round-trip.
- **Неизвестный тип / blank:** `parse` → `null`.
- **WEEKDAYS/WEEKENDS и `interval` в конструкторе:** serialize interval не пишет; для голосовых правил interval не используется. Игнор `interval=2` — ограничение модели, не бесконечный цикл.
- **Значение `DayOfWeek`:** ISO совпадает с подписями пн=1 … вс=7 в `toLabel`.

## Дополнительные находки

- **Неиспользуемый импорт** `java.time.temporal.ChronoUnit` в `RecurrenceCalculator.kt:5` (низкий). Удалить либо заменить `plusDays` на `ChronoUnit.DAYS.addTo` — на семантику не влияет.
- **`nextDaily` без `isAfter`:** в отличие от WEEKLY/MONTHLY. При `interval >= 1` и без отрицательного шага результат и так после `from`; асимметрия всплывает только вместе с находкой 3.
- **Порядок `withHour` → `withMinute`:** в overlap/gap промежуточное `withHour(2)` уже резолвит дату, затем минуты ставятся на сдвинутый час. Явная сборка `LocalDate + LocalTime` (находка 5) это снимает.
- **`toLabel` для WEEKLY с `dayOfWeek=null`:** пустые скобки; для MONTHLY с `null` — литерал `"null"` в UI. Низкий, чинится в находке 7.
- **Экстремальный `interval` (Int.MAX_VALUE):** `plusWeeks`/`plusMonths` могут выйти за диапазон `ZonedDateTime` (`DateTimeException`). Низкий; после `coerceAtLeast(1)` отрицательный край пропадает, верхний лучше ограничить разумным максимумом в `parse` (например `interval in 1..365`).
- **Пробелы в сериализации** (`"DAILY: 2"`): `toIntOrNull` → `null` → interval=1. Низкий; при желании `trim()` каждой части.
