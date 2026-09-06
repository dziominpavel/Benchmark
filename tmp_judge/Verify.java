import java.time.*;
import java.time.temporal.ChronoUnit;

public class Verify {
    enum RecurrenceType { DAILY, WEEKDAYS, WEEKENDS, WEEKLY, MONTHLY }

    static class RecurrenceRule {
        RecurrenceType type;
        int interval;
        Integer dayOfWeek;
        Integer dayOfMonth;
        RecurrenceRule(RecurrenceType type, int interval, Integer dayOfWeek, Integer dayOfMonth) {
            this.type = type; this.interval = interval; this.dayOfWeek = dayOfWeek; this.dayOfMonth = dayOfMonth;
        }
        static RecurrenceRule parse(String s) {
            if (s == null || s.isBlank()) return null;
            String[] p = s.split(":");
            return switch (p[0]) {
                case "DAILY" -> new RecurrenceRule(RecurrenceType.DAILY, parseIntOrDefault(p, 1, 1), null, null);
                case "WEEKDAYS" -> new RecurrenceRule(RecurrenceType.WEEKDAYS, 1, null, null);
                case "WEEKENDS" -> new RecurrenceRule(RecurrenceType.WEEKENDS, 1, null, null);
                case "WEEKLY" -> new RecurrenceRule(RecurrenceType.WEEKLY, parseIntOrDefault(p, 2, 1), parseIntOrDefault(p, 1, 1), null);
                case "MONTHLY" -> new RecurrenceRule(RecurrenceType.MONTHLY, parseIntOrDefault(p, 2, 1), null, parseIntOrDefault(p, 1, 1));
                default -> null;
            };
        }
        static int parseIntOrDefault(String[] p, int idx, int def) {
            if (p.length <= idx) return def;
            try { return Integer.parseInt(p[idx]); } catch (NumberFormatException e) { return def; }
        }
    }

    static long nextOccurrence(RecurrenceRule rule, long fromMillis, ZoneId zone) {
        ZonedDateTime from = ZonedDateTime.ofInstant(Instant.ofEpochMilli(fromMillis), zone);
        ZonedDateTime candidate = switch (rule.type) {
            case DAILY -> nextDaily(from, rule.interval);
            case WEEKDAYS -> nextWeekdays(from);
            case WEEKENDS -> nextWeekends(from);
            case WEEKLY -> nextWeekly(from, rule.dayOfWeek != null ? rule.dayOfWeek : 1, rule.interval);
            case MONTHLY -> nextMonthly(from, rule.dayOfMonth != null ? rule.dayOfMonth : 1, rule.interval);
        };
        return candidate.toInstant().toEpochMilli();
    }

    static ZonedDateTime nextDaily(ZonedDateTime from, int interval) {
        return withSameTime(from.plusDays(interval), from);
    }
    static ZonedDateTime nextWeekdays(ZonedDateTime from) {
        ZonedDateTime candidate = withSameTime(from.plusDays(1), from);
        while (candidate.getDayOfWeek().getValue() > 5) {
            candidate = candidate.plusDays(1);
        }
        return candidate;
    }
    static ZonedDateTime nextWeekends(ZonedDateTime from) {
        ZonedDateTime candidate = withSameTime(from.plusDays(1), from);
        while (candidate.getDayOfWeek().getValue() < 6) {
            candidate = candidate.plusDays(1);
        }
        return candidate;
    }
    static ZonedDateTime nextWeekly(ZonedDateTime from, int dayOfWeek, int interval) {
        ZonedDateTime candidate = withSameTime(from.plusWeeks(interval), from);
        int targetDow = Math.min(Math.max(dayOfWeek, 1), 7);
        int currentDow = candidate.getDayOfWeek().getValue();
        int delta = (targetDow - currentDow + 7) % 7;
        candidate = candidate.plusDays(delta);
        if (!candidate.isAfter(from)) {
            candidate = candidate.plusWeeks(interval);
        }
        return candidate;
    }
    static ZonedDateTime nextMonthly(ZonedDateTime from, int dayOfMonth, int interval) {
        ZonedDateTime candidate = withSameTime(from.plusMonths(interval), from);
        int maxDay = candidate.toLocalDate().lengthOfMonth();
        int targetDay = Math.min(Math.max(dayOfMonth, 1), maxDay);
        candidate = candidate.withDayOfMonth(targetDay);
        if (!candidate.isAfter(from)) {
            candidate = candidate.plusMonths(interval);
            int newMaxDay = candidate.toLocalDate().lengthOfMonth();
            candidate = candidate.withDayOfMonth(Math.min(Math.max(dayOfMonth, 1), newMaxDay));
        }
        return candidate;
    }

