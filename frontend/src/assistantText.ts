/**
 * Words around the assistant plan's numbers (GET /assistant/plan), for the
 * monthly view, the form hint, the buffer card and Home's consolidation card
 * (UI-29). Every amount and month is the API's; this only formats and picks words.
 */
import type { AssistantPlanOut, BufferPlanOut, ConsolidationReason } from "./api-types.ts";
import { ASSIST } from "./copy.ts";
import { formatBaht, toSatang } from "./money.ts";
import { thaiMonth } from "./thaiMonth.ts";

export type PlanLines = { back: string; pauseNow: boolean; safe: string };

/** "กลับมาอยู่ในงบเดือน ..." and the safe new monthly amount, with the pause when over budget now. */
export function planLines(plan: AssistantPlanOut): PlanLines {
  const from = thaiMonth(plan.safe_new_from);
  const pauseNow = plan.pause_until !== null;
  const room =
    toSatang(plan.safe_new_monthly) > 0n ? ASSIST.safeNew(from, formatBaht(plan.safe_new_monthly)) : ASSIST.safeNone(from);
  return {
    back: plan.back_in_budget_month === null ? ASSIST.allInBudget : ASSIST.backInBudget(thaiMonth(plan.back_in_budget_month)),
    pauseNow,
    safe: pauseNow ? `${ASSIST.pauseNow} ${room}` : room,
  };
}

/** The small hint on the เช็กก่อนผ่อน form; null when nothing more fits. */
export function formHint(plan: AssistantPlanOut): string | null {
  if (toSatang(plan.safe_new_monthly) === 0n) return ASSIST.safeNone(thaiMonth(plan.safe_new_from));
  return ASSIST.formHint(formatBaht(plan.safe_new_monthly), thaiMonth(plan.safe_new_from));
}

/** The buffer screen's over-budget card: the shortfall, then covered or still short. */
export function bufferPlanLines(b: BufferPlanOut): { tone: "ok" | "warn"; lines: string[] } {
  if (toSatang(b.shortfall) === 0n) return { tone: "ok", lines: [ASSIST.bufferNone] };
  return {
    tone: b.covered ? "ok" : "warn",
    lines: [
      ASSIST.shortfall(formatBaht(b.shortfall)),
      b.covered ? ASSIST.covered(formatBaht(b.balance)) : ASSIST.stillShort(formatBaht(b.balance), formatBaht(b.still_short)),
    ],
  };
}

/** Home's one-line banner when consolidation is not offered (L70); the reason expands under it. */
export function notConsolidatingLine(reason: ConsolidationReason): string {
  return reason === "NOT_NEEDED" ? ASSIST.notNeeded : ASSIST.notWorth;
}

/** "0.18" -> "18", "0.185" -> "18.5": the decimal point moved two places, as text. */
export function ratePercent(rate: string): string {
  const [whole = "0", frac = ""] = rate.split(".");
  const digits = frac.padEnd(2, "0");
  const intPart = (whole + digits.slice(0, 2)).replace(/^0+(?=\d)/, "");
  const rest = digits.slice(2).replace(/0+$/, "");
  return rest === "" ? intPart : `${intPart}.${rest}`;
}

/**
 * The assistant's example summary (AI is roadmap only): the plan's own words, the
 * same lines the screens show, one point per line. Shown labelled ตัวอย่าง.
 */
export function exampleSummary(plan: AssistantPlanOut): string {
  const lines = planLines(plan);
  const buffer = bufferPlanLines(plan.buffer_plan).lines.join(" ");
  const c = plan.consolidation;
  const consolidate =
    c.estimate === null
      ? `${notConsolidatingLine(c.reason)} ${ASSIST.reason[c.reason]}`
      : `${ASSIST.worth} ${ASSIST.newMonthly} ${formatBaht(c.estimate.monthly_payment)} ${ASSIST.totalCost} ${formatBaht(c.estimate.total_cost)} (${ASSIST.exampleTag})`;
  // The buffer line already says every month is in budget: say it once.
  const back = plan.back_in_budget_month === null ? [] : [lines.back];
  return [...back, lines.safe, buffer, consolidate].join("\n"); // one point per line
}
