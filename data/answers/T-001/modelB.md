---
task: T-001
model: modelB
date: 2026-09-05
---

# Ответ на задачу T-001

## Анализ

Рассмотрены два файла на коммите `ce2d3f6` проекта VoiceMind:

- `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt` (80 строк)
- `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt` (69 строк)

Метод `nextOccurrence()` обещает вернуть срабатывание **строго после** `fromMillis`.
Проверены: контракт «строго после», арифметика `plusDays` / `plusWeeks` / `plusMonths`,
поведение в короткие/високосные месяцы, DST-разрывы, конвертация часовых поясов,
валидация `parse()` / конструктора, завершаемость циклов WEEKDAYS/WEEKENDS.

**Итог: 7 находок — 3 критичных, 2 средних, 2 низких.**
Самый тяжёлый дефект: `nextWeekly` и `nextMonthly` систематически возвращают
срабатывание на один период позже положенного (еженедельное напоминание
«каждый вторник» при запросе в среду вернётся не через 6 дней, а через 13).

---

## Находки

### 1. nextWeekly возвращает срабатывание на неделю позже положенного

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:49-59`
**Критичность:** критичный

**Проблема:** алгоритм сначала прибавляет `interval` недель к `from`,
а уже потом подгоняет день недели вперёд (`delta`). Поэтому целевой день
текущей недели всегда пропускается — ответ опаздывает ровно на `interval` недель.
`plusWeeks()` сохраняет день недели, так что `delta`, посчитанный после сдвига,
равен `delta`, посчитанному от `from`. Итог: `результат = правильный ответ + 7 * interval дней`.
Фолбэк `if (!isAfter)` при `interval >= 1` — мёртвый код (кандидат после сдвига
всегда строго позже `from`), он ничего не чинит.

```kotlin
private fun nextWeekly(from: ZonedDateTime, dayOfWeek: Int, interval: Int): ZonedDateTime {
    var candidate = from.plusWeeks(interval.toLong()).withSameTime(from) // сдвиг ВПЕРЁД до подгонки — ошибка
    val targetDow = dayOfWeek.coerceIn(1, 7)
    val currentDow = candidate.dayOfWeek.value
    val delta = (targetDow - currentDow + 7) % 7
    candidate = candidate.plusDays(delta.toLong())
    ...
}
```

**Пример:** правило `WEEKLY(dayOfWeek=2 /* вторник */, interval=1)`,
`from` = среда 2026-09-02 10:00. Правильный ответ — вторник 2026-09-08 10:00
(через 6 дней). Алгоритм: 09-02 + 7 дней = среда 09-09, `delta` = 6 →
вторник **09-15** (через 13 дней). Напоминание «каждый вторник в 9:00»
прозвенит на неделю позже. Аналогично: `from` = понедельник 09-07, цель —
вторник: вернёт 09-15 вместо 09-08 (завтра).

Дополнительный подслучай — `interval > 1` пропускает валидное срабатывание:
правило «каждые 2 недели по вторникам», `from` = среда 09-02. Алгоритм:
09-02 + 2 недели = среда 09-16, `delta` = 6 → вторник 09-22.
Ближайший вторник после 09-02 — 09-15 — пропущен. (Полноценная «фаза»
для `interval > 1` без точки отсчёта в модели данных неопределима,
поэтому разумная семантика — ближайшее будущее срабатывание; см. исправление.)

**Исправление** (сначала подгонка дня недели, потом шаг — плюс защита интервала):

```kotlin
private fun nextWeekly(from: ZonedDateTime, dayOfWeek: Int, interval: Int): ZonedDateTime {
    val safeInterval = interval.coerceAtLeast(1)
    val targetDow = dayOfWeek.coerceIn(1, 7)
    val delta = (targetDow - from.dayOfWeek.value + 7) % 7
    var candidate = from.plusDays(delta.toLong()).withSameTime(from)
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusWeeks(safeInterval.toLong())
    }
    return candidate
}
```

Примечание: для `interval > 1` это возвращает ближайшее будущее совпадение
по дню недели. Истинная фаза «каждые N недель от даты создания» требует
поля-якоря в `RecurrenceRule` — это уже изменение модели, выходящее за рамки
точечного исправления, поэтому зафиксировано здесь как ограничение.

---

### 2. nextMonthly возвращает срабатывание на месяц позже положенного

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:61-72`
**Критичность:** критичный

