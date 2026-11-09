/**
 * Money on the client is display only (DESIGN.md section 3).
 *
 * The API sends money as JSON strings ("1500.00", L49) and the client never adds,
 * subtracts or rounds them. This file only:
 * - formats an API string for display, by string operations;
 * - checks what the user typed, before it is sent as a string (never rounded);
 * - turns two amounts into a bar height in per mille, exactly, with BigInt satang.
 *   The result is a drawing size, never shown as money;
 * - multiplies a typed monthly amount by the months, exactly, with BigInt satang
 *   (the form's price from the monthly amount, UI-72). The one product the client
 *   makes; it never rounds, so it needs no rounding rule.
 */

export type Money = string; // an API money string, e.g. "1500.00"

// What the API sends: digits, then at most 2 decimals. Never a float, sign or exponent.
const API_MONEY = /^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$/;

export class MoneyFormatError extends Error {}

function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/** "1500.00" -> "1,500.00". Throws MoneyFormatError for anything else. */
export function formatAmount(value: Money): string {
  const match = API_MONEY.exec(value);
  if (match === null) {
    throw new MoneyFormatError(`not an API money string: ${JSON.stringify(value)}`);
  }
  const whole = match[1] ?? "0";
  const decimals = (match[2] ?? ".").slice(1).padEnd(2, "0");
  return `${groupThousands(whole)}.${decimals}`;
}

/** "1500.00" -> "1,500.00 บาท". */
export function formatBaht(value: Money): string {
  return `${formatAmount(value)} บาท`;
}

// What a user may type: plain digits, or digits grouped in threes by commas
// ("12,000"), then at most 2 decimals. A comma anywhere else is refused, never
// dropped: "1,5" is not 15 (review F5).
const TYPED_MONEY = /^([0-9]+|[0-9]{1,3}(,[0-9]{3})+)(\.[0-9]{1,2})?$/;
const MAX_WHOLE_DIGITS = 10; // Numeric(12,2)

export type MoneyInput =
  | { ok: true; value: Money }
  | { ok: false; reason: "empty" | "format" | "decimals" | "zero" | "too_large" };

/**
 * Check a typed amount and return it as the string the API expects. Commas are
 * removed; the digits are kept exactly as typed. More than 2 decimals is refused,
 * never rounded (L49).
 */
export function parseMoneyInput(raw: string): MoneyInput {
  const text = raw.trim();
  if (text === "") return { ok: false, reason: "empty" };
  if (/^[0-9,]*\.[0-9]{3,}$/.test(text)) return { ok: false, reason: "decimals" };
  if (!TYPED_MONEY.test(text)) return { ok: false, reason: "format" };
  const plain = text.replaceAll(",", "");
  const [whole = "", decimals] = plain.split(".");
  const trimmed = whole.replace(/^0+(?=[0-9])/, "");
  if (trimmed.length > MAX_WHOLE_DIGITS) return { ok: false, reason: "too_large" };
  if (/^0*$/.test(trimmed) && /^0*$/.test(decimals ?? "")) return { ok: false, reason: "zero" };
  return { ok: true, value: decimals === undefined ? trimmed : `${trimmed}.${decimals}` };
}

/** Whether an answer's field is an API money string, before anything formats it (UI-39). */
export function isApiMoney(value: unknown): value is Money {
  return typeof value === "string" && API_MONEY.test(value);
}

/** "1500.5" -> 150050n. Exact; for comparisons and bar heights only. */
export function toSatang(value: Money): bigint {
  const match = API_MONEY.exec(value);
  if (match === null) {
    throw new MoneyFormatError(`not an API money string: ${JSON.stringify(value)}`);
  }
  const decimals = (match[2] ?? ".").slice(1).padEnd(2, "0");
  return BigInt(`${match[1] ?? "0"}${decimals}`);
}

/** 150050n -> "1500.50". Exact; the sign kept. */
export function fromSatang(value: bigint): Money {
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(3, "0");
  const text = `${digits.slice(0, -2)}.${digits.slice(-2)}`;
  return negative ? `-${text}` : text;
}

/**
 * The price from the monthly amount (the form's two-way input, UI-72): monthly x
 * months, exact in BigInt satang, never rounded. "2000" x 6 -> "12000.00". The
 * opposite way, price / months, rounds, so it stays the API's suggestion
 * (GET /installments/suggested-monthly); the client never divides money.
 */
export function timesMonths(monthly: Money, months: number): Money {
  if (!Number.isSafeInteger(months) || months < 1) throw new RangeError(`not a count of months: ${months}`);
  return fromSatang(toSatang(monthly) * BigInt(months));
}

/**
 * Bar height in per mille of the scale, rounded down, capped at 1000.
 * A zero scale gives 0. Exact: BigInt satang, no floating point.
 */
export function barPermille(value: Money, scale: Money): number {
  const max = toSatang(scale);
  if (max === 0n) return 0;
  const permille = (toSatang(value) * 1000n) / max;
  return permille > 1000n ? 1000 : Number(permille); // ui-06-allow: per mille, not money
}

/** The largest of several API money strings, compared exactly. */
export function largest(values: readonly Money[]): Money {
  let best: Money = "0.00";
  for (const value of values) {
    if (toSatang(value) > toSatang(best)) best = value;
  }
  return best;
}
