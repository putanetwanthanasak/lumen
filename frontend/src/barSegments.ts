/**
 * One month's bar as segments, left to right (UI-52, DESIGN.md section 7.2b):
 * - ok: green, up to the budget (or the whole total when it is within budget; red then if
 *   that total is still over one third of income, which a budget above a third allows, L64);
 * - buffer: teal, what was moved from the buffer for this month, never past the shortfall;
 * - gap: amber (red when over one third of income), the remaining_gap the API sent.
 * Every amount is the API's (GET /debts/months and GET /buffer/shortfalls). Positions are
 * barPermille values (exact, BigInt); the only arithmetic is on those per mille numbers,
 * never on money. Segments touch with no gap or overlap and end at barPermille(total).
 */
import type { ShortfallMonth } from "./api-types.ts";
import { BUFFER_BAR } from "./accent.ts";
import { barPermille, toSatang, type Money } from "./money.ts";

export type SegmentKind = "ok" | "buffer" | "gap";

/** From and to in per mille of the scale (0 to 1000). */
export type Segment = { kind: SegmentKind; from: number; to: number; className: string };

export type BarInput = {
  total: Money;
  budget: Money;
  scale: Money;
  row: ShortfallMonth | null; // this month's row of GET /buffer/shortfalls, if over budget
  overBudget: boolean; // the API's flags (L65), never worked out here
  overOneThird: boolean;
};

const OK = "bg-bar-ok";
const OVER = "bg-bar-over";
const RISK = "bg-bar-risk";

export function barSegments({ total, budget, scale, row, overBudget, overOneThird }: BarInput): Segment[] {
  const t = barPermille(total, scale);
  if (!overBudget) return [{ kind: "ok", from: 0, to: t, className: overOneThird ? RISK : OK }];
  const b = barPermille(budget, scale);
  const ok: Segment = { kind: "ok", from: 0, to: b, className: OK };
  const gap = (from: number): Segment => ({ kind: "gap", from, to: t, className: overOneThird ? RISK : OVER });
  const buffer = (to: number): Segment => ({ kind: "buffer", from: b, to, className: BUFFER_BAR });
  if (row === null || row.state === "not_prepared") return [ok, gap(b)];
  // Prepared, or partly prepared with nothing left (never sent by the API): all teal.
  if (row.state === "prepared" || toSatang(row.remaining_gap) === 0n) return [ok, buffer(t)];
  // Partly prepared: the gap is the API's remaining_gap at the end of the bar. Rounding
  // may put t - g below the budget mark, so it is held there: the teal is then zero wide,
  // and the chip and the line still say what was moved.
  const g = barPermille(row.remaining_gap, scale);
  const split = t - g < b ? b : t - g; // per mille, not money
  return [ok, buffer(split), gap(split)];
}

/** A segment's place on the bar, as CSS percentages. */
export function segmentStyle(segment: Segment): { left: string; width: string } {
  return { left: `${segment.from / 10}%`, width: `${(segment.to - segment.from) / 10}%` };
}