**Проблема:** та же структурная ошибка, что в находке 1: сначала
`plusMonths(interval)`, потом установка дня месяца. Если целевой день месяца
ещё впереди в текущем месяце, он пропускается — ответ опаздывает на `interval`
месяцев. Фолбэк `if (!isAfter)` при `interval >= 1` мёртвый код: кандидат
всегда лежит в строго более позднем месяце, чем `from`, и потому всегда
`isAfter` независимо от дня.

```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    var candidate = from.plusMonths(interval.toLong()).withSameTime(from) // сдвиг ВПЕРЁД до подгонки — ошибка
    ...
    candidate = candidate.withDayOfMonth(targetDay)
    ...
}
```

**Пример 1:** правило `MONTHLY(dayOfMonth=20, interval=1)`,
`from` = суббота 2026-09-05 10:00. Правильный ответ — 20 сентября.
Алгоритм: 09-05 + 1 месяц = 10-05 → `withDayOfMonth(20)` = **20 октября**.
Опоздание на месяц.

**Пример 2 (короткий месяц):** правило `MONTHLY(dayOfMonth=29, interval=1)`,
`from` = среда 2024-02-28 10:00 (2024 — високосный). Правильный ответ —
четверг 2024-02-29 (завтра). Алгоритм: 02-28 + 1 месяц = 03-28 →
`withDayOfMonth(29)` = **29 марта**. Срабатывание 29 февраля пропущено.

**Исправление** (сначала пробуем текущий месяц, потом шаг):

```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    val safeInterval = interval.coerceAtLeast(1)
    val thisMonthMax = from.toLocalDate().lengthOfMonth()
    var candidate = from.withDayOfMonth(dayOfMonth.coerceIn(1, thisMonthMax))
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusMonths(safeInterval.toLong())
        val maxDay = candidate.toLocalDate().lengthOfMonth()
        candidate = candidate.withDayOfMonth(dayOfMonth.coerceIn(1, maxDay))
    }
    return candidate
}
```

(`withDayOfMonth` / `plusMonths` сами сохраняют время, отдельный `withSameTime`
не нужен.) Проверка исправления на примерах: 09-05 + dom=20 → 09-20, после
`from` → возврат (верно); `from` 09-05 10:00 + dom=5 → кандидат равен `from`,
не `isAfter` → +1 месяц = 10-05 (верно, строго после); `from` 2024-02-28 +
dom=29 → кандидат 2024-02-29, после → возврат (верно).

---

### 3. interval = 0 и отрицательный interval нарушают контракт «строго после»

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:29-31,49-59,61-72`
**Критичность:** критичный

**Проблема:** ни один из трёх параметризованных методов не проверяет `interval`.
Контракт `nextOccurrence` — «строго после `fromMillis`» — нарушается:

- `nextDaily` при `interval = 0`: `plusDays(0)` + то же время → кандидат **равен**
  `from`, возвращается то же самое `fromMillis`. Планировщик, пересчитывающий
  аларм от времени срабатывания, получит то же время и может зациклиться
  (плотный цикл перепланирований, расход батареи).
- `nextDaily` при `interval < 0`: возвращается **прошлое** (например,
  `interval = -1` → вчера в то же время).
- `nextWeekly` при `interval = 0` и совпадении дня недели: `plusWeeks(0)` +
  `delta = 0` → кандидат равен `from` → фолбэк `plusWeeks(0)` ничего не меняет →
  возвращается `from`. (При несовпадении дня недели `delta > 0` случайно даёт
  будущее — поведение непоследовательно.)
- `nextWeekly` при `interval < 0`: сдвиг в прошлое + подгонка 0–6 дней вперёд
  + повторный сдвиг в прошлое → возвращается прошлое.
- `nextMonthly` при `interval = 0`: если целевой день ≤ текущего дня месяца,
  кандидат равен `from` или раньше него, фолбэк `plusMonths(0)` бессилен.
  Пример: `from` = 2026-09-05 10:00, `dayOfMonth = 5` → возвращается тот же
  момент; `dayOfMonth = 3` → возвращается **прошлое** (3 сентября).
- `nextMonthly` при `interval < 0`: возвращается прошлое.

Источники невалидного `interval` реальны: `RecurrenceRule.parse()` принимает
`"DAILY:0"` / `"DAILY:-5"` без проверки (см. находку 4), а конструктор
`RecurrenceRule` не валидирует поля — такое правило можно построить и напрямую.

**Исправление:** защита на месте использования (показана в исправлениях
к находкам 1–2) плюс валидация на входе (находка 4):

```kotlin
private fun nextDaily(from: ZonedDateTime, interval: Int): ZonedDateTime {
    return from.plusDays(interval.coerceAtLeast(1).toLong()).withSameTime(from)
}
```

Альтернатива — `require(interval >= 1)` с исключением, но тогда каждый вызов
калькулятора обязан валидировать заранее; `coerceAtLeast(1)` безопаснее
для уже сохранённых правил.

---

### 4. RecurrenceRule.parse() не валидирует вход, конструктор не валидирует поля

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:11-16,45-67`
**Критичность:** средний

