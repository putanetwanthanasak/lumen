/**
 * The status of one month's total (screen "ภาระผ่อนรายเดือน", UI-20): an icon and
 * Thai text, never colour only. The API decides the flags (L65); this only picks
 * the words: over the ธปท. guidance first, then over budget, else in budget.
 */
import type { MonthRow, PreparedState } from "./api-types.ts";
import { ACCENT, BUFFER_CHIP } from "./accent.ts";
import type { IconName } from "./components/Icon.tsx";
import { MONTHS_VIEW } from "./copy.ts";

export type MonthStatus = { tone: "ok" | "over" | "risk"; icon: "check" | "alert" | "stop"; label: string };

/** The chip of each status (Months and the host app's KidNee card): a tint and its ink. */
export const STATUS_CHIP: Record<MonthStatus["tone"], string> = {
  ok: "bg-ok-bg text-ok-ink",
  over: "bg-warn-bg text-warn-ink",
  risk: "bg-risk-bg text-risk-ink",
};

export function monthStatus(row: Pick<MonthRow, "over_budget" | "over_one_third">): MonthStatus {
  if (row.over_one_third) return { tone: "risk", icon: "stop", label: MONTHS_VIEW.risk };
  if (row.over_budget) return { tone: "over", icon: "alert", label: MONTHS_VIEW.over };
  return { tone: "ok", icon: "check", label: MONTHS_VIEW.ok };
}

export type Chip = { icon: IconName; label: string; className: string };

/**
 * A month's chip on ภาระผ่อนรายเดือน (UI-54) and on บัญชีหลัก's KidNee card (UI-69):
 * over one third of income always says so, even when the buffer covered the month (the
 * payment is covered, the burden on income is not); else a month over budget the buffer fully
 * prepared says "กันชนเตรียมเงินแล้ว"; else the month's status. `state` is the month's
 * row in GET /buffer/shortfalls, null when it has none: the API decides.
 */
export function monthChip(month: Pick<MonthRow, "over_budget" | "over_one_third">, state: PreparedState | null): Chip {
  const status = monthStatus(month);
  if (month.over_budget && !month.over_one_third && state === "prepared") {
    return { icon: ACCENT.buffer.icon, label: MONTHS_VIEW.bufferReady, className: BUFFER_CHIP };
  }
  return { icon: status.icon, label: status.label, className: STATUS_CHIP[status.tone] };
}

/**
 * The months over budget in the API's rows (one row per month, in order), for one
 * summary line: how many, the first and the last (UI-41). Counted, never added up.
 * `together` is true when they run without a gap, so "{first} ถึง {last}" reads true;
 * otherwise the line says "ในช่วง" (somewhere in that span).
 */
export type OverRange = { count: number; first: string; last: string; together: boolean };

export function overRange(rows: readonly Pick<MonthRow, "month" | "over_budget">[]): OverRange | null {
  const over = rows.flatMap((row, at) => (row.over_budget ? [{ month: row.month, at }] : []));
  const first = over[0];
  const last = over.at(-1);
  if (first === undefined || last === undefined) return null;
  return {
    count: over.length,
    first: first.month,
    last: last.month,
    together: last.at - first.at + 1 === over.length, // positions in the rows, not money
  };
}
