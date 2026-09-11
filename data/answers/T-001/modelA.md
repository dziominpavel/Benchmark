---
task: T-001
model: modelA
date: 2026-09-11
---

# Ответ на задачу T-001

## Анализ

Проанализированы `RecurrenceCalculator.kt` и `RecurrenceRule.kt` на baseline-коммите
`ce2d3f66b2089c7b60073dc2a96899aaa006c9ce` (совпадает с HEAD проекта VoiceMind на момент
анализа, рабочее дерево чистое). Дополнительно проверены call-sites, чтобы оценить
достижимость сценариев:

- `ReminderAlarmReceiver.kt:83-94` — пересчёт следующего срабатывания после alarm,
  `from = System.currentTimeMillis()`, зона по умолчанию (system default);
- `ReminderRepository.kt:107-120` — `rescheduleAll()` пересчитывает правило при
  `fireAt <= now`; вызывается из `VoiceMindApplication.kt:33` (старт приложения)
  и `BootReceiver.kt:24` (boot / package replaced);
- `ReminderScheduler.kt:18-22` — напоминание с `fireAt <= now` молча **не планируется**;
- `ReminderRepository.kt:144-147` — `updateAndSchedule` тоже не ставит alarm для `fireAt <= now`;
- `ReminderParser.kt:156-202` — штатный парсер всегда создаёт правило с `interval = 1`
  (сериализация `DAILY:1`, `WEEKLY:d:1`, `MONTHLY:d:1`), т.е. `interval <= 0` или
  выход за диапазон `dayOfWeek`/`dayOfMonth` возможны только из повреждённых/легаси-данных БД.

**Методика и ограничения проверки.** Gradle-тесты проекта не запускались. Семантика
`java.time`, на которую опирается калькулятор, проверена вне проекта на локальном JVM
(JDK 25) точной Java-трансляцией baseline-логики (`_probe/RecurrenceProbe.java` в отдельной
копии репозитория `.devin/cache/benchmark/T-001/modelA-run-20260911`, созданной через
`git clone --no-local --no-checkout` + checkout baseline; Kotlin вызывает те же методы JDK,
поэтому результаты переносимы). Android-часть (AlarmManager) не исполнялась. Все 10 кейсов
существующего `RecurrenceCalculatorTest` воспроизведены трансляцией — результаты совпадают
с ожиданиями тестов (сами тесты не запускались). Ниже «проверено на JVM» означает эту проверку.

## Находки