**Проблема:** `parse()` принимает заведомо некорректные значения и молча
превращает их в «валидные» правила, которые затем ломают калькулятор
(см. находку 3) или тихо переинтерпретируются:

| Вход | Результат `parse()` | Проблема |
|---|---|---|
| `"DAILY:0"`, `"DAILY:-5"` | `interval = 0 / -5` | Прошлое / тот же момент из калькулятора |
| `"WEEKLY:2:0"`, `"MONTHLY:15:-3"` | `interval = 0 / -3` | То же |
| `"WEEKLY:0:1"`, `"WEEKLY:9:1"` | `dayOfWeek = 0 / 9` | Калькулятор молча `coerceIn(1,7)` → понедельник/воскресенье, а `toLabel()` покажет пустое название дня |
| `"MONTHLY:0:1"`, `"MONTHLY:99:1"` | `dayOfMonth = 0 / 99` | Калькулятор молча клампит, а `toLabel()` покажет «ежемесячно (0)/(99)» — рассогласование |
| `"DAILY:abc"`, `"WEEKLY:x:y"` | `interval = 1` (фолбэк `?: 1`) | Битый ввод неотличим от корректного |
| `"DAILY:2147483647"` | гигантский `interval` | Аларм на миллионы лет вперёд — фактически «никогда», без ошибки |
| `"MONTHLY:15:1:мусор"` | лишние части игнорируются | Мусор в хранилище не замечается |

Корень проблемы — отсутствие инвариантов в самом `data class`: поля можно
сконструировать невалидными напрямую, без `parse()`.

**Исправление** — инварианты в конструкторе + строгий `parse()`:

```kotlin
data class RecurrenceRule(
    val type: RecurrenceType,
    val interval: Int = 1,
    val dayOfWeek: Int? = null,
    val dayOfMonth: Int? = null,
) {
    init {
        require(interval >= 1) { "interval must be >= 1, was $interval" }
        require(dayOfWeek == null || dayOfWeek in 1..7) { "dayOfWeek must be 1..7, was $dayOfWeek" }
        require(dayOfMonth == null || dayOfMonth in 1..31) { "dayOfMonth must be 1..31, was $dayOfMonth" }
    }
    ...
    companion object {
        fun parse(serialized: String?): RecurrenceRule? {
            if (serialized.isNullOrBlank()) return null
            val parts = serialized.split(":")
            return when (parts[0]) {
                "DAILY" -> {
                    val interval = parts.getOrNull(1)?.toIntOrNull() ?: 1
                    if (interval < 1) return null
                    RecurrenceRule(type = RecurrenceType.DAILY, interval = interval)
                }
                "WEEKDAYS" -> RecurrenceRule(type = RecurrenceType.WEEKDAYS)
                "WEEKENDS" -> RecurrenceRule(type = RecurrenceType.WEEKENDS)
                "WEEKLY" -> {
                    val dayOfWeek = parts.getOrNull(1)?.toIntOrNull() ?: 1
                    val interval = parts.getOrNull(2)?.toIntOrNull() ?: 1
                    if (dayOfWeek !in 1..7 || interval < 1) return null
                    RecurrenceRule(
                        type = RecurrenceType.WEEKLY,
                        dayOfWeek = dayOfWeek,
                        interval = interval,
                    )
                }
                "MONTHLY" -> {
                    val dayOfMonth = parts.getOrNull(1)?.toIntOrNull() ?: 1
                    val interval = parts.getOrNull(2)?.toIntOrNull() ?: 1
                    if (dayOfMonth !in 1..31 || interval < 1) return null
                    RecurrenceRule(
                        type = RecurrenceType.MONTHLY,
                        dayOfMonth = dayOfMonth,
                        interval = interval,
                    )
                }
                else -> null
            }
        }
    }
}
```

