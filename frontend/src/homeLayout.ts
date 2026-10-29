/**
 * Home's state rules (DESIGN.md section 7.2, UI-33): which card shows, in which
 * shape, and what it says. A card with nothing to act on shrinks: the hero keeps one
 * status line, consolidation becomes a one-line banner. Every amount, flag and month
 * comes from the API layer (src/api.ts) and is only formatted here; nothing is added
 * up. Every coloured part is a Marked item: an icon and text with its accent (UI-34).
 */
import type { AssistantPlanOut, AssistantSummaryOut, BufferOut, ConsolidationOut, EstimateOut, MonthDetail, ShortfallsOut } from "./api-types.ts";
import { ACCENT, type Marked } from "./accent.ts";
import { notConsolidatingLine, planSummary } from "./assistantText.ts";
import { shortfallView, type ShortfallView } from "./bufferState.ts";
import { ASSIST, HOME } from "./copy.ts";
import { formatBaht, toSatang, type Money } from "./money.ts";
import { overRange } from "./monthStatus.ts";
import { thaiMonth } from "./thaiMonth.ts";
import type { Load } from "./useLoad.ts";

export type HeroView = {
  status: "all_in" | "later_over" | "now_over";
  month: string;
  total: Money;
  barOver: boolean;
  line: Marked | null; // this month in budget; null when this month is over (the warning covers it)
  warning: Marked | null; // the one warning line: how many months over, from when to when
  buffer: ShortfallView | null; // the first month over budget and the buffer (UI-46)
};

/**
 * This month's card, from GET /debts/months (this month first, up to the last month
 * due), one card with one warning line (UI-42). The months over budget are counted
 * from the rows (UI-41). The buffer line is the first month over budget from GET
 * /buffer/shortfalls, prepared or not (UI-46), never worked out here.
 */
export function heroView(months: readonly MonthDetail[], shortfalls: ShortfallsOut | null): HeroView | null {
  const [now, ...later] = months;
  if (now === undefined) return null;
  const over = overRange(months);
  const status = now.over_budget ? "now_over" : over !== null ? "later_over" : "all_in";
  const inBudget = (text: string): Marked => ({ accent: "debt", icon: "check", text });
  const line: Marked | null =
    status === "now_over"
      ? null
      : status === "later_over" || later.length === 0
        ? inBudget(HOME.withinBudgetNow)
        : inBudget(HOME.allInBudget(later.length)); // the rows the API sent after this month
  return {
    status,
    month: now.month,
    total: now.total,
    barOver: now.over_budget,
    line,
    warning:
      over === null
        ? null
        : { accent: "warn", icon: "alert", text: HOME.overWarning(over.count, thaiMonth(over.first), thaiMonth(over.last), over.together) },
    buffer: over === null || shortfalls === null ? null : firstShortfall(shortfalls),
  };
}

function firstShortfall(out: ShortfallsOut): ShortfallView | null {
  const first = out.months[0];
  return first === undefined ? null : shortfallView(first, out.balance);
}

export const WALLET_SEGMENTS = 6;

export type WalletView = { title: Marked; balance: Money; filled: number; caption: string };

/** The buffer as a wallet: the balance, and one segment per month it covers (at most 6). */
export function walletView(buffer: BufferOut): WalletView {
  const covered = buffer.months_covered; // a count from the API, null when nothing is owed
  return {
    title: { accent: "buffer", icon: ACCENT.buffer.icon, text: HOME.bufferTitle },
    balance: buffer.balance,
    filled: covered === null ? 0 : covered > WALLET_SEGMENTS ? WALLET_SEGMENTS : covered,
    caption: covered === null ? HOME.walletNothingOwed : covered === 0 ? HOME.walletCoversNone : HOME.walletCovers(covered),
  };
}

/**
 * The buffer screen's months covered, only for the balance they were worked out for:
 * after a move the balance shows at once, and the months wait for the next GET /buffer
 * (review F4). Null: not known yet.
 */
export function walletFor(buffer: BufferOut, balance: Money): WalletView | null {
  return toSatang(buffer.balance) === toSatang(balance) ? walletView(buffer) : null;
}

export type ConsolidationView =
  | { kind: "banner"; line: Marked; reason: string }
  | { kind: "offer"; title: Marked; estimate: EstimateOut; currentMonthly: Money | null; benefit: string | null };

/**
 * Not offered (L70): a one-line banner whose reason expands. Offered: the bank's card.
 * Its "ตอนนี้" is the estimate's `current_monthly_total`, this month's total as on the
 * hero. Its one benefit line is the API's `monthly_reduction` (never worked out here),
 * left out unless it is above zero, and when the answer did not carry it (null, from
 * src/apiFields.ts, UI-39). "ทุกเดือนกลับมาอยู่ในงบ" holds for every offer: the plan
 * offers only a loan that brings every month back within budget (L70 b).
 */
export function consolidationView(c: ConsolidationOut): ConsolidationView {
  if (c.estimate === null) {
    return { kind: "banner", line: { accent: "quiet", icon: "info", text: notConsolidatingLine(c.reason) }, reason: ASSIST.reason[c.reason] };
  }
  const reduction = c.estimate.monthly_reduction;
  return {
    kind: "offer",
    title: { accent: "bank", icon: ACCENT.bank.icon, text: ACCENT.bank.label },
    estimate: c.estimate,
    currentMonthly: c.estimate.current_monthly_total,
    benefit: reduction !== null && toSatang(reduction) > 0n ? ASSIST.benefit(formatBaht(reduction)) : null,
  };
}

export type AiBubble = { state: "loading" } | { state: "done"; first: string; rest: string[] };

const linesOf = (text: string) => text.split("\n").filter((line) => line.trim() !== "");

/**
 * The assistant's bubble: the summary's first line, the rest behind "อ่านต่อ". The
 * model's words and the backend's template show the same way, with no tag. A failed
 * request shows the plan's own words (planSummary): never an error or an empty card.
 */
export function aiBubble(load: Load<AssistantSummaryOut>, plan: AssistantPlanOut): AiBubble {
  if (load.state === "loading") return { state: "loading" };
  const said = load.state === "ready" ? linesOf(load.data.text) : [];
  const [first = "", ...rest] = said.length > 0 ? said : linesOf(planSummary(plan));
  return { state: "done", first, rest };
}

export type HomeView = {
  hero: HeroView | null;
  wallet: WalletView;
  assistant: boolean; // the summary puts words around the plan: no plan, no bubble
  consolidation: ConsolidationView | null; // null when the plan did not load
};

export function homeView(data: {
  months: readonly MonthDetail[];
  plan: AssistantPlanOut | null;
  buffer: BufferOut;
  shortfalls: ShortfallsOut | null;
}): HomeView {
  const { months, plan, buffer, shortfalls } = data;
  return {
    hero: heroView(months, shortfalls),
    wallet: walletView(buffer),
    assistant: plan !== null,
    consolidation: plan === null ? null : consolidationView(plan.consolidation),
  };
}
