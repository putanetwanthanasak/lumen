/**
 * A month over budget and the buffer (Session 17, L66), from GET /buffer/shortfalls:
 * the same words on Home's hero, the buffer screen and ภาระผ่อนรายเดือน (UI-46).
 * - not prepared: amber, "{month} เกินงบ {shortfall}", and "ใช้กันชนจ่ายส่วนที่เกิน";
 * - partly prepared: amber, what was moved and the gap left, and the button;
 * - prepared: a check, "... ย้ายจากกันชนเข้าบัญชีหลักแล้ว อย่าลืมจ่ายค่างวดในแอปผ่อน", no button.
 * The state, the shortfall and the gap are the API's; the budget numbers never change
 * after a move, only the state does. Nothing is added up here: the amount to move is
 * the smaller of two API amounts, the gap and what the buffer holds.
 */
import type { PreparedState, ShortfallMonth, ShortfallsOut } from "./api-types.ts";
import type { MoveRequest } from "./bufferMove.ts";
import type { Marked } from "./accent.ts";
import { BUFFER_STATE } from "./copy.ts";
import { formatBaht, toSatang, type Money } from "./money.ts";
import { thaiMonth } from "./thaiMonth.ts";

/** "ใช้กันชนจ่ายส่วนที่เกิน" for one month: move `amount` with `for_month` = `month`. */
export type Prepare = { month: string; amount: Money; total: Money };

export type ShortfallView = {
  month: string;
  state: PreparedState;
  total: Money;
  line: Marked;
  prepare: Prepare | null;
  row: ShortfallMonth; // the API's row as it came, for the month's bar (barSegments)
};

const smaller = (a: Money, b: Money): Money => (toSatang(a) <= toSatang(b) ? a : b);

/**
 * The move a month's card offers. A move for this month whose outcome is unknown wins
 * over the API's answer, even when the API already counts it as prepared: the ledger
 * commits before the bank call, so only a retry under the same id finishes it (review
 * round 2 F1). Otherwise, what `shortfallView` gave.
 */
export function cardMove(view: ShortfallView, kept: MoveRequest | null): Prepare | null {
  if (kept !== null && kept.forMonth === view.month) return { month: view.month, amount: kept.amount, total: view.total };
  return view.prepare;
}

export function shortfallView(row: ShortfallMonth, bufferBalance: Money): ShortfallView {
  const month = thaiMonth(row.month);
  const shortfall = formatBaht(row.shortfall);
  if (row.state === "prepared") {
    const line: Marked = { accent: "buffer", icon: "check", text: BUFFER_STATE.prepared(month, shortfall) };
    return { month: row.month, state: row.state, total: row.total, line, prepare: null, row };
  }
  const text =
    row.state === "partly_prepared"
      ? BUFFER_STATE.partly(month, shortfall, formatBaht(row.prepared), formatBaht(row.remaining_gap))
      : BUFFER_STATE.over(month, shortfall);
  // An empty buffer has nothing to move: the line stays, without the button.
  const amount = smaller(row.remaining_gap, bufferBalance);
  return {
    month: row.month,
    state: row.state,
    total: row.total,
    line: { accent: "warn", icon: "alert", text },
    prepare: toSatang(amount) > 0n ? { month: row.month, amount, total: row.total } : null,
    row,
  };
}

/** Each month over budget, keyed by "YYYY-MM", for the months screen. */
export function shortfallsByMonth(out: ShortfallsOut | null): ReadonlyMap<string, ShortfallView> {
  if (out === null) return new Map();
  return new Map(out.months.map((row) => [row.month, shortfallView(row, out.balance)]));
}

// Home and ภาระผ่อนรายเดือน open the buffer screen at a month; it scrolls to that card.
let wanted: string | null = null;

export function openBufferAt(month: string): void {
  wanted = month;
}

/** The month asked for, once. */
export function takeBufferMonth(): string | null {
  const month = wanted;
  wanted = null;
  return month;
}
