---
task: T-001
model: modelB
date: 2026-09-07
---

# Ответ на задачу T-001

## Анализ

Проанализированы два файла на коммите `ce2d3f6`:

- `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt` — вычисление
  следующего срабатывания для типов DAILY / WEEKDAYS / WEEKENDS / WEEKLY / MONTHLY,
  вспомогательный `withSameTime`.
- `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt` — модель правила,
  `toLabel()`, `serialize()`, `parse()`.

Контракт (из док-комментария к `nextOccurrence`): результат — **ближайшее будущее**
срабатывание **строго после** `fromMillis`. Все находки проверялись ручной трассировкой
по датам (понедельник 2026-09-07, високосный 2024, DST Europe/Berlin 29.03.2026 /
25.10.2026).

Найдено **6 багов**: 3 критичных, 3 низкой критичности. Кроме того, проверено 8 граничных
случаев, которые работают корректно (переход 31 января → февраль, високосный год, DST,
зацикливание WEEKDAYS/WEEKENDS и др.).

## Находки

### 1. interval = 0 или отрицательный — нарушение контракта «строго после» (DAILY, WEEKLY, MONTHLY)

**Файлы:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:29-31`,
`:49-58`, `:61-71`
**Критичность:** критичный

**Описание:** Нигде в калькуляторе не проверяется `interval >= 1`.

- `nextDaily(from, 0)` → `from.plusDays(0)` = `from` — возвращается **тот же самый момент**
  `fromMillis`, результат не строго после.
- `nextDaily(from, -3)` → дата в **прошлом**.
- `nextWeekly(from, dow, 0)`: если `delta == 0` (целевой день = день `from`), то после
  `candidate.plusWeeks(0)` кандидат по-прежнему равен `from` — и возвращается как есть.
- `nextMonthly(from, dom, 0)`: кандидат == `from`, ветка `if (!candidate.isAfter(from))`
  прибавляет `plusMonths(0)` — снова `from`. Возвращается невалидный результат.

Для планировщика это означает alarm на момент «сейчас/в прошлом» → немедленное
срабатывание и потенциальный цикл срабатывание → перепланирование → немедленное
срабатывание (каждый `nextOccurrence` от времени последнего fire возвращает то же
или прошедшее время).

**Пример:**
```
from = 2026-09-07T10:00 Europe/Moscow (fromMillis = соответствующий epoch ms)
rule = RecurrenceRule(DAILY, interval = 0)
nextOccurrence(...) → ровно fromMillis (ожидалось: 2026-09-08T10:00 или ошибка)

rule = RecurrenceRule(MONTHLY, dayOfMonth = 7, interval = 0)
from = 2026-09-07T10:00
→ возвращает 2026-09-07T10:00 (== from), т.к. plusMonths(0) ничего не меняет,
а вторая ветка тоже прибавляет 0 месяцев.
```

**Исправление:**

```kotlin
private fun nextDaily(from: ZonedDateTime, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1)
    return from.plusDays(step.toLong()).withSameTime(from)
}

// аналогично в nextWeekly / nextMonthly:
// val step = interval.coerceAtLeast(1) — использовать вместо interval
```

Оптимально — запретить невалидный интервал в самой модели (см. находку 2):

```kotlin
init {
    require(interval >= 1) { "interval must be >= 1, was $interval" }
}
```

### 2. `RecurrenceRule.parse()` не валидирует interval / dayOfWeek / dayOfMonth

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:45-67`
**Критичность:** критичный

**Описание:** `parse()` — единственный путь восстановления правила из БД
(`serialize()` пишется в `Reminder`). Проверяется только «строка парсится как Int»,
но не диапазон значений:

- `"DAILY:0"` / `"DAILY:-2"` → `interval = 0` / `-2` → активирует баг из находки 1.
  Заметим: `?:` подменяет только **непарсящееся** значение дефолтом, а `0` и `-2`
  парсятся успешно и проходят дальше.
- `"WEEKLY:99:1"` → `dayOfWeek = 99`. Калькулятор **молча** зажимает его в 1..7
  (`coerceIn`), т.е. `99` превращается в воскресенье; `toLabel()` при этом выводит
  пустое имя дня — см. находку 4.
- `"MONTHLY:0:1"` → `dayOfMonth = 0` → молча превращается в 1 число.
- `"MONTHLY:32:1"` → молча зажимается в последний день месяца.

Молчаливая подмена маскирует повреждённые данные и приводит к неожиданным для
пользователя датам срабатывания.

**Пример:**
```
RecurrenceRule.parse("DAILY:0")  -> RecurrenceRule(DAILY, interval=0)  // должен быть null или 1
RecurrenceRule.parse("WEEKLY:99:1") -> dayOfWeek=99 // молча станет воскресеньем
```

**Исправление:**

