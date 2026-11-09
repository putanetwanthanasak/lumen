/**
 * Thai month names, as backend/app/notifications/copy.py shows them: a short month
 * name and the Buddhist-era year ("2026-11" -> "พ.ย. 2569").
 */

export const THAI_MONTHS = [
  "ม.ค.",
  "ก.พ.",
  "มี.ค.",
  "เม.ย.",
  "พ.ค.",
  "มิ.ย.",
  "ก.ค.",
  "ส.ค.",
  "ก.ย.",
  "ต.ค.",
  "พ.ย.",
  "ธ.ค.",
] as const;

const BUDDHIST_ERA_OFFSET = 543;
const MONTH = /^([0-9]{4})-(0[1-9]|1[0-2])$/;

type YearMonth = { year: number; month: number }; // month 1-12

export function parseMonth(value: string): YearMonth {
  const match = MONTH.exec(value);
  if (match === null) throw new Error(`not a month string: ${JSON.stringify(value)}`);
  return { year: Number(match[1]), month: Number(match[2]) }; // ui-06-allow: a date, not money
}

function format({ year, month }: YearMonth): string {
  return `${year.toString().padStart(4, "0")}-${month.toString().padStart(2, "0")}`;
}

/** "2026-11" -> "พ.ย. 2569". */
export function thaiMonth(value: string): string {
  const { year, month } = parseMonth(value);
  return `${THAI_MONTHS[month - 1]} ${year + BUDDHIST_ERA_OFFSET}`;
}

/** "2026-11" -> "พ.ย." (for narrow bar labels). */
export function thaiMonthShort(value: string): string {
  return THAI_MONTHS[parseMonth(value).month - 1] ?? value;
}

/** "2026-12", 1 -> "2027-01". */
export function addMonths(value: string, count: number): string {
  const { year, month } = parseMonth(value);
  const index = year * 12 + (month - 1) + count;
  return format({ year: Math.floor(index / 12), month: (index % 12) + 1 }); // ui-06-allow: a date
}

/** The calendar month of a date, "YYYY-MM". */
export function monthOf(date: Date): string {
  return format({ year: date.getFullYear(), month: date.getMonth() + 1 });
}

const DAY = /^([0-9]{4})-(0[1-9]|1[0-2])-([0-3][0-9])T/;

/**
 * "2026-11-03T09:00:00+07:00" -> "3 พ.ย. 2569". The API sends Bangkok time, so the
 * date part is the Bangkok date: read as text, with no time zone arithmetic.
 */
export function thaiDate(at: string): string {
  const match = DAY.exec(at);
  if (match === null) throw new Error(`not a datetime string: ${JSON.stringify(at)}`);
  const day = Number(match[3]); // ui-06-allow: a date, not money
  return `${day} ${thaiMonth(`${match[1]}-${match[2]}`)}`;
}

const CLOCK = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "Asia/Bangkok" });

/** The Bangkok clock time of an instant, 24-hour "HH:MM": when บัญชีหลัก's data loaded (UI-67). */
export function thaiTime(at: Date): string {
  return CLOCK.format(at);
}

const PRINT_DAY = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "numeric", year: "numeric", timeZone: "Asia/Bangkok" });

/**
 * The Bangkok date of an instant as a passbook prints it, "DD ม.ค. YY" with the
 * Buddhist year: "2026-11-04T09:00:00+07:00" -> "04 พ.ย. 69" (UI-71). Formatted in
 * Asia/Bangkok whatever the offset the instant carries and the machine's time zone.
 */
export function printDate(at: string): string {
  const instant = new Date(at);
  if (!DAY.test(at) || Number.isNaN(instant.getTime())) throw new Error(`not a datetime string: ${JSON.stringify(at)}`);
  const part = (type: string) => PRINT_DAY.formatToParts(instant).find((p) => p.type === type)?.value ?? "";
  const year = (Number(part("year")) + BUDDHIST_ERA_OFFSET) % 100; // ui-06-allow: a date, not money
  return `${part("day")} ${THAI_MONTHS[Number(part("month")) - 1]} ${year.toString().padStart(2, "0")}`; // ui-06-allow: a date
}