Если в хранилище уже могут лежатьRule с `interval = 0` (миграция), вместо
`return null` допустимо `coerceAtLeast(1)` / `coerceIn(...)` в `parse()` —
но молчаливое поведение должно быть задокументировано, а не случайным.

---

### 5. DST-разрыв: напоминание в 02:30 в день перехода молча сдвигается на 03:30

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:74-79`
**Критичность:** средний

**Проблема:** `withSameTime()` переносит час/минуту через `withHour()` /
`withMinute()`. Если целевая дата — день весеннего перехода на летнее время,
времени 02:30 не существует (разрыв), и `java.time` сдвигает результат вперёд
на величину разрыва. Напоминание срабатывает на час позже без какого-либо
сигнала. Осенний переход (наложение, время наступает дважды) — наоборот,
неоднозначен: `withHour` сохраняет смещение, если оно валидно, иначе берёт
раннее — какое из двух срабатываний выберется, из кода неочевидно.

**Пример:** `zone = Europe/Berlin`, ежедневное правило, `from` = 2026-03-28
02:30 +01:00. `plusDays(1)` → 29 марта (день перехода, 02:00–03:00 не существует).
`withSameTime` → `withHour(2)` в разрыве → сдвиг → **29 марта 03:30 +02:00**.
Пользователь, просивший 02:30, получит звонок в 03:30. (Сам по себе
`plusDays` уже корректно разрешает разрыв по правилам `java.time`; лишний
`withSameTime` поверх лишь дублирует это неявно.)

**Исправление:** поведение `java.time` по умолчанию (первое валидное время
после разрыва) — приемлемая политика, но она должна быть явной
и покрытой тестом. Вариант с явной политикой:

```kotlin
private fun ZonedDateTime.withSameTime(other: ZonedDateTime): ZonedDateTime {
    var result = this.withHour(other.hour)
        .withMinute(other.minute)
        .withSecond(other.second)
        .withNano(other.nano)
    // Явная политика DST-разрыва: несуществующее время -> первое валидное после разрыва.
    val validOffsets = result.zone.rules.getValidOffsets(result.toLocalDateTime())
    if (validOffsets.isEmpty()) {
        val transition = result.zone.rules.getTransition(result.toLocalDateTime())
        result = result.plusSeconds(transition?.duration?.seconds ?: 3600L)
    }
    return result
}
```

Дешёвая часть исправления — удалить избыточный `withSameTime` после
`plusDays` / `plusWeeks` (они уже сохраняют локальное время) там, где время
не менялось, и оставить его только после `plusDays(delta)` / `withDayOfMonth`.

---

### 6. Неиспользуемый импорт ChronoUnit

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:5`
**Критичность:** низкий

```kotlin
import java.time.temporal.ChronoUnit
```

Импорт не используется ни в одном методе — остатки незавершённого рефакторинга.
Вреда для логики нет, но это шум и признак того, что файл правили впопыхах.

**Исправление:**

```kotlin
import java.time.ZoneId
import java.time.ZonedDateTime
// import java.time.temporal.ChronoUnit — удалить
```

---