### 1. WEEKLY: пропускается ближайшее срабатывание (лишняя неделя)

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:49-59`
**Критичность:** средний

**Описание:** `nextWeekly` сначала прыгает на `interval` недель от `from`
(`from.plusWeeks(interval)`), и только затем выравнивается на `dayOfWeek`. Если `from`
попадает на день недели **раньше** целевого в текущей неделе, ближайшее срабатывание
пропускается — возвращается дата на 1–2 недели позже. KDoc обещает «ближайшее будущее
срабатывание», в т.ч. для пропущенных (см. тест `skipped_occurrence_jumps_to_future`),
поэтому это дефект, а не задумка. В штатном цикле (пересчёт сразу после срабатывания,
когда `from` — целевой день недели) не проявляется; достижим при восстановлении
пропущенных срабатываний (`rescheduleAll` на старте приложения/boot) и при доставке
alarm после полуночи (Doze/OEM-задержки).

**Пример:** правило «каждую субботу 09:00» (`WEEKLY:6:1`), восстановление в среду
17.06.2026 09:00:
- ожидается сб 20.06.2026 09:00 (ближайшая суббота, +72 ч);
- фактически (проверено на JVM): сб 27.06.2026 09:00 (+240 ч) — суббота 20.06 пропущена.

Дополнительно проверено: from=пт 19.06 → 27.06 (суббота 20.06 пропущена); from=ср 17.06
при `interval=2` → 04.07.

**Исправление:** выравнивать от `from` в текущей неделе, а `interval` добавлять только
если ближайшая дата не строго после `from`:

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

Существующий тест `weekly_sameDay` (from=Fri → Fri+7) остаётся зелёным: `delta=0` →
candidate == from → `plusWeeks(interval)`. Примечание: для `interval > 1` фаза цикла
определяется последним срабатыванием, которого в API нет; при восстановлении пропуска
фаза неоднозначна — выравнивание даёт «ближайшее будущее», что соответствует KDoc.
Полный учёт фазы требует передачи планового времени (см. находку 4).

### 2. MONTHLY: пропускается ближайшее срабатывание (лишний месяц)

**Файл:** `app/src/main/java/com/example/voicemind/data/RecurrenceCalculator.kt:61-72`
**Критичность:** средний

**Описание:** `nextMonthly` сначала прыгает на `interval` месяцев, затем ставит
`dayOfMonth`. Если в текущем месяце `from` раньше целевого дня, текущий месяц
пропускается: срабатывание уезжает на месяц вперёд. Достижимость та же — восстановление
пропущенного срабатывания / поздняя доставка.

**Пример:** правило «каждое 15-е» (`MONTHLY:15:1`), восстановление 05.06.2026 10:00:
- ожидается 15.06.2026 10:00 (+240 ч);
- фактически (проверено на JVM): 15.07.2026 10:00 (+960 ч) — ближайшее 15-е пропущено.

Ещё проверено: from=30.01.2026, day=31 → ожидается 31.01 (ближайшее), фактически 28.02;
from=05.08, day=20 → 20.09 вместо 20.08.

**Исправление:** сначала выравнивание в текущем месяце (с клампом по длине месяца),
затем прыжок на `interval`:

```kotlin
private fun nextMonthly(from: ZonedDateTime, dayOfMonth: Int, interval: Int): ZonedDateTime {
    val targetDay = dayOfMonth.coerceIn(1, from.toLocalDate().lengthOfMonth())
    var candidate = from.withDayOfMonth(targetDay)
    if (!candidate.isAfter(from)) {
        candidate = from.plusMonths(interval.toLong())
        candidate = candidate.withDayOfMonth(
            dayOfMonth.coerceIn(1, candidate.toLocalDate().lengthOfMonth()),
        )
    }
    return candidate
}
```

Существующие тесты остаются зелёными: `monthly_sameDay` (15.06 → 15.07),
`monthly_31st_coerces` (31.01 → 28.02); кламп коротких месяцев и отсутствие «дрейфа»
дня сохраняются (28.02 → 31.03).

### 3. interval <= 0: нарушение контракта «строго после» → «застревание» напоминания

**Файл:** `RecurrenceCalculator.kt:29-31` (nextDaily), `:49-59` (nextWeekly),
`:61-72` (nextMonthly); источник — `RecurrenceRule.kt:45-67` (parse без валидации)
**Критичность:** критичный (по последствиям; достижим только при некорректных данных —
штатный парсер всегда пишет `interval = 1`)

**Описание:** KDoc обещает «строго после fromMillis», но:
- `nextDaily(interval=0)` → `from.plusDays(0)` = ровно `from` → возвращается `fromMillis`;
- `nextWeekly(interval=0)` при `dayOfWeek == dow(from)` → ровно `from`; при
  `interval < 0` (weekly/monthly тоже) — дата в прошлом;
- `nextMonthly(interval=0)` при `dayOfMonth <= day(from)` → ровно `from` или прошлое
  (from=20.03, day=15 → 15.03 — в прошлом).

Последствие в приложении: `fireAt = now/прошлое` → `updateAndSchedule`
(`ReminderRepository.kt:144-147`) и `ReminderScheduler.schedule` (`:18-22`) молча не ставят
alarm для `fireAt <= now` → повторяющееся напоминание **перестаёт срабатывать** (PENDING
с прошедшим fireAt), причём повторные `rescheduleAll` дают то же прошедшее значение.

Проверено на JVM: daily interval=0 → delta 0 ч, `strictAfter=false`; interval=-1 → −24 ч;
weekly interval=0 (dow=5, from=Fri) → delta 0 ч, `strictAfter=false`; monthly interval=0
(from=20.03, day=15) → −120 ч.

**Исправление:** защитный кламп в калькуляторе + валидация interval в `parse`:

```kotlin
// RecurrenceCalculator.nextOccurrence (фрагмент)
val interval = rule.interval.coerceAtLeast(1)
val candidate = when (rule.type) {
    RecurrenceType.DAILY -> nextDaily(from, interval)
    RecurrenceType.WEEKDAYS -> nextWeekdays(from)
    RecurrenceType.WEEKENDS -> nextWeekends(from)
    RecurrenceType.WEEKLY -> nextWeekly(from, rule.dayOfWeek ?: 1, interval)
    RecurrenceType.MONTHLY -> nextMonthly(from, rule.dayOfMonth ?: 1, interval)
}
```

```kotlin
// RecurrenceRule.parse (фрагмент: interval)
"DAILY" -> RecurrenceRule(
    type = RecurrenceType.DAILY,
    interval = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it >= 1 } ?: 1,
)
```

### 4. Время суток берётся из момента пересчёта (`fromMillis`), а не из планового времени: дрейф и «залипание» после DST

**Файл:** `RecurrenceCalculator.kt:29-31, 49-59, 61-72, 74-79`; вызовы —
`ReminderAlarmReceiver.kt:85-88`, `ReminderRepository.kt:113`
**Критичность:** средний

**Описание:** все ветки берут время суток из `from`; `withSameTime(from)` — фактически
no-op, т.к. `plusDays/plusWeeks/plusMonths` уже сохраняют локальное время. Вызовы передают
`System.currentTimeMillis()`, поэтому:
1. **Поздняя доставка / восстановление.** Если alarm доставлен позже (Doze,
   OEM-оптимизации) или пропущенное срабатывание восстанавливается при старте приложения,
   время суток навсегда сдвигается на момент пересчёта: «каждый день в 9:00», телефон был
   выключен, старт приложения в 14:20 → следующее срабатывание «завтра 14:20» вместо
   «завтра 9:00» (проверено на JVM: daily от 14:20 → 14:20 следующих суток).
2. **DST-gap.** В день весеннего перехода несуществующее локальное время (02:30)
   java.time сдвигает вперёд → срабатывание в 03:30; на следующем цикле `from` уже 03:30,
   поэтому напоминание остаётся в 03:30 навсегда. `withSameTime(from)` восстановить 02:30
   не может (проверено: `29.03 03:30+02:00.withHour(2).withMinute(30)` → снова 03:30 —
   gap-разрешение). Для 09:00 перехода не видно: wall time сохраняется (в сутках перехода
   23 ч) — проверено.

**Пример:** Europe/Berlin, daily 02:30: 28.03 02:30 → 29.03 **03:30** → 30.03 **03:30** →
… (ожидалось: 29.03 — ближайшее существующее 03:30, но 30.03 — снова 02:30). Аналогично
WEEKDAYS: пт 02:30 → пн **03:30** (проверено).

**Исправление (в рамках файла):** сделать время суток явным «якорем» (по умолчанию —
`fromMillis`, обратная совместимость) и использовать его во всех ветках; вызовы должны
передавать плановое время `reminder.fireAt`:

```kotlin
fun nextOccurrence(
    rule: RecurrenceRule,
    fromMillis: Long,
    zone: ZoneId = ZoneId.systemDefault(),
    anchorMillis: Long = fromMillis,   // плановое время срабатывания (fireAt)
): Long {
    val from = ZonedDateTime.ofInstant(Instant.ofEpochMilli(fromMillis), zone)
    val anchor = ZonedDateTime.ofInstant(Instant.ofEpochMilli(anchorMillis), zone)
    val interval = rule.interval.coerceAtLeast(1)
    val candidate = when (rule.type) {
        RecurrenceType.DAILY -> nextDaily(from, anchor, interval)
        RecurrenceType.WEEKDAYS -> nextWeekdays(from, anchor)
        RecurrenceType.WEEKENDS -> nextWeekends(from, anchor)
        RecurrenceType.WEEKLY -> nextWeekly(from, anchor, rule.dayOfWeek ?: 1, interval)
        RecurrenceType.MONTHLY -> nextMonthly(from, anchor, rule.dayOfMonth ?: 1, interval)
    }
    return candidate.toInstant().toEpochMilli()
}

