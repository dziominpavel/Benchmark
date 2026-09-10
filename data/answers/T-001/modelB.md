---
task: T-001
model: modelB
date: 2026-09-10
---

# Ответ на задачу T-001

## Анализ

Проанализированы `RecurrenceCalculator.kt` (80 строк) и `RecurrenceRule.kt` (69 строк)
на коммите `ce2d3f66b2089c7b60073dc2a96899aaa006c9ce`. Проверены: контракт
«строго после `fromMillis`», математика выравнивания на день недели/месяца,
поведение при `interval <= 0`, переходы через короткие месяцы и високосные годы,
DST (gap/overlap), часовые пояса, циклы WEEKDAYS/WEEKENDS, round-trip
сериализации и `toLabel()`.

Главная проблема — общий паттерн «сначала прибавить interval, потом выровнять
день» в `nextWeekly`/`nextMonthly`: из-за него ближайшее срабатывание внутри
текущего периода безвозвратно пропускается.

## Находки

### 1. WEEKLY: пропуск ближайшего срабатывания — результат сдвинут на `interval` недель

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:50`
**Критичность:** критичный
**Описание:** `nextWeekly` сначала делает `from.plusWeeks(interval)`, а уже потом
выравнивается на `dayOfWeek` через `delta`. День недели у `from + N недель` тот же,
что у `from`, поэтому при `targetDow != fromDow` результат всегда равен
`from + 7*interval + delta` вместо `from + delta` — срабатывание в текущей неделе
теряется. Пользователь говорит в понедельник «каждую среду в 9:00» — напоминание
сработает не через 2 дня, а через 9. Ветка `if (!candidate.isAfter(from))` при
`interval >= 1` мёртвая: `candidate` всегда минимум на 7 дней впереди.

**Пример:**
`from` = 2026-09-07 (понедельник) 09:00, `WEEKLY dayOfWeek=3 interval=1`.
Ожидается: 2026-09-09 09:00 (среда этой недели).
Фактически: `plusWeeks(1)` → пн 14.09, `delta=2` → **ср 16.09 09:00** — пропущено
ближайшее срабатывание.

**Исправление:**
```kotlin
private fun nextWeekly(from: ZonedDateTime, dayOfWeek: Int, interval: Int): ZonedDateTime {
    val targetDow = dayOfWeek.coerceIn(1, 7)
    val delta = (targetDow - from.dayOfWeek.value + 7) % 7
    var candidate = from.plusDays(delta.toLong())
    if (!candidate.isAfter(from)) {
        candidate = candidate.plusWeeks(interval.toLong())
    }
    return candidate
}
```
Сначала выравниваемся на ближайший целевой день недели (0–6 дней); только если
это тот же момент (`delta == 0`, то же время), отступаем на `interval` недель.

### 2. MONTHLY: пропуск срабатывания в текущем месяце

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:62`
**Критичность:** критичный
**Описание:** Тот же паттерн: `from.plusMonths(interval)` выполняется до
`withDayOfMonth`. Если `dayOfMonth > from.dayOfMonth` (с учётом клампа к длине
текущего месяца), срабатывание должно произойти в этом же месяце, но код
перепрыгивает на `interval` месяцев вперёд. При `dayOfMonth <= from.dayOfMonth`
результат случайно корректен (для `interval=1`).

**Пример:**
`from` = 2026-01-05 09:00, `MONTHLY dayOfMonth=20 interval=1`.
Ожидается: 2026-01-20 09:00. Фактически: 2026-02-20 09:00.
Ещё хуже: `dayOfMonth=31`, `from` = 05.01 → ожидается 31.01, получаем
`05.02 → clamp → 28.02` — срабатывание и позже, и не на 31-м.

**Исправление:**
```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    val maxDay = from.toLocalDate().lengthOfMonth()
    var candidate = from.withDayOfMonth(dayOfMonth.coerceIn(1, maxDay))
    if (!candidate.isAfter(from)) {
        candidate = from.plusMonths(interval.toLong())
        val newMaxDay = candidate.toLocalDate().lengthOfMonth()
        candidate = candidate.withDayOfMonth(dayOfMonth.coerceIn(1, newMaxDay))
    }
    return candidate
}
```
Проверяем дату в текущем месяце; если она не строго позже `from` — шагаем на
`interval` месяцев и заново клампим день к длине целевого месяца.

### 3. `interval <= 0` не валидируется — нарушение контракта «строго после»

**Файл:** `RecurrenceCalculator.kt:20,30` и `RecurrenceRule.kt:51,58,63`
**Критичность:** критичный
**Описание:** Ни `parse()`, ни `nextOccurrence()` не проверяют `interval`.
- `nextDaily(interval=0)`: `from.plusDays(0).withSameTime(from)` возвращает сам
  `from` — срабатывание «в этот же момент» (alarm ставится в прошлое/сейчас,
  что для AlarmManager означает немедленный выстрел).