```kotlin
companion object {
    fun parse(serialized: String?): RecurrenceRule? {
        if (serialized.isNullOrBlank()) return null
        val parts = serialized.split(":")
        fun intervalAt(index: Int): Int =
            parts.getOrNull(index)?.toIntOrNull()?.takeIf { it >= 1 } ?: 1
        return when (parts[0]) {
            "DAILY" -> RecurrenceRule(
                type = RecurrenceType.DAILY,
                interval = intervalAt(1),
            )
            "WEEKDAYS" -> RecurrenceRule(type = RecurrenceType.WEEKDAYS)
            "WEEKENDS" -> RecurrenceRule(type = RecurrenceType.WEEKENDS)
            "WEEKLY" -> RecurrenceRule(
                type = RecurrenceType.WEEKLY,
                dayOfWeek = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it in 1..7 } ?: 1,
                interval = intervalAt(2),
            )
            "MONTHLY" -> RecurrenceRule(
                type = RecurrenceType.MONTHLY,
                dayOfMonth = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it in 1..31 } ?: 1,
                interval = intervalAt(2),
            )
            else -> null
        }
    }
}
```

### 3. `nextWeekly` всегда пропускает текущую неделю, если целевой день позже дня `from`

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:49-58`
**Критичность:** критичный

**Описание:** Сначала прибавляется `interval` недель (`from.plusWeeks(interval)`), и только
потом кандидат выравнивается на `dayOfWeek` внутри уже «следующей» недели. Если целевой
день недели наступает позже в этой же неделе (и строго после `from`), ближайшее
срабатывание теряется — результат уходит лишних 7 дней вперёд. Это ломает основной
сценарий продукта: «каждый вторник в 9:00» в понедельник 10:00 назначается не на завтра,
а через 8 дней. Заодно видно, что проверка `if (!candidate.isAfter(from))` для
`interval >= 1` — мёртвая ветка (кандидат всегда минимум через 7 дней), т.е. логика
сконструирована в неверном порядке: выравнивание на день недели должно происходить
**перед** добавлением интервала.

**Пример:**
```
from = понедельник 2026-09-07T10:00
rule = RecurrenceRule(WEEKLY, dayOfWeek = 2 /* вт */, interval = 1)

Ожидание (ближайшее будущее): вторник 2026-09-08T10:00 (+1 день)
Фактически:                  вторник 2026-09-15T10:00 (+8 дней)

Аналогично from = пн, dayOfWeek = 7 (вс): ожидание +6 дней, фактически +13 дней.
```

**Исправление:**

```kotlin
private fun nextWeekly(from: ZonedDateTime, dayOfWeek: Int, interval: Int): ZonedDateTime {
    val step = interval.coerceAtLeast(1)
    val targetDow = dayOfWeek.coerceIn(1, 7)
    val delta = (targetDow - from.dayOfWeek.value + 7) % 7
    var candidate = from.plusDays(delta.toLong()).withSameTime(from)
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusWeeks(step.toLong())
    }
    return candidate
}
```

Здесь сначала берётся ближайший целевой день недели от `from` (включая сегодня); если он
не строго после `from` (совпал по времени), сдвигаемся ровно на `step` недель — контракт
выполняется при любом `step >= 1`.

### 4. `toLabel()` выводит `ежемесячно (null)` и пустые скобки для WEEKLY

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:23-30`
**Критичность:** низкий

**Описание:**
- `MONTHLY` интерполирует `dayOfMonth` без проверки: при `dayOfMonth = null`
  (значение по умолчанию у `RecurrenceRule(MONTHLY)`) пользователь видит
  **«ежемесячно (null)»**.
- `WEEKLY`: если `dayOfWeek == null` или вне 1..7 (см. находку 2), `dayName = ""`,
  и label становится «еженедельно ()» с пустыми скобками.

**Пример:**
```
RecurrenceRule(MONTHLY, interval = 1).toLabel()      -> "ежемесячно (null)"
RecurrenceRule(WEEKLY, dayOfWeek = 99).toLabel()     -> "еженедельно ()"
```

**Исправление:**

```kotlin
RecurrenceType.WEEKLY -> {
    val dayName = when (dayOfWeek) {
        1 -> "пн"; 2 -> "вт"; 3 -> "ср"; 4 -> "чт"
        5 -> "пт"; 6 -> "сб"; 7 -> "вс"
        else -> null
    }
    val suffix = dayName?.let { " ($it)" } ?: ""
    if (interval == 1) "еженедельно$suffix" else "каждые $interval нед.$suffix"
}
RecurrenceType.MONTHLY -> {
    val day = dayOfMonth ?: 1
    if (interval == 1) "ежемесячно ($day)" else "каждые $interval мес. ($day)"
}
```

### 5. WEEKDAYS/WEEKENDS игнорируют `interval` и не сохраняют его в `serialize()`

