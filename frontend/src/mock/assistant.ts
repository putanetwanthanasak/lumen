/**
 * Mock GET /assistant/plan, the same shape and rules as the merged backend
 * (backend/app/assistant/plan.py, L69, L70), in exact BigInt satang like the rest of
 * the mock. The mock's installments are all recorded by hand (L62): none is overdue
 * or disputed, so the backend's OVERDUE_DEBT and DISPUTED_DEBT checks never apply here.
 */
import type { AssistantPlanOut, ConsolidationOut, PlanMonth } from "../api-types.ts";
import { bufferPlanLines, notConsolidatingLine, planLines } from "../assistantText.ts";
import { ASSIST } from "../copy.ts";
import { formatBaht, type Money } from "../money.ts";
import { addMonths } from "../thaiMonth.ts";
import { fromSatang, toSatang } from "./satang.ts";

export type PlanDebt = { first_due_month: string; months: number; monthly_amount: Money };

const HORIZON_CAP = 600; // months shown (L59 6)
export const SAFE_NEW_TERM = 12; // safe_new_monthly is for a new 12-month installment
const CONSOLIDATION_RUN = 3; // L70 (a)
const MONEY_MAX = toSatang("9999999999.99"); // Numeric(12,2)
// The backend's config defaults: EXAMPLE values, not a real rate (L71).
export const EXAMPLE_ANNUAL_RATE = "0.18";
export const EXAMPLE_TERM_MONTHS = 24;

/** "YYYY-MM" as a month count, so months compare and subtract as integers. */
function index(month: string): number {
  const [y = "0", m = "1"] = month.split("-");
  return Number(y) * 12 + Number(m) - 1; // ui-06-allow: a date
}

function lastIndex(d: PlanDebt): number {
  return index(d.first_due_month) + d.months - 1;
}

function totalAt(debts: readonly PlanDebt[], i: number): bigint {
  return debts
    .filter((d) => index(d.first_due_month) <= i && i <= lastIndex(d))
    .reduce((acc, d) => acc + toSatang(d.monthly_amount), 0n);
}

const max0 = (v: bigint): bigint => (v > 0n ? v : 0n);
const later = (a: number, b: number): number => (a > b ? a : b); // month indices and counts
const ceilDiv = (a: bigint, b: bigint): bigint => (a + b - 1n) / b;

/**
 * The level payment P * r / (1 - (1 + r) ** -n), r = annual / 12, rounded UP to the
 * satang, as an exact fraction. The backend first cleans its 34-digit result to 20
 * places, then rounds up: the two differ only if the exact payment lies less than
 * 1E-20 above a satang without being on it.
 */
export function amortisedPayment(principal: bigint, annualRate: string, term: number): bigint {
  const [whole = "0", frac = ""] = annualRate.split(".");
  const num = BigInt(whole + frac); // the rate as num / 10^digits
  const perMonth = 10n ** BigInt(frac.length) * 12n; // r = num / perMonth
  const n = BigInt(term);
  if (num === 0n) return ceilDiv(principal, n);
  // r (1+r)^n / ((1+r)^n - 1) = num * A / (perMonth * (A - B)), A = (perMonth + num)^n, B = perMonth^n
  const a = (perMonth + num) ** n;
  const b = perMonth ** n;
  return ceilDiv(principal * num * a, perMonth * (a - b));
}