- `nextDaily(interval<0)`: дата в прошлом — прямое нарушение контракта.
- `nextWeekly(interval=0)`, `targetDow == fromDow`: `candidate == from` → ветка
  восстановления добавляет `plusWeeks(0)` → всё равно `from` — возвращается
  не-будущее время.
- `interval < 0` в weekly/monthly: `plusWeeks/plusMonths` уходит в прошлое,
  ветка восстановления делает ещё один шаг назад — результата «в будущем» нет.
- `parse("DAILY:0")`, `parse("WEEKLY:2:-3")` молча создают такие правила.

**Пример:**
`parse("DAILY:0")` → `RecurrenceRule(DAILY, interval=0)` →
`nextOccurrence` возвращает `fromMillis` без изменений.

**Исправление:**
```kotlin
fun nextOccurrence(rule: RecurrenceRule, fromMillis: Long, zone: ZoneId = ZoneId.systemDefault()): Long {
    require(rule.interval >= 1) { "interval must be >= 1, got ${rule.interval}" }
    // ... далее без изменений
}
```
И валидация в `parse`:
```kotlin
return when (parts[0]) {
    // ... существующие ветки
    else -> null
}?.takeIf { it.interval >= 1 }
```

### 4. `toLabel()`: «ежемесячно (null)» и пустые скобки для WEEKLY

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:30,23-27`
**Критичность:** низкий
**Описание:** Для `MONTHLY` в строку интерполируется nullable `dayOfMonth`
напрямую — при `dayOfMonth = null` (дефолт) label будет «ежемесячно (null)»,
хотя калькулятор трактует его как 1 (`dayOfMonth ?: 1`). Для `WEEKLY` при
`dayOfWeek` вне 1..7 `dayName = ""` → «еженедельно ()» — пустые скобки в UI.
Расхождение label/калькулятора: калькулятор клампит `dayOfWeek` через
`coerceIn(1,7)` → 7 (воскресенье), а label показывает «()».

**Пример:**
`RecurrenceRule(MONTHLY).toLabel()` → `"ежемесячно (null)"`.

**Исправление:**
```kotlin
RecurrenceType.MONTHLY -> {
    val dom = dayOfMonth ?: 1
    if (interval == 1) "ежемесячно ($dom)" else "каждые $interval мес. ($dom)"
}
// и для WEEKLY:
val dayName = when (dayOfWeek?.coerceIn(1, 7) ?: 1) {
    1 -> "пн"; 2 -> "вт"; 3 -> "ср"; 4 -> "чт"
    5 -> "пт"; 6 -> "сб"; else -> "вс"
}
```

### 5. `serialize()` теряет `interval` для WEEKDAYS/WEEKENDS — round-trip не сохраняет данные

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:37-38`
**Критичность:** низкий
**Описание:** `WEEKDAYS`/`WEEKENDS` сериализуются без полей. Если правило создано
с `interval=2`, после `parse(serialize(rule))` `interval` станет 1 —
несимметрично с DAILY/WEEKLY/MONTHLY. Калькулятор `interval` для этих типов
действительно игнорирует, но потеря поля при round-trip — латентный баг.

**Пример:**
`RecurrenceRule(WEEKDAYS, interval=2).serialize()` → `"WEEKDAYS"` →
`parse(...)` → `interval=1`.

**Исправление:**
```kotlin
RecurrenceType.WEEKDAYS -> "WEEKDAYS:$interval"
RecurrenceType.WEEKENDS -> "WEEKENDS:$interval"
// и в parse читать parts.getOrNull(1) по аналогии с DAILY
```

### 6. `parse()` молча подставляет дефолты на повреждённых данных

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceRule.kt:51,57-58,62-63`
**Критичность:** низкий
**Описание:** `parts.getOrNull(N)?.toIntOrNull() ?: 1` превращает любой мусор в
валидное правило: `"DAILY:abc"` → interval=1, `"WEEKLY:99:1"` → dayOfWeek=99
(калькулятор склампит к 7, label покажет «()» — см. находку 4),
`"MONTHLY:0:1"` → dayOfMonth=0 → кламп к 1. Ошибки в данных маскируются
вместо того, чтобы вернуть `null`. Также `parse` принимает `interval <= 0`
(находка 3) и `dayOfMonth` вне 1..31 без валидации.

**Пример:**
`parse("WEEKLY:99:1")` → правило с `dayOfWeek=99` — не `null`.

**Исправление:**
```kotlin
return when (parts[0]) {
    // ... ветки без изменений
    else -> null
}?.takeIf {
    it.interval >= 1 &&
        (it.dayOfWeek == null || it.dayOfWeek in 1..7) &&
        (it.dayOfMonth == null || it.dayOfMonth in 1..31)
}
```

### 7. Мёртвый код: ветки восстановления `if (!candidate.isAfter(from))` недостижимы при `interval >= 1`

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:55-57,66-70`
**Критичность:** низкий
**Описание:** В `nextWeekly` `candidate >= from + 7*interval` дней — всегда
строго позже `from`; в `nextMonthly` `candidate` минимум на месяц впереди —
`withDayOfMonth` внутри того же месяца не может вернуть его раньше `from`.
Обе ветки существуют только для случая `interval <= 0`, в котором они не
помогают (добавляют 0 или отрицательное число). Код создаёт ложное ощущение
защиты. После исправлений 1–2 эти ветки станут осмысленными (проверка даты
в текущем периоде), но в текущем виде — мёртвый код.