### 7. Рассогласование null-значений между toLabel(), serialize() и калькулятором

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:17-42`,
`app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:23-24`
**Критичность:** низкий

**Проблема:** `dayOfWeek` / `dayOfMonth` — nullable, но три потребителя
трактуют `null` по-разному:

- калькулятор: `rule.dayOfWeek ?: 1`, `rule.dayOfMonth ?: 1` (понедельник / 1-е число);
- `toLabel()`: `dayOfWeek = null` → `else -> ""` → ярлык «еженедельно ()»;
  `dayOfMonth = null` → «ежемесячно (null)»;
- `serialize()`: `null` → `"WEEKLY:1:..."` / `"MONTHLY:1:..."`, а `parse()` обратно
  вернёт уже не `null`, а `1` — round-trip не сохраняет значение.

Плюс `toLabel()` для `WEEKLY` при `dayOfWeek` вне 1–7 (возможно до находки 4)
показывает пустое название дня.

**Исправление (точечное):**

```kotlin
RecurrenceType.WEEKLY -> {
    val dayName = when (dayOfWeek) {
        1 -> "пн"; 2 -> "вт"; 3 -> "ср"; 4 -> "чт"
        5 -> "пт"; 6 -> "сб"; 7 -> "вс"
        null -> "пн" // дефолт калькулятора — понедельник
        else -> "?"  // не должно случаться после валидации из находки 4
    }
    ...
}
RecurrenceType.MONTHLY -> {
    val dom = dayOfMonth ?: 1 // дефолт калькулятора
    if (interval == 1) "ежемесячно ($dom)" else "каждые $interval мес. ($dom)"
}
```

---

## Граничные случаи (проверено, не баг)

1. **WEEKDAYS / WEEKENDS не зацикливаются.** Цикл шагает по дню вперёд и выходит
   не более чем за 2 итерации (будни) / 5 итераций (выходные): пятница → +1 = суббота →
   воскресенье → понедельник; воскресенье → … → суббота. Бесконечный цикл невозможен,
   `dayOfWeek.value` всегда 1–7. Корректность переходов проверена: пятница → понедельник,
   суббота → понедельник, воскресенье → понедельник (будни); пятница → суббота,
   суббота → воскресенье, воскресенье → следующая суббота (выходные).
2. **Переход через короткий месяц без дрейфа.** `plusMonths` клампит день
   (31 янв + 1 мес → 28 фев), но исходный `dayOfMonth` хранится отдельно,
   поэтому следующее срабатывание восстанавливается: 31 янв → 28 фев → 31 мар.
   Дрейфа даты (28 фев → 28 мар) нет — это спроектировано правильно.
3. **Конвертация часовых поясов корректна.**
   `ZonedDateTime.ofInstant(Instant.ofEpochMilli(fromMillis), zone)` правильно
   переводит абсолютный момент в локальное время зоны, обратный
   `candidate.toInstant().toEpochMilli()` — тоже. Подозрение из постановки
   («fromMillis в UTC, а zone локальная») не подтвердилось: `Instant` не имеет
   зоны, конвертация однозначна. Реальное замечание — лишь то, что дефолт
   `ZoneId.systemDefault()` вычисляется в момент вызова: при смене часового пояса
   устройства между планированием и срабатыванием «9:00» поплывёт за зоной.
   Это проектное решение (напоминание в локальном времени), а не баг, но его
   стоит зафиксировать в документации метода.
4. **`parse()` корректно возвращает `null`** для `null` / пустой строки /
   неизвестного типа — эти ветви в порядке.
5. **Секунды и наносекунды сохраняются** — `withSameTime` копирует
   час/минуту/секунду/нано, напоминание в 9:00:30 не обрежется до 9:00.
6. **`WEEKDAYS`/`WEEKENDS` игнорируют `interval`, `DAILY` игнорирует
   `dayOfWeek`/`dayOfMonth`** — by design, лишние поля правила для этих типов
   не имеют смысла; молчаливое игнорирование здесь приемлемо.

---

## Дополнительные находки

- `serialize()` / `parse()` согласованы по порядку полей
  (`WEEKLY:dow:interval`, `MONTHLY:dom:interval`) — round-trip корректных значений работает.
- Строгий формат `parse()` (регистрозависимый, без `trim`) приемлем для внутреннего
  формата хранилища, менять не требуется.
- Дефолт `ZoneId.systemDefault()` как параметра затрудняет unit-тестирование:
  рекомендуется в тестах всегда передавать явную зону (например, `ZoneId.of("Europe/Moscow")`)
  и добавить тесты на даты из находок 1–3 (среда→вторник, 5-е→20-е число,
  28.02.2024→29.02.2024, `interval = 0`).