private fun nextDaily(from: ZonedDateTime, anchor: ZonedDateTime, interval: Int): ZonedDateTime =
    from.withSameTime(anchor).plusDays(interval.toLong())
```

В остальных трёх функциях базой становится `from.withSameTime(anchor)` (одна точечная
замена выражения; проверка `!candidate.isAfter(from)` сохраняется). Это устраняет дрейф
при поздней доставке/восстановлении (якорь `fireAt` хранит плановое время). Полное
восстановление часа после DST-gap требует хранить исходное локальное время (новое поле
в `Reminder`/правиле) — это вне двух анализируемых файлов; правка вызовов — тоже вне
области задачи, но без неё параметр не даёт эффекта.

### 5. Валидация значений правила отсутствует: parse принимает мусор, калькулятор молча нормализует

**Файл:** `RecurrenceRule.kt:45-67` (parse), `RecurrenceCalculator.kt:51, 64, 69` (coerceIn)
**Критичность:** средний

**Описание:** `parse` не проверяет диапазоны и не сообщает о некорректных данных:
- `"DAILY:0"`, `"WEEKLY:5:-1"`, `"MONTHLY:15:0"` → правило с `interval <= 0` (см. находку 3);
- `"WEEKLY:0:1"` / `"WEEKLY:9:1"` → `dayOfWeek` вне 1–7, калькулятор молча зажимает
  (`coerceIn(1, 7)`): 0 → понедельник, 9 → воскресенье;
- `"MONTHLY:0:1"` → день 0 молча становится 1-м; `"MONTHLY:99:1"` → молча «последний день
  месяца» (в феврале 28, в апреле 30 — непоследовательно);
- `"DAILY:abc"` → молча interval=1; `"daily:1"`, `" DAILY:1"` → null (регистр/пробелы);
  `"DAILY:1:9"` → лишние части игнорируются.

**Пример (проверено на JVM):** `"WEEKLY:9:1"` от субботы 20.06 → 28.06 (правило незаметно
превратилось в воскресенье); `"MONTHLY:99:1"` от 20.03 → 30.04 (вместо 31-го — 30-е).

**Исправление:** валидировать/нормализовать на входе (единственная точка чтения данных
из БД), `coerceIn` в калькуляторе оставить только как страховку от исключений:

```kotlin
fun parse(serialized: String?): RecurrenceRule? {
    if (serialized.isNullOrBlank()) return null
    val parts = serialized.trim().split(":")
    return when (parts[0]) {
        "DAILY" -> RecurrenceRule(
            type = RecurrenceType.DAILY,
            interval = parts.getOrNull(1)?.toIntOrNull()?.takeIf { it >= 1 } ?: 1,
        )
        "WEEKDAYS" -> RecurrenceRule(type = RecurrenceType.WEEKDAYS)
        "WEEKENDS" -> RecurrenceRule(type = RecurrenceType.WEEKENDS)
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
        else -> null
    }
}
```

`require(...)` в `init` data-класса не предлагаю: он бросит исключение на легаси-строке
в receiver; нормализация с fallback-дефолтом безопаснее.

## Граничные случаи (проверено, не баг)

1. **WEEKDAYS/WEEKENDS — циклы корректны и завершаются** (`RecurrenceCalculator.kt:33-47`):
   не более 2/5 итераций, зацикливание невозможно; результат строго после `from`.
   Проверено на JVM: Fri→Mon (+72 ч), Mon→Tue (+24 ч), Sat→Mon (+48 ч);
   Fri→Sat (+24 ч), Sun→Sat (+144 ч), Sat→Sun (+24 ч). Совпадает с существующими тестами.
2. **DAILY при interval >= 1** — переход через месяц/год и 29 февраля корректен
   (`plusDays` — календарный), «строго после» соблюдается.
3. **MONTHLY: кламп коротких месяцев работает** (`:61-72`): 31.01.2026 → 28.02.2026,
   31.01.2028 → 29.02.2028 (високосный), day=30 от 31.01 → 28.02. «Дрейфа» дня нет:
   после 28.02 следующий — 31.03 (целевой день берётся из правила, а не из `from`).
   Проверено на JVM; соответствует тестам `monthly_sameDay`, `monthly_31st_coerces`.
4. **Часовые пояса** (`:18`): `ZonedDateTime.ofInstant(Instant.ofEpochMilli(fromMillis), zone)`
   корректна — epoch millis абсолютны, зона применяется при разборе/отображении.
   Проверено: один и тот же millis даёт корректные представления в Europe/Moscow, UTC,
   Europe/Berlin. Смена пояса устройства не искажает расчёт (пересчёт в текущем поясе).
5. **DST fall-back**: wall time сохраняется, offset пересчитывается — 24.10 02:30+02:00 →
   25.10 02:30+02:00 (+24 ч). Daily 09:00 через весенний переход: 28.03 09:00+01:00 →
   29.03 09:00+02:00 (+23 ч) — корректно. Проверено на JVM.
6. **WEEKLY в штатном цикле** (`from` — целевой день недели, сразу после срабатывания):
   корректно — Fri 07:00 → Fri+7 07:00 (тест `weekly_sameDay`), Sat → Sat+7.
7. **MONTHLY в штатном цикле** (`from` >= целевого дня): корректно — 15.06 → 15.07,
   31.01 → 28.02 (тесты `monthly_sameDay`, `monthly_31st_coerces`).
8. **Экстремальные interval**: `interval = Int.MAX_VALUE` не бросает исключение
   (java.time выдерживает диапазон дат, результат — абсурдно далёкая дата); крэша нет,
   отдельного фикса не требует. Проверено на JVM.

## Дополнительные находки

- **Неиспользуемый импорт** — `RecurrenceCalculator.kt:5` (`java.time.temporal.ChronoUnit`)
  не используется нигде в файле. Критичность: низкий. Удалить импорт.
- **`withSameTime` — мёртвый код** (`:74-79`): на всех текущих путях no-op, т.к.
  `plusDays/plusWeeks/plusMonths` уже сохраняют локальное время; DST-gap им не
  компенсируется (см. находку 4). Либо удалить, либо задействовать с anchor-параметром.
- **`toLabel()`** (`RecurrenceRule.kt:23-30`): `MONTHLY` без `?: 1` печатает
  «ежемесячно (null)» при `dayOfMonth = null`; `WEEKLY` с некорректным `dayOfWeek` даёт
  «еженедельно ()» (пустое имя дня). Критичность: низкий; UI-косметика.
- **`serialize()` теряет `interval` для WEEKDAYS/WEEKENDS** (`:37-38`): round-trip
  `RecurrenceRule(WEEKDAYS, interval = 3)` → `"WEEKDAYS"` → `interval = 1`. Поведения не
  меняет (калькулятор игнорирует `interval` для этих типов), но round-trip неполный.
- **`parse()` устойчивость**: регистрозависим, не тримит вход (до фикса), игнорирует
  лишние части (`"DAILY:1:9"`), `"WEEKLY"` без дня недели → понедельник. Критичность: низкий.
