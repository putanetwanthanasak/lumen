/**
 * The mock backend: answers like the merged FastAPI app, from memory.
 *
 * It mirrors L43 (monthly total), L63 (saving rule and 500.00 safety net), L64
 * (budget warning) and L65 (verdict) closely enough for the demo, with exact BigInt
 * satang. It is NOT the source of truth: the backend tests are. When USE_MOCK is
 * false nothing here runs.
 */
import type {
  AssistantPlanOut,
  AssistantSummaryOut,
  DebtSummary,
  ErrorBody,
  InstallmentLine,
  ManualEntryIn,
  MonthDetail,
  MonthRow,
  MonthsOut,
  MovedOut,
  NotificationOut,
  NotificationsOut,
  PaydayOut,
  PreviewOut,
  RecordedOut,
  SettingsIn,
  SettingsOut,
  SuggestedMonthlyOut,
  Verdict,
  VerdictOut,
} from "../api-types.ts";
import { BUDGET_ABOVE_ONE_THIRD_OF_INCOME } from "../api-types.ts";
import type { Money } from "../money.ts";
import { addMonths, monthOf } from "../thaiMonth.ts";
import {
  DEMO_USER,
  PERSONA_BUFFER_BALANCE,
  PERSONA_MAIN_BALANCE,
  PERSONA_SETTINGS,
  personaInstallments,
  type MockInstallment,
} from "./persona.ts";
import { leftoverAlert, manualEntryAlert, shortfallAlert } from "./alerts.ts";
import { assistantPlan, exampleSummary } from "./assistant.ts";
import { SCENARIOS } from "./persona.ts";
import { fromSatang, sum, toSatang } from "./satang.ts";

/** `delayMs`: extra wait before the answer arrives (the Demo panel's slow assistant). */
export type MockResponse = { status: number; body: unknown; delayMs?: number };

const SAFETY_NET = toSatang("500.00");
export const SLOW_SUMMARY_MS = 15000; // long enough to show and screenshot the loading state
const PLATFORM_MAX = 60;
const CONTROL = /[\u0000-\u001f]/; // L55: no control characters in text fields

type Recorded = { fingerprint: string; installmentId: string; savedAmount: Money };
type Moved = { amount: Money; out: MovedOut };

type Store = {
  settings: SettingsOut | null;
  installments: MockInstallment[];
  mainBalance: Money;
  bufferBalance: Money;
  recorded: Map<string, Recorded>;
  moves: Map<string, Moved>;
  paydays: Map<string, PaydayOut>;
  notifications: NotificationOut[];
  summary: "ok" | "slow" | "failing"; // the Demo panel's assistant states
  today: Date;
};

function freshStore(today: Date): Store {
  return {
    settings: null, // first launch: the app opens on the settings screen
    installments: personaInstallments(today),
    mainBalance: PERSONA_MAIN_BALANCE,
    bufferBalance: PERSONA_BUFFER_BALANCE,
    recorded: new Map(),
    moves: new Map(),
    paydays: new Map(),
    notifications: [],
    summary: "ok",
    today,
  };
}

function notify(alert: { kind: NotificationOut["kind"]; title: string; body: string }): void {
  store.notifications.unshift({ ...alert, id: crypto.randomUUID(), created_at: new Date().toISOString(), read: false });
}

function notificationsOut(): NotificationsOut {
  return { notifications: store.notifications, unread_count: store.notifications.filter((n) => !n.read).length };
}

/**
 * The persona recorded its latest installment by hand, so its alert is the manual
 * entry one (L62), never the webhook's, which offers "Not me" (no "Not me" for
 * manual entries, L68; UI-24). It is unread, so the bell shows 1.
 */
function seedNotifications(): void {
  const latest = store.installments.filter(owed).sort((a, b) => b.first_due_month.localeCompare(a.first_due_month))[0];
  if (latest !== undefined) {
    notify(manualEntryAlert(latest.kind, latest.item_name, latest.principal, latest.months, latest.monthly_amount, monthlyTotal()));
  }
}

let store = freshStore(new Date());
seedNotifications();

// Demo shortcut: "?persona" starts with มิ้นท์'s settings already saved, so a demo or a
// screenshot can open straight on Home (e.g. http://127.0.0.1:5173/?persona#/home).
if (typeof window !== "undefined" && new URLSearchParams(window.location.search).has("persona")) {
  store.settings = toSettingsOut(PERSONA_SETTINGS);
}