    static ZonedDateTime withSameTime(ZonedDateTime self, ZonedDateTime other) {
        return self.withHour(other.getHour())
            .withMinute(other.getMinute())
            .withSecond(other.getSecond())
            .withNano(other.getNano());
    }

    static void p(String s) { System.out.println(s); }
    static String fmt(long ms, ZoneId zone) { return ZonedDateTime.ofInstant(Instant.ofEpochMilli(ms), zone).toString(); }
    static String fmt(ZonedDateTime zdt) { return zdt.toString(); }

    public static void main(String[] args) {
        ZoneId berlin = ZoneId.of("Europe/Berlin");
        ZoneId ny = ZoneId.of("America/New_York");

        // interval 0 daily
        ZonedDateTime from = ZonedDateTime.of(2026, 6, 19, 8, 0, 0, 0, berlin);
        long fromMs = from.toInstant().toEpochMilli();
        long next = nextOccurrence(new RecurrenceRule(RecurrenceType.DAILY, 0, null, null), fromMs, berlin);
        p("DAILY interval=0 from=" + fmt(from) + " next=" + fmt(next, berlin) + " equal? " + (next == fromMs));

        // weekly skip
        ZonedDateTime wfrom = ZonedDateTime.of(2026, 9, 7, 9, 0, 0, 0, berlin); // Monday
        long wfromMs = wfrom.toInstant().toEpochMilli();
        long wnext = nextOccurrence(new RecurrenceRule(RecurrenceType.WEEKLY, 1, 2, null), wfromMs, berlin);
        p("WEEKLY from Mon target Tue interval=1 next=" + fmt(wnext, berlin));

        // monthly skip
        ZonedDateTime mfrom = ZonedDateTime.of(2026, 1, 10, 9, 0, 0, 0, berlin);
        long mfromMs = mfrom.toInstant().toEpochMilli();
        long mnext = nextOccurrence(new RecurrenceRule(RecurrenceType.MONTHLY, 1, null, 15), mfromMs, berlin);
        p("MONTHLY from Jan 10 target 15 interval=1 next=" + fmt(mnext, berlin));

        // monthly dayOfMonth 31 from June 15
        ZonedDateTime m2from = ZonedDateTime.of(2026, 6, 15, 10, 0, 0, 0, berlin);
        long m2fromMs = m2from.toInstant().toEpochMilli();
        long m2next = nextOccurrence(new RecurrenceRule(RecurrenceType.MONTHLY, 1, null, 31), m2fromMs, berlin);
        p("MONTHLY from June 15 day=31 next=" + fmt(m2next, berlin));

        // monthly dayOfMonth 31 from March 29
        ZonedDateTime m3from = ZonedDateTime.of(2025, 3, 29, 10, 0, 0, 0, berlin);
        long m3fromMs = m3from.toInstant().toEpochMilli();
        long m3next = nextOccurrence(new RecurrenceRule(RecurrenceType.MONTHLY, 1, null, 31), m3fromMs, berlin);
        p("MONTHLY from March 29 day=31 next=" + fmt(m3next, berlin));

        // DST gap NY
        ZonedDateTime dfrom = ZonedDateTime.of(2026, 3, 7, 2, 30, 0, 0, ny);
        long dfromMs = dfrom.toInstant().toEpochMilli();
        long dnext = nextOccurrence(new RecurrenceRule(RecurrenceType.DAILY, 1, null, null), dfromMs, ny);
        p("DAILY DST gap from=" + fmt(dfrom) + " next=" + fmt(dnext, ny));

        // DST gap second occurrence
        long dnext2 = nextOccurrence(new RecurrenceRule(RecurrenceType.DAILY, 1, null, null), dnext, ny);
        p("DAILY DST gap second next=" + fmt(dnext2, ny));

        // parse
        p("parse DAILY:0 -> " + RecurrenceRule.parse("DAILY:0").interval);
        p("parse WEEKLY:8:1 -> dow=" + RecurrenceRule.parse("WEEKLY:8:1").dayOfWeek + " interval=" + RecurrenceRule.parse("WEEKLY:8:1").interval);
        p("parse MONTHLY:32:1 -> dom=" + RecurrenceRule.parse("MONTHLY:32:1").dayOfMonth);
        p("parse DAILY:abc -> " + (RecurrenceRule.parse("DAILY:abc") == null ? "null" : RecurrenceRule.parse("DAILY:abc").interval));

        // negative daily
        ZonedDateTime neg = ZonedDateTime.of(2026, 6, 19, 8, 0, 0, 0, berlin);
        long negMs = neg.toInstant().toEpochMilli();
        long negNext = nextOccurrence(new RecurrenceRule(RecurrenceType.DAILY, -1, null, null), negMs, berlin);
        p("DAILY interval=-1 next=" + fmt(negNext, berlin));

        // weekly interval 0 same day
        ZonedDateTime w0 = ZonedDateTime.of(2026, 6, 19, 7, 0, 0, 0, berlin); // friday
        long w0Ms = w0.toInstant().toEpochMilli();
        long w0next = nextOccurrence(new RecurrenceRule(RecurrenceType.WEEKLY, 0, 5, null), w0Ms, berlin);
        p("WEEKLY interval=0 same dow next=" + fmt(w0next, berlin) + " equal? " + (w0next == w0Ms));

        // monthly interval 0 same day
        ZonedDateTime m0 = ZonedDateTime.of(2026, 6, 15, 10, 0, 0, 0, berlin);
        long m0Ms = m0.toInstant().toEpochMilli();
        long m0next = nextOccurrence(new RecurrenceRule(RecurrenceType.MONTHLY, 0, null, 15), m0Ms, berlin);
        p("MONTHLY interval=0 same dom next=" + fmt(m0next, berlin) + " equal? " + (m0next == m0Ms));

        // weekly invalid dayOfWeek 8 => computed as Sunday (7)
        ZonedDateTime w8 = ZonedDateTime.of(2026, 6, 19, 7, 0, 0, 0, berlin); // friday
        long w8Ms = w8.toInstant().toEpochMilli();
        long w8next = nextOccurrence(new RecurrenceRule(RecurrenceType.WEEKLY, 1, 8, null), w8Ms, berlin);
        p("WEEKLY dayOfWeek=8 from Fri next=" + fmt(w8next, berlin));

        // weekdays DST cycle
        ZonedDateTime wd = ZonedDateTime.of(2026, 3, 6, 2, 30, 0, 0, ny); // friday
        long wdMs = wd.toInstant().toEpochMilli();
        long wdNext = nextOccurrence(new RecurrenceRule(RecurrenceType.WEEKDAYS, 1, null, null), wdMs, ny);
        p("WEEKDAYS DST from=" + fmt(wd) + " next=" + fmt(wdNext, ny));

        // DST overlap fall back
        ZonedDateTime ol = ZonedDateTime.of(2026, 10, 31, 1, 30, 0, 0, ny);
        long olMs = ol.toInstant().toEpochMilli();
        long olNext = nextOccurrence(new RecurrenceRule(RecurrenceType.DAILY, 1, null, null), olMs, ny);
        p("DAILY overlap from=" + fmt(ol) + " next=" + fmt(olNext, ny));

        // time-of-day drift: desired time 9:00, boundary now 12:00
        ZonedDateTime tfrom = ZonedDateTime.of(2026, 6, 19, 12, 0, 0, 0, berlin);
        long tfromMs = tfrom.toInstant().toEpochMilli();
        long tnext = nextOccurrence(new RecurrenceRule(RecurrenceType.DAILY, 1, null, null), tfromMs, berlin);
        p("DAILY desired 09:00 from 12:00 next=" + fmt(tnext, berlin));

        // B's DST gap fix test
        LocalDateTime gapLocal = LocalDateTime.of(2026, 3, 8, 2, 30);
        try {
            ZonedDateTime zGap = gapLocal.atZone(ny);
            p("B fix: LocalDateTime.atZone gap -> " + zGap);
        } catch (DateTimeException e) {
            p("B fix: LocalDateTime.atZone gap threw: " + e.getMessage());
        }
        try {
            ZonedDateTime zStrict = ZonedDateTime.of(gapLocal, ny);
            p("ZonedDateTime.of gap -> " + zStrict);
        } catch (DateTimeException e) {
            p("ZonedDateTime.of gap threw: " + e.getMessage());
        }
    }
}