**Исправление:** см. находки 1 и 2 — корректная реализация делает проверку
`isAfter` реально нужной.

### 8. DST gap: срабатывание в «несуществующее» локальное время сдвигается вперёд

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:74-79`
**Критичность:** низкий
**Описание:** `withSameTime` (и `plusDays/plusWeeks/plusMonths` у
`ZonedDateTime`) сохраняют локальное время. Если целевое время попадает в
DST-gap (напр., 02:30 в день перевода стрелок вперёд в `America/New_York`),
`java.time` разрешает неоднозначность сдвигом вперёд на длину gap →
срабатывание в 03:30. Напоминание сработает на час позже — приемлемое
поведение (лучше, чем пропуск), но оно нигде не документировано. Отдельно:
`withSameTime(from)` после `plusDays` в `nextDaily`/`nextWeekdays`/`nextWeekends`
— избыточный no-op, т.к. `plusDays` уже сохраняет локальное время.

**Пример:**
`from` = 2026-03-07 02:30 `America/New_York`, `DAILY interval=1` →
кандидат 2026-03-08 02:30 не существует → фактически 03:30 EDT.

**Исправление:** поведение оставить, зафиксировать в KDoc:
```kotlin
/**
 * ... Если локальное время срабатывания попадает в DST-gap, оно сдвигается
 * вперёд на длину разрыва (например, 02:30 -> 03:30 при переходе на летнее время).
 */
```

## Граничные случаи (проверено, не баг)

- **`dayOfMonth=31` в коротком месяце + дрейф якоря.** `from` = 31.01, `dom=31`:
  `plusMonths(1)` клампится к 28.02 → `withDayOfMonth(min(31,28))` → 28.02.
  Следующий вызов от 28.02: `plusMonths(1)` = 28.03 → `withDayOfMonth(31)` →
  **31.03** — якорь 31 восстанавливается, дрейфа на 28-е нет. Кламп к последнему
  дню месяца — разумная семантика.
- **Високосный год:** `from` = 29.02.2024, `dom=29` → март 2024 имеет 31 день →
  29.03; через год `from` = 29.01.2025 → февраль 2025: кламп к 28.02 — корректно.
- **`dayOfWeek` вне 1..7** в `nextWeekly` — `coerceIn(1,7)` молча клампит
  (0→1, 9→7). Работает, но расходится с `toLabel` (находка 4) и `parse`
  (находка 6).
- **Циклы WEEKDAYS/WEEKENDS** — `while` по `dayOfWeek.value` терминируется
  максимум за 6 итераций (день недели монотонно цикличен 1..7), бесконечного
  цикла нет. Результат всегда `>= from + 1 день` — контракт «строго после»
  соблюдён. Пятница → понедельник, суббота → понедельник (WEEKDAYS);
  воскресенье → суббота через 6 дней (WEEKENDS) — верно.
- **Часовые пояса:** `fromMillis` — instant (UTC), корректно конвертируется в
  `zone` через `ZonedDateTime.ofInstant`; все вычисления идут в локальных
  терминах целевой зоны, результат — снова instant. Правило «в 9:00 по
  America/New_York» вычисляется по нью-йоркскому календарю — корректно.
- **DST overlap (осень):** при неоднозначном локальном времени выбирается более
  ранний offset — срабатывание происходит один раз, не дублируется.
- **`targetDow == fromDow` в WEEKLY при `interval >= 1`:** `delta=0`,
  `candidate = from + 7*interval` — единственная ветка, где текущий код даёт
  верный ответ (строго после).
- **`dayOfMonth <= from.dayOfMonth` в MONTHLY при `interval=1`:** например
  `from` = 25.01, `dom=10` → 10.02 — корректно (10.01 уже в прошлом). Баг №2
  проявляется только когда срабатывание есть в текущем месяце.

## Дополнительные находки

- **Неиспользуемый импорт** `java.time.temporal.ChronoUnit` —
  `RecurrenceCalculator.kt:5`, нигде не используется.
- **`java.time.Instant` через FQN** (строка 18) при импортированных `ZoneId`/
  `ZonedDateTime` — непоследовательный стиль; стоит добавить `import java.time.Instant`.
- **Молчаливый дефолт `dayOfWeek ?: 1` / `dayOfMonth ?: 1`** (строки 23–24):
  `WEEKLY` без дня недели превращается в «по понедельникам» — маскирует
  незаполненное поле; логичнее `requireNotNull` или явная валидация правила.
- `withSameTime` копирует hour/minute/second/nano, но не проверяет зону `other` —
  сейчас безопасно (всегда вызывается с `from` той же зоны), но как
  extension-функция общего вида хрупкая.