**Файлы:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:33-47`,
`app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:37-38`
**Критичность:** низкий

**Описание:** В `RecurrenceRule` поле `interval` существует для всех типов, но
`WEEKDAYS`/`WEEKENDS` сериализуются как `"WEEKDAYS"` / `"WEEKENDS"` без интервала, и
`nextWeekdays`/`nextWeekends` его не принимают. Правило `RecurrenceRule(WEEKDAYS,
interval = 3)` теряет интервал при сериализации (round-trip вернёт `interval = 1`).
Либо интервал для этих типов должен быть запрещён явно, либо сериализован и учтён —
сейчас это тихая потеря данных модели.

**Пример:**
```
RecurrenceRule(WEEKDAYS, interval = 3).serialize()              -> "WEEKDAYS"
RecurrenceRule.parse("WEEKDAYS")                                -> interval == 1
```

**Исправление (вариант с сохранением интервала):**

```kotlin
RecurrenceType.WEEKDAYS -> "WEEKDAYS:$interval"
RecurrenceType.WEEKENDS -> "WEEKENDS:$interval"
// в parse(): WEEKDAYS/WEEKENDS читают intervalAt(1) с дефолтом 1,
// nextWeekdays/nextWeekends — принимают step = interval.coerceAtLeast(1)
// и шагают по 7-day циклу с подсчётом подходящих дней.
```

### 6. Неиспользуемый импорт `ChronoUnit`

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:5`
**Критичность:** низкий

**Описание:** `import java.time.temporal.ChronoUnit` не используется нигде в файле.
Заодно: `java.time.Instant` в строке 18 использован с полной квалификацией, хотя
`ZoneId`/`ZonedDateTime` импортированы — единообразнее вынести в import.

**Исправление:**

```kotlin
import java.time.Instant
import java.time.ZoneId
import java.time.ZonedDateTime
// строку ChronoUnit — удалить; в теле: Instant.ofEpochMilli(fromMillis)
```

## Граничные случаи (проверено, не баг)

1. **MONTHLY 31 января → февраль**: `from = 2024-01-31`, `dayOfMonth = 31`:
   `plusMonths(1)` сам зажимает до 2024-02-29 (високосный) / 2023-02-28 (обычный),
   `coerceIn(1, lengthOfMonth())` повторно ограничивает. Работает корректно.
2. **MONTHLY не «прилипает» к 28/29 числу**: следующая итерация от 2024-02-29 снова
   берёт `rule.dayOfMonth = 31` (а не текущий день кандидата) → 2024-03-31. Цепочка
   восстанавливается на исходный день.
3. **Високосный 29 февраля**: `MONTHLY dayOfMonth = 29` в невисокосный год корректно
   зажимается до 28 февраля, в високосный — остаётся 29.
4. **DST весна (Europe/Berlin, 29.03.2026, час 02:30 не существует)**: `plusDays` на
   `ZonedDateTime` сохраняет локальное wall-time и корректирует offset; при прямом
   попадании в gap `withHour/withMinute` сдвигает вперёд по длине gap → 03:30.
   Напоминание сработает один раз, с ожидаемым для пользователя временем
   (документированное поведение java.time).
5. **DST осень (25.10.2026, 02:30 существует дважды)**: `ZonedDateTime` выбирает более
   ранний offset (летний) — срабатывание ровно один раз. Поведение детерминированно.
6. **fromMillis в UTC + локальная zone**: `ZonedDateTime.ofInstant(Instant..., zone)`
   корректно конвертирует абсолютный момент в локальное время; дальнейшая арифметика
   календарная (wall-time), что правильно для напоминалок «в 9:00».
7. **WEEKDAYS / WEEKENDS не зацикливаются**: `dayOfWeek.value` ограничен 1..7, шаг
   `plusDays(1)` гарантированно выходит на подходящий день максимум за 2 (будни) и 5
   (выходные) итерации. Время суток сохраняется через `withSameTime`.
8. **`parse()` для мусорных входов**: `null` / пустая строка / неизвестный тип → `null`;
   отсутствующие хвосты (`"DAILY"`, `"WEEKLY"`) → дефолты `1`; нечисловой интервал
   (`"DAILY:abc"`) → дефолт `1`. Падений нет (проблема только в отсутствии проверки
   диапазона — находка 2).

## Дополнительные находки

- **Мёртвая ветка `if (!candidate.isAfter(from))`** в `nextWeekly` (строки 55-57) и
  `nextMonthly` (66-70) для `interval >= 1`: после `plusWeeks/plusMonths(interval)`
  кандидат всегда минимум на период впереди `from`, условие никогда не срабатывает.
  Это симптом неверного порядка операций (находка 3), отдельного исправления не требует.
- **`serialize()`/`parse()` round-trip** для валидных правил (DAILY/WEEKLY/MONTHLY)
  корректен; round-trip ломается только для WEEKDAYS/WEEKENDS с нестандартным
  интервалом (находка 5).
- **Точность времени не дрейфует**: `withSameTime` копирует час/минуту/секунду/нано
  у `from`, миллисекунды сохраняются через всю цепочку перепланирований.
- **Стиль**: смешение полного квалификатора `java.time.Instant` и импортов — см.
  находку 6.
- Немецкая/английская локализация label'ов в `toLabel()` отсутствует, но по правилам
  проекта UI-тексты — на русском, это соответствует требованиям.
