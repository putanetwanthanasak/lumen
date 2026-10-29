/**
 * Fields the screens read that came last to the backend (Session 17), read with care:
 * `current_monthly_total` and `monthly_reduction` on the plan's estimate,
 * `platform_name` on installment lines, and the assistant summary's shape. The
 * backend and the mock send them all; an older or partial answer must still not
 * break a screen.
 *
 * Each reader takes an answer as it came. Such a field that is absent, or not what the
 * contract says, is read as null, with one console warning per answer and field, and
 * the screen leaves out only the part that needs it: Home never crashes on a missing
 * field (UI-39). Nothing is guessed, and the answer given is never changed.
 */
import type { AssistantPlanOut, AssistantSummaryOut, DebtSummary, MonthsOut } from "./api-types.ts";
import { isApiMoney, type Money } from "./money.ts";

function warnMissing(answer: string, field: string, count: number, effect: string): void {
  const times = count > 1 ? ` (${count} times)` : "";
  console.warn(`${answer}: no readable ${field}${times}, so ${effect}.`);
}

const moneyOrNull = (value: unknown): Money | null => (isApiMoney(value) ? value : null);

/** A platform name is text, or null when no app is named; nothing else is one. */
const isName = (value: unknown): value is string | null => value === null || typeof value === "string";

/**
 * GET /assistant/plan: without the estimate's `monthly_reduction`, the offer shows
 * without its benefit line; without `current_monthly_total`, its "ตอนนี้" column
 * shows the total only.
 */
export function readPlan(plan: AssistantPlanOut): AssistantPlanOut {
  const estimate = plan.consolidation.estimate;
  if (estimate === null) return plan;
  const reduction = moneyOrNull(estimate.monthly_reduction);
  if (reduction === null) {
    warnMissing("GET /assistant/plan", "consolidation.estimate.monthly_reduction", 1, "the offer card shows without its benefit line");
  }
  const current = moneyOrNull(estimate.current_monthly_total);
  if (current === null) {
    warnMissing("GET /assistant/plan", "consolidation.estimate.current_monthly_total", 1, "the offer's ตอนนี้ shows its total only");
  }
  const read = { ...estimate, monthly_reduction: reduction, current_monthly_total: current };
  return { ...plan, consolidation: { ...plan.consolidation, estimate: read } };
}

/** GET /debts/months: without an installment's `platform_name`, it shows no app name. */
export function readMonths(out: MonthsOut): MonthsOut {
  let noName = 0;
  const months = out.months.map((row) => {
    const installments = row.installments.map((item) => {
      if (isName(item.platform_name)) return item;
      noName += 1;
      return { ...item, platform_name: null };
    });
    return { ...row, installments };
  });
  if (noName > 0) warnMissing("GET /debts/months", "installments[].platform_name", noName, "those installments show no app name");
  return { ...out, months };
}

/** GET /debts/summary: without `platform_name`, an installment shows no app name. */
export function readSummary(summary: DebtSummary): DebtSummary {
  let noName = 0;
  const installments = summary.installments.map((line) => {
    if (isName(line.platform_name)) return line;
    noName += 1;
    return { ...line, platform_name: null };
  });
  if (noName > 0) warnMissing("GET /debts/summary", "installments[].platform_name", noName, "those installments show no app name");
  return { ...summary, installments };
}

/**
 * GET /assistant/summary: without readable text the answer counts as failed, so the
 * bubble shows the plan's own words (homeLayout.aiBubble), never an empty card. Its
 * `source` and `reason` change nothing on screen.
 */
export function readAssistantSummary(out: AssistantSummaryOut): AssistantSummaryOut {
  if (typeof out.text === "string" && out.text.trim() !== "") return out;
  warnMissing("GET /assistant/summary", "text", 1, "the assistant's bubble shows the plan's own words");
  throw new Error("GET /assistant/summary: no text");
}
