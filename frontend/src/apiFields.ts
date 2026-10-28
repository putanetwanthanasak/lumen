/**
 * Fields the screens read that the backend does not send yet (TODO(backend)), checked
 * against its schemas on main: `monthly_reduction` on the plan's estimate, `over_by` on
 * the month rows, `platform_name` on installment lines, and the assistant summary,
 * which has no endpoint yet. The mock sends them all.
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
  console.warn(`${answer}: no readable ${field}${times}, so ${effect}. TODO(backend): send it.`);
}

const moneyOrNull = (value: unknown): Money | null => (isApiMoney(value) ? value : null);

/** A platform name is text, or null when no app is named; nothing else is one. */
const isName = (value: unknown): value is string | null => value === null || typeof value === "string";

/** GET /assistant/plan: without the estimate's `monthly_reduction`, the offer shows without its benefit line. */
export function readPlan(plan: AssistantPlanOut): AssistantPlanOut {
  const estimate = plan.consolidation.estimate;
  if (estimate === null) return plan;
  const reduction = moneyOrNull(estimate.monthly_reduction);
  if (reduction === null) {
    warnMissing("GET /assistant/plan", "consolidation.estimate.monthly_reduction", 1, "the offer card shows without its benefit line");
  }
  return { ...plan, consolidation: { ...plan.consolidation, estimate: { ...estimate, monthly_reduction: reduction } } };
}

/** GET /debts/months: without a row's `over_by`, Home's chip for that month shows no amount. */
export function readMonths(out: MonthsOut): MonthsOut {
  let noOverBy = 0;
  let noName = 0;
  const months = out.months.map((row) => {
    const overBy = moneyOrNull(row.over_by);
    if (overBy === null) noOverBy += 1;
    const installments = row.installments.map((item) => {
      if (isName(item.platform_name)) return item;
      noName += 1;
      return { ...item, platform_name: null };
    });
    return { ...row, over_by: overBy, installments };
  });
  if (noOverBy > 0) warnMissing("GET /debts/months", "over_by", noOverBy, "Home's over-budget chips show without their amounts");
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
 * POST /assistant/summary: without its text the bubble shows its error state, with a
 * retry; without `is_example` it keeps the example tag, the safe side for AI text.
 */
export function readAssistantSummary(out: AssistantSummaryOut): AssistantSummaryOut {
  if (typeof out.text !== "string") {
    warnMissing("POST /assistant/summary", "text", 1, "the assistant's bubble shows its error state");
    throw new Error("POST /assistant/summary: no text");
  }
  if (typeof out.is_example === "boolean") return out;
  warnMissing("POST /assistant/summary", "is_example", 1, "the summary keeps its example tag");
  return { ...out, is_example: true };
}