/** Start the demo again. `today` is injectable for tests. */
export function resetMock(today: Date = new Date(), withSettings: SettingsIn | null = null): void {
  store = freshStore(today);
  seedNotifications();
  if (withSettings !== null) store.settings = toSettingsOut(withSettings);
}

// ---- helpers ----------------------------------------------------------------

const ok = (body: unknown, status = 200): MockResponse => ({ status, body });
const fail = (status: number, detail: ErrorBody["detail"]): MockResponse => ({
  status,
  body: { detail },
});
const coded = (status: number, code: string, message: string): MockResponse =>
  fail(status, { code, message });

const SETTINGS_REQUIRED = coded(
  409,
  "SETTINGS_REQUIRED",
  "set income and budget with POST /settings first",
);

const MONEY = /^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$/;
const isMoney = (v: unknown): v is Money => typeof v === "string" && MONEY.test(v);
const isInt = (v: unknown, min: number, max: number): v is number =>
  typeof v === "number" && Number.isInteger(v) && v >= min && v <= max;

function invalid(field: string): MockResponse {
  return fail(422, [{ loc: ["body", field], msg: "invalid", type: "value_error" }]);
}

function lastMonth(i: { first_due_month: string; months: number }): string {
  return addMonths(i.first_due_month, i.months - 1);
}

function dueIn(i: MockInstallment, month: string): boolean {
  return i.first_due_month <= month && month <= lastMonth(i);
}

function owed(i: MockInstallment): boolean {
  return toSatang(i.remaining) > 0n;
}

/** L43: the monthly amounts of every installment still owed. */
function monthlyTotal(): Money {
  return sum(store.installments.filter(owed).map((i) => i.monthly_amount));
}

// ---- L64 and L65 ------------------------------------------------------------

function toSettingsOut(data: SettingsIn): SettingsOut {
  const income = toSatang(data.income);
  const budget = toSatang(data.monthly_installment_budget);
  return {
    income: data.income,
    payday: data.payday,
    monthly_installment_budget: data.monthly_installment_budget,
    saving_rule: data.saving_rule,
    auto_save_enabled: data.auto_save_enabled,
    consent_at: data.auto_save_consent ? new Date().toISOString() : null,
    leftover_saving_enabled: data.leftover_saving_enabled,
    // L64: budget * 3 > income, no division; exactly one third does not warn.
    warnings: budget * 3n > income ? [BUDGET_ABOVE_ONE_THIRD_OF_INCOME] : [],
  };
}

type Candidate = { first_due_month: string; months: number; monthly_amount: Money };

/** L65 over the candidate's term. */
export function assess(
  settings: Pick<SettingsOut, "income" | "monthly_installment_budget">,
  installments: readonly MockInstallment[],
  candidate: Candidate,
  includeCandidate: boolean,
): VerdictOut {
  const income = toSatang(settings.income);
  const budget = toSatang(settings.monthly_installment_budget);
  const counted = installments.filter(owed);
  const rows: MonthRow[] = [];
  for (let n = 0; n < candidate.months; n += 1) {
    const month = addMonths(candidate.first_due_month, n);
    let total = counted
      .filter((i) => dueIn(i, month))
      .reduce((acc, i) => acc + toSatang(i.monthly_amount), 0n);
    if (includeCandidate) total += toSatang(candidate.monthly_amount);
    rows.push({
      month,
      total: fromSatang(total),
      over_budget: total > budget,
      over_one_third: total * 3n > income,
    });
  }
  const verdict: Verdict = rows.some((r) => r.over_one_third)
    ? "RED"
    : rows.some((r) => r.over_budget)
      ? "YELLOW"
      : "GREEN";
  return {
    verdict,
    months: rows,
    over_budget_months: rows.filter((r) => r.over_budget).map((r) => r.month),
    monthly_total: fromSatang(
      counted.reduce((acc, i) => acc + toSatang(i.monthly_amount), 0n),
    ),
  };
}

