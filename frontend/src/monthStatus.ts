/**
 * The status of one month's total (screen "ภาระผ่อนรายเดือน", UI-20): an icon and
 * Thai text, never colour only. The API decides the flags (L65); this only picks
 * the words: over the ธปท. guidance first, then over budget, else in budget.
 */
import type { MonthRow } from "./api-types.ts";
import { MONTHS_VIEW } from "./copy.ts";

export type MonthStatus = { tone: "ok" | "over" | "risk"; icon: "check" | "alert" | "stop"; label: string };

export function monthStatus(row: Pick<MonthRow, "over_budget" | "over_one_third">): MonthStatus {
  if (row.over_one_third) return { tone: "risk", icon: "stop", label: MONTHS_VIEW.risk };
  if (row.over_budget) return { tone: "over", icon: "alert", label: MONTHS_VIEW.over };
  return { tone: "ok", icon: "check", label: MONTHS_VIEW.ok };
}
