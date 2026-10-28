/**
 * Home's state rules (DESIGN.md section 7.2, UI-33): which card shows, in which
 * shape, and what it says. A card with nothing to act on shrinks: the hero keeps one
 * status line, consolidation becomes a one-line banner. Every amount, flag and month
 * comes from the API layer (src/api.ts) and is only formatted here; nothing is added
 * up. Every coloured part is a Marked item: an icon and text with its accent (UI-34).
 */
import type {
  AssistantPlanOut,
  AssistantSummaryOut,
  BufferOut,
  BufferPlanOut,
  ConsolidationOut,
  EstimateOut,
  MonthDetail,
} from "./api-types.ts";
import { ACCENT, type Marked } from "./accent.ts";
import { notConsolidatingLine } from "./assistantText.ts";
import { ASSIST, HOME } from "./copy.ts";
import { formatBaht, toSatang, type Money } from "./money.ts";
import type { Route } from "./router.ts";
import { thaiMonth } from "./thaiMonth.ts";
import type { Load } from "./useLoad.ts";

export type OverChip = Marked & { month: string; amount: string; spoken: string };

export type OverStrip = {
  title: Marked;
  chips: OverChip[];
  buffer: Marked | null; // null when the plan did not load
  link: Marked & { route: Route };
};

export type HeroView = {
  status: "all_in" | "later_over" | "now_over";
  month: string;
  total: Money;
  barOver: boolean;
  line: Marked;
  strip: OverStrip | null; // only when some month shown is over budget
};

/** This month's card, from GET /debts/months?count=6 (this month first). */
export function heroView(months: readonly MonthDetail[], plan: BufferPlanOut | null, bufferBalance: Money): HeroView | null {
  const [now, ...later] = months;
  if (now === undefined) return null;
  const over = months.filter((m) => m.over_budget);
  const status = now.over_budget ? "now_over" : over.length > 0 ? "later_over" : "all_in";
  const inBudget = (text: string): Marked => ({ accent: "debt", icon: "check", text });
  const line: Marked =
    status === "now_over"
      ? { accent: "warn", icon: "alert", text: HOME.overBudgetNow }
      : status === "later_over" || later.length === 0
        ? inBudget(HOME.withinBudgetNow)
        : inBudget(HOME.allInBudget(later.length)); // the rows the API sent after this month
  return {
    status,
    month: now.month,
    total: now.total,
    barOver: now.over_budget,
    line,
    strip: over.length === 0 ? null : overStrip(over, plan, bufferBalance),
  };
}

function overStrip(over: readonly MonthDetail[], plan: BufferPlanOut | null, bufferBalance: Money): OverStrip {
  return {
    title: { accent: "warn", icon: "alert", text: HOME.overMonthsTitle },
    chips: over.map((m) => ({
      accent: "warn",
      icon: "alert",
      text: thaiMonth(m.month),
      month: m.month,
      amount: HOME.overBy(formatBaht(m.over_by)),
      spoken: HOME.overBySpoken(formatBaht(m.over_by)),
    })),
    buffer: plan === null ? null : bufferLine(plan),
    // As on the payday alert (UI-17): the buffer while it holds money, else the months.
    link:
      toSatang(bufferBalance) > 0n
        ? { accent: "buffer", icon: ACCENT.buffer.icon, text: HOME.useBuffer, route: "buffer" }
        : { accent: "debt", icon: "calendar", text: HOME.toMonths, route: "months" },
  };
}

/** The plan's buffer line: covers every month over budget, or still short by how much. */
function bufferLine(plan: BufferPlanOut): Marked {
  return plan.covered
    ? { accent: "buffer", icon: ACCENT.buffer.icon, text: ASSIST.covered(formatBaht(plan.balance)) }
    : { accent: "warn", icon: "alert", text: ASSIST.stillShort(formatBaht(plan.balance), formatBaht(plan.still_short)) };
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

export type ConsolidationView =
  | { kind: "banner"; line: Marked; reason: string }
  | { kind: "offer"; title: Marked; estimate: EstimateOut; currentMonthly: Money };

/** Not offered (L70): a one-line banner whose reason expands. Offered: the bank's card. */
export function consolidationView(c: ConsolidationOut, currentMonthly: Money): ConsolidationView {
  return c.estimate === null
    ? { kind: "banner", line: { accent: "quiet", icon: "info", text: notConsolidatingLine(c.reason) }, reason: ASSIST.reason[c.reason] }
    : { kind: "offer", title: { accent: "bank", icon: ACCENT.bank.icon, text: ACCENT.bank.label }, estimate: c.estimate, currentMonthly };
}

export type AiBubble =
  | { state: "loading" }
  | { state: "failed" }
  | { state: "done"; first: string; rest: string[]; example: boolean };

/** The assistant's bubble: the summary's first line, the rest behind "อ่านต่อ". */
export function aiBubble(load: Load<AssistantSummaryOut>): AiBubble {
  if (load.state === "loading") return { state: "loading" };
  if (load.state === "error") return { state: "failed" };
  const [first = "", ...rest] = load.data.text.split("\n").filter((line) => line.trim() !== "");
  return { state: "done", first, rest, example: load.data.is_example };
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
  monthlyTotal: Money;
}): HomeView {
  const { months, plan, buffer, monthlyTotal } = data;
  return {
    hero: heroView(months, plan?.buffer_plan ?? null, buffer.balance),
    wallet: walletView(buffer),
    assistant: plan !== null,
    consolidation: plan === null ? null : consolidationView(plan.consolidation, monthlyTotal),
  };
}