/** L63: one mode; percent rounds down to satang; 0.00 saves nothing; cash never saves. */
export function savingFor(settings: SettingsOut, entry: ManualEntryIn, main: Money): Money {
  if (!settings.auto_save_enabled || settings.consent_at === null) return "0.00";
  if (entry.kind !== "purchase") return "0.00";
  const rule = settings.saving_rule;
  const amount =
    rule.mode === "percent"
      ? (toSatang(entry.item_price) * BigInt(rule.percent)) / 100n
      : toSatang(rule.amount);
  if (amount === 0n) return "0.00";
  // The safety net: skip the whole saving if main would drop below 500.00.
  if (toSatang(main) - amount < SAFETY_NET) return "0.00";
  return fromSatang(amount);
}

// ---- body checks (a small part of the backend's 422 rules) ------------------

function checkSettings(body: unknown): SettingsIn | MockResponse {
  const b = body as Partial<SettingsIn>;
  if (!isMoney(b.income) || toSatang(b.income) === 0n) return invalid("income");
  if (!isInt(b.payday, 1, 31)) return invalid("payday");
  if (!isMoney(b.monthly_installment_budget)) return invalid("monthly_installment_budget");
  const rule = b.saving_rule;
  if (rule === undefined) return invalid("saving_rule");
  if (rule.mode === "percent" && !isInt(rule.percent, 1, 100)) return invalid("saving_rule");
  if (rule.mode === "fixed" && (!isMoney(rule.amount) || toSatang(rule.amount) === 0n)) {
    return invalid("saving_rule");
  }
  if (b.auto_save_enabled === true && b.auto_save_consent !== true) {
    return invalid("auto_save_consent");
  }
  return b as SettingsIn;
}

function checkEntry(body: unknown): ManualEntryIn | MockResponse {
  const b = body as Partial<ManualEntryIn>;
  if (typeof b.client_request_id !== "string" || b.client_request_id === "") {
    return invalid("client_request_id");
  }
  if (!isMoney(b.item_price) || toSatang(b.item_price) === 0n) return invalid("item_price");
  if (!isInt(b.months, 1, 600)) return invalid("months");
  if (!isMoney(b.monthly_amount) || toSatang(b.monthly_amount) === 0n) {
    return invalid("monthly_amount");
  }
  if (typeof b.first_due_month !== "string" || !/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(b.first_due_month)) {
    return invalid("first_due_month");
  }
  // TODO(backend): platform_name is mock only for now.
  const platform = b.platform_name;
  if (platform !== null && platform !== undefined) {
    if (typeof platform !== "string" || platform.trim() === "" || [...platform].length > PLATFORM_MAX || CONTROL.test(platform)) {
      return invalid("platform_name");
    }
  }
  return { ...(b as ManualEntryIn), platform_name: platform ?? null };
}

const isResponse = (v: unknown): v is MockResponse =>
  typeof v === "object" && v !== null && "status" in v && "body" in v;

// ---- endpoints ----------------------------------------------------------------

function previewOrRecord(body: unknown, record: boolean): MockResponse {
  const settings = store.settings;
  if (settings === null) return SETTINGS_REQUIRED;
  const entry = checkEntry(body);
  if (isResponse(entry)) return entry;
  if (!record) {
    // TODO(backend): saving_if_recorded is mock only for now.
    const out: PreviewOut = {
      ...assess(settings, store.installments, entry, true),
      saving_if_recorded: savingFor(settings, entry, store.mainBalance),
    };
    return ok(out);
  }

  const { client_request_id: key, ...fields } = entry;
  const fingerprint = JSON.stringify(fields);
  const previous = store.recorded.get(key);
  if (previous !== undefined && previous.fingerprint !== fingerprint) {
    return fail(409, "client_request_id reused with other fields");
  }
  let recorded = previous;
  if (recorded === undefined) {
    const saved = savingFor(settings, entry, store.mainBalance);
    const id = crypto.randomUUID();
    store.installments.push({
      id,
      vendor: "manual",
      contract_id: `manual-${id.slice(0, 8)}`,
      kind: entry.kind,
      item_name: entry.item_name,
      principal: entry.item_price,
      monthly_amount: entry.monthly_amount,
      months: entry.months,
      paid_amount: "0.00",
      remaining: fromSatang(toSatang(entry.monthly_amount) * BigInt(entry.months)),
      first_due_month: entry.first_due_month,
      platform_name: entry.platform_name,
    });
    store.mainBalance = fromSatang(toSatang(store.mainBalance) - toSatang(saved));
    store.bufferBalance = fromSatang(toSatang(store.bufferBalance) + toSatang(saved));
    recorded = { fingerprint, installmentId: id, savedAmount: saved };
    store.recorded.set(key, recorded);
    notify(manualEntryAlert(entry.kind, entry.item_name, entry.item_price, entry.months, entry.monthly_amount, monthlyTotal()));
  }
  const out: RecordedOut = {
    installment_id: recorded.installmentId,
    status: previous === undefined ? "created" : "duplicate",
    saved_amount: recorded.savedAmount,
    monthly_total: monthlyTotal(),
    // Recorded now, so counted from the Ledger, not added again.
    warnings: assess(settings, store.installments, entry, false),
  };
  return ok(out, previous === undefined ? 201 : 200);
}