function consolidation(
  debts: readonly PlanDebt[],
  overRun: boolean,
  now: number,
  budget: bigint,
  annualRate: string,
  term: number,
): ConsolidationOut {
  const no = (reason: ConsolidationOut["reason"]): ConsolidationOut => ({ eligible: false, reason, estimate: null });
  if (!overRun) return no("NOT_NEEDED");
  // A manual row gets no payments: months left from now x the monthly amount.
  const principal = debts.reduce((acc, d) => {
    const left = later(0, lastIndex(d) - later(index(d.first_due_month), now) + 1);
    return acc + BigInt(left) * toSatang(d.monthly_amount);
  }, 0n);
  if (principal > MONEY_MAX) return no("ESTIMATE_TOO_LARGE");
  const payment = amortisedPayment(principal, annualRate, term);
  const total = payment * BigInt(term);
  if (total > MONEY_MAX) return no("ESTIMATE_TOO_LARGE");
  // The loan replaces every counted installment, so it is the only plan due (b).
  if (payment > budget) return no("PAYMENT_ABOVE_BUDGET");
  const first = addMonths(monthOfIndex(now), 1);
  return {
    eligible: true,
    reason: "ELIGIBLE",
    estimate: {
      principal: fromSatang(principal),
      annual_rate: annualRate,
      rate_is_example: true,
      rate_note: "example, not a real rate",
      term_months: term,
      first_due_month: first,
      monthly_payment: fromSatang(payment),
      total_cost: fromSatang(total),
      current_remaining_total: fromSatang(principal),
      extra_cost: fromSatang(total - principal),
    },
  };
}

function monthOfIndex(i: number): string {
  const m = i % 12;
  return `${(i - m) / 12}-${String(m + 1).padStart(2, "0")}`;
}

export function assistantPlan(
  debts: readonly PlanDebt[],
  now: string,
  income: Money,
  budget: Money,
  bufferBalance: Money,
  annualRate = EXAMPLE_ANNUAL_RATE,
  term = EXAMPLE_TERM_MONTHS,
): AssistantPlanOut {
  const cap = toSatang(budget);
  const third = toSatang(income);
  const start = index(now);
  const end = debts.reduce((e, d) => later(e, lastIndex(d) + 1), start + 1); // exclusive
  const totals = Array.from({ length: end - start }, (_, k) => totalAt(debts, start + k));
  const over = totals.map((t) => t > cap);

  const lastOver = over.lastIndexOf(true);
  const back = lastOver === -1 ? null : monthOfIndex(start + lastOver + 1);
  const safeFrom = back ?? now;
  const window = Array.from({ length: SAFE_NEW_TERM }, (_, k) => totalAt(debts, index(safeFrom) + k));
  // Within budget AND at most a third of income (no L65 RED), rounded down.
  const safe = window
    .map((t) => {
      const room = max0(cap - t);
      const thirdRoom = max0(third - 3n * t) / 3n;
      return room < thirdRoom ? room : thirdRoom;
    })
    .reduce((min, v) => (v < min ? v : min));

  let run = 0;
  let longest = 0;
  for (const o of over) {
    run = o ? run + 1 : 0;
    longest = later(longest, run);
  }
  const shortfall = totals.reduce((acc, t) => acc + max0(t - cap), 0n);
  const balance = toSatang(bufferBalance);

  const shown = totals.length > HORIZON_CAP ? HORIZON_CAP : totals.length;
  const months: PlanMonth[] = totals.slice(0, shown).map((t, k) => ({
    month: monthOfIndex(start + k),
    total: fromSatang(t),
    budget,
    over_budget: t > cap,
    headroom: fromSatang(max0(cap - t)),
  }));
  return {
    months,
    months_truncated: shown < totals.length,
    back_in_budget_month: back,
    pause_until: back !== null && over[0] === true ? back : null,
    safe_new_monthly: fromSatang(safe),
    safe_new_from: safeFrom,
    safe_new_months: SAFE_NEW_TERM,
    buffer_plan: {
      shortfall: fromSatang(shortfall),
      balance: fromSatang(balance),
      covered: balance >= shortfall,
      still_short: fromSatang(max0(shortfall - balance)),
    },
    consolidation: consolidation(debts, longest >= CONSOLIDATION_RUN, start, cap, annualRate, term),
  };
}

/**
 * TODO(backend, tomorrow): the AI summary. The mock is a fixed example, built from
 * the plan's own words (the same lines the screens show), labelled ตัวอย่าง.
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
