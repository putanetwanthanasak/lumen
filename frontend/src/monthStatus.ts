/**
 * The status of one month's total (screen "ภาระผ่อนรายเดือน", UI-20): an icon and
 * Thai text, never colour only. The API decides the flags (L65); this only picks
 * the words: over the ธปท. guidance first, then over budget, else in budget.
 */
import type { MonthRow } from "./api-types.ts";
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