function debtSummary(): DebtSummary {
  const lines: InstallmentLine[] = store.installments.map((i) => ({
    id: i.id,
    vendor: i.vendor,
    contract_id: i.contract_id,
    kind: i.kind,
    item_name: i.item_name,
    principal: i.principal,
    monthly_amount: i.monthly_amount,
    months: i.months,
    paid_amount: i.paid_amount,
    late_fees_accrued: "0.00",
    remaining: i.remaining,
    status: owed(i) ? "active" : "paid_off",
    disputed_at: null,
    owed: owed(i),
    platform_name: i.platform_name,
  }));
  const owedLines = store.installments.filter(owed);
  const last = owedLines.map(lastMonth).sort().at(-1);
  return {
    monthly_total: monthlyTotal(),
    total_remaining: sum(owedLines.map((i) => i.remaining)),
    debt_free_date: last === undefined ? null : `${last}-01`,
    installments: lines,
  };
}

/**
 * TODO(backend): GET /debts/months. From this month, with no candidate: `count`
 * months, or up to the last month an owed installment is due.
 */
function months(path: string): MockResponse {
  const settings = store.settings;
  if (settings === null) return SETTINGS_REQUIRED;
  const from = monthOf(store.today);
  const counted = store.installments.filter(owed);
  const countParam = new URLSearchParams(path.split("?")[1] ?? "").get("count");
  let count: number;
  if (countParam === null) {
    const last = counted.map(lastMonth).sort().at(-1);
    count = last === undefined || last < from ? 0 : monthsBetween(from, last) + 1;
  } else {
    count = Number(countParam); // ui-06-allow: a count of months
    if (!isInt(count, 1, 600)) return invalid("count");
  }
  const rows = count === 0 ? [] : assess(settings, store.installments, { first_due_month: from, months: count, monthly_amount: "0.00" }, false).months;
  const budget = toSatang(settings.monthly_installment_budget);
  const out: MonthsOut = {
    months: rows.map(
      (row): MonthDetail => ({
        ...row,
        // TODO(backend): over_by, total - budget when over budget, else 0.00.
        over_by: row.over_budget ? fromSatang(toSatang(row.total) - budget) : "0.00",
        installments: counted
          .filter((i) => dueIn(i, row.month))
          .map((i) => ({
            installment_id: i.id,
            item_name: i.item_name,
            platform_name: i.platform_name,
            monthly_amount: i.monthly_amount,
            installment_no: monthsBetween(i.first_due_month, row.month) + 1,
            installments_total: i.months,
            is_last: row.month === lastMonth(i),
          })),
      }),
    ),
  };
  return ok(out);
}

function monthsBetween(from: string, to: string): number {
  const [fy, fm] = from.split("-").map(Number); // ui-06-allow: a date
  const [ty, tm] = to.split("-").map(Number); // ui-06-allow: a date
  return ((ty ?? 0) - (fy ?? 0)) * 12 + ((tm ?? 0) - (fm ?? 0));
}

/** TODO(backend): GET /installments/suggested-monthly. price / months, rounded UP to 0.01. */
function suggestedMonthly(path: string): MockResponse {
  const query = new URLSearchParams(path.split("?")[1] ?? "");
  const price = query.get("item_price");
  const monthsParam = query.get("months");
  if (!isMoney(price) || toSatang(price) === 0n) return invalid("item_price");
  const n = monthsParam !== null && /^[0-9]{1,3}$/.test(monthsParam) ? BigInt(monthsParam) : 0n;
  if (n < 1n || n > 600n) return invalid("months");
  const out: SuggestedMonthlyOut = { monthly_amount: fromSatang((toSatang(price) + n - 1n) / n) };
  return ok(out);
}

/** POST /buffer/move-to-main (L66): idempotent on client_request_id, never blocked. */
function moveToMain(body: unknown): MockResponse {
  const b = body as { client_request_id?: unknown; amount?: unknown };
  if (typeof b.client_request_id !== "string" || b.client_request_id === "") return invalid("client_request_id");
  if (!isMoney(b.amount) || toSatang(b.amount) === 0n) return invalid("amount");
  const previous = store.moves.get(b.client_request_id);
  if (previous !== undefined) {
    if (toSatang(previous.amount) !== toSatang(b.amount)) {
      return fail(409, "client_request_id reused with another amount");
    }
    return ok({ ...previous.out, status: "duplicate", balance: store.bufferBalance }, 200);
  }
  if (toSatang(b.amount) > toSatang(store.bufferBalance)) {
    return coded(422, "AMOUNT_ABOVE_BALANCE", "the buffer holds less than this amount");
  }
  store.bufferBalance = fromSatang(toSatang(store.bufferBalance) - toSatang(b.amount));
  store.mainBalance = fromSatang(toSatang(store.mainBalance) + toSatang(b.amount));
  const out: MovedOut = {
    transaction_id: crypto.randomUUID(),
    status: "created",
    amount: b.amount,
    balance: store.bufferBalance,
  };
  store.moves.set(b.client_request_id, { amount: b.amount, out });
  return ok(out, 201);
}

/** POST /demo/payday (L67), in the backend's decision order; once per month. */
function payday(body: unknown): MockResponse {
  const settings = store.settings;
  if (settings === null) return SETTINGS_REQUIRED;
  const month = (body as { month?: unknown }).month;
  if (typeof month !== "string" || !/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(month)) return invalid("month");
  const stored = store.paydays.get(month);
  if (stored !== undefined) return ok({ ...stored, status: "duplicate" }, 200);

  const row = assess(settings, store.installments, { first_due_month: month, months: 1, monthly_amount: "0.00" }, false)
    .months[0];
  const total = toSatang(row?.total ?? "0.00");
  const budget = toSatang(settings.monthly_installment_budget);
  let outcome: PaydayOut["outcome"] = "leftover_off";
  let amount = 0n;
  if (total > budget) {
    outcome = "over_budget";
    amount = total - budget;
  } else if (total === budget) {
    outcome = "no_leftover";
  } else if (settings.leftover_saving_enabled && settings.auto_save_enabled && settings.consent_at !== null) {
    const leftover = budget - total;
    if (toSatang(store.mainBalance) - leftover < SAFETY_NET) {
      outcome = "safety_net";
    } else {
      outcome = "leftover_saved";
      amount = leftover;
      store.mainBalance = fromSatang(toSatang(store.mainBalance) - leftover);
      store.bufferBalance = fromSatang(toSatang(store.bufferBalance) + leftover);
    }
  }
  const out: PaydayOut = {
    month,
    status: "created",
    outcome,
    month_total: fromSatang(total),
    budget: settings.monthly_installment_budget,
    amount: fromSatang(amount),
    buffer_balance: store.bufferBalance,
  };
  if (outcome === "over_budget") {
    notify(shortfallAlert(month, out.month_total, out.amount, store.bufferBalance, toSatang(store.bufferBalance) === 0n));
  } else if (outcome === "leftover_saved") {
    notify(leftoverAlert(month, out.month_total, out.amount));
  }
  store.paydays.set(month, out);
  return ok(out, 201);
}

function recordScenario(name: keyof typeof SCENARIOS, firstDue: string): void {
  const s = SCENARIOS[name];
  previewOrRecord(
    {
      client_request_id: `demo-scene-${name}`,
      kind: "purchase",
      item_name: s.item_name,
      item_price: s.item_price,
      months: s.months,
      monthly_amount: s.monthly_amount,
      first_due_month: firstDue,
    },
    true,
  );
}

/** GET /assistant/plan over the installments still owed. */
function planNow(settings: SettingsOut): AssistantPlanOut {
  return assistantPlan(
    store.installments.filter(owed),
    monthOf(store.today),
    settings.income,
    settings.monthly_installment_budget,
    store.bufferBalance,
  );
}

/** Mock only: put the demo in a known state (the Demo panel). */
function demoScene(body: unknown): MockResponse {
  const scene = (body as { scene?: unknown }).scene;
  if (scene === "first_launch") {
    resetMock(store.today);
  } else if (scene === "persona") {
    resetMock(store.today, PERSONA_SETTINGS);
  } else if (scene === "over_budget") {
    // Two months over budget from next month: buffer covers it, no consolidation.
    resetMock(store.today, PERSONA_SETTINGS);
    recordScenario("YELLOW", addMonths(monthOf(store.today), 1));
  } else if (scene === "over_budget_now") {
    // Over budget from this month for 9 months: pause, buffer still short, and
    // consolidation is worth asking about (L70).
    resetMock(store.today, PERSONA_SETTINGS);
    recordScenario("RED", monthOf(store.today));
  } else if (scene === "over_budget_empty_buffer") {
    // As over_budget, then the whole buffer moved back to the main account (L66), by
    // the same path as the screen, so no money disappears (review F5).
    resetMock(store.today, PERSONA_SETTINGS);
    recordScenario("YELLOW", addMonths(monthOf(store.today), 1));
    const moved = moveToMain({ client_request_id: "scene-empty-buffer", amount: store.bufferBalance });
    if (moved.status !== 201) return moved;
  } else if (scene === "ai_slow" || scene === "ai_failing") {
    // The persona, with the assistant's summary slow (loading state) or failing.
    resetMock(store.today, PERSONA_SETTINGS);
    store.summary = scene === "ai_slow" ? "slow" : "failing";
  } else {
    return invalid("scene");
  }
  return ok({ scene }, 200);
}

/** Route one request, as FastAPI would. The demo user is the only user. */
export function handle(
  method: string,
  path: string,
  body: unknown,
  user: string | null,
): MockResponse {
  if (user !== DEMO_USER) return fail(401, "unauthorized");
  const route = `${method} ${path.split("?")[0] ?? path}`;
  switch (route) {
    case "GET /settings":
      return store.settings === null ? fail(404, "settings not found") : ok(store.settings);
    case "POST /settings": {
      if (store.settings !== null) return fail(409, "settings already exist");
      const data = checkSettings(body);
      if (isResponse(data)) return data;
      store.settings = toSettingsOut(data);
      return ok(store.settings, 201);
    }
    case "PUT /settings": {
      if (store.settings === null) return fail(404, "settings not found");
      const data = checkSettings(body);
      if (isResponse(data)) return data;
      store.settings = toSettingsOut(data);
      return ok(store.settings);
    }
    case "POST /installments/preview":
      return previewOrRecord(body, false);
    case "POST /installments":
      return previewOrRecord(body, true);
    case "GET /debts/summary":
      return ok(debtSummary());
    case "GET /debts/months":
      return months(path);
    case "GET /installments/suggested-monthly":
      return suggestedMonthly(path);
    case "POST /buffer/move-to-main":
      return moveToMain(body);
    case "POST /demo/payday":
      return payday(body);
    case "GET /notifications":
      return ok(notificationsOut());
    case "POST /notifications/read":
      store.notifications = store.notifications.map((n) => ({ ...n, read: true }));
      return ok(notificationsOut());
    case "GET /assistant/plan":
      return store.settings === null ? SETTINGS_REQUIRED : ok(planNow(store.settings));
    case "POST /assistant/summary": {
      // TODO(backend, tomorrow): the AI summary. The mock is a fixed example.
      if (store.settings === null) return SETTINGS_REQUIRED;
      if (store.summary === "failing") return fail(503, "summary unavailable");
      const out: AssistantSummaryOut = { text: exampleSummary(planNow(store.settings)), is_example: true };
      return store.summary === "slow" ? { ...ok(out), delayMs: SLOW_SUMMARY_MS } : ok(out);
    }
    case "POST /demo/scene":
      return demoScene(body);
    case "GET /buffer": {
      const total = monthlyTotal();
      const t = toSatang(total);
      return ok({
        balance: store.bufferBalance,
        monthly_total: total,
        months_covered: t === 0n ? null : Number(toSatang(store.bufferBalance) / t), // ui-06-allow: a count of months
      });
    }
    default:
      return fail(404, "Not Found");
  }
}
