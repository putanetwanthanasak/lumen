/**
 * The เช็กก่อนผ่อน form and its stages as data (screen 3), kept apart from React so
 * they can be tested (UI-16). Money stays the string the user typed (L49).
 *
 * A preview answer is shown only if the screen is still waiting for that very
 * request: editing the form while it is in flight drops the answer, so "บันทึก"
 * never records a plan the screen does not show (review round 2, F2). Recording
 * sends the previewed entry unchanged, so a retry reuses its client_request_id and
 * records once (F3).
 *
 * The first due month has no default: the user picks this month or next month, as
 * the app's summary page says (UI-18).
 *
 * The price and the monthly amount are linked both ways (UI-72, Session 25). Each is
 * typed (the user entered it) or calculated. Only the price typed: the monthly amount
 * is the API's 0% suggestion (price / months rounded up, the backend's own rule).
 * Only the monthly amount typed: the price is monthly x months, exact (money.ts
 * timesMonths). Both typed: neither is ever recalculated, the months included, so a
 * plan with the app's interest (12,000 at 2,100 x 6) is sent as typed. Clearing a
 * field makes it calculated again. The entry sends both as strings, as before.
 *
 * The four fields the preview needs come first; the item name and the app are
 * optional (UI-37). The check stays disabled until all four are valid, and a field
 * shows its error once the user leaves it with something typed.
 */
import type { InstallmentKind, ManualEntryIn, PreviewOut } from "./api-types.ts";
import { MONEY_ERRORS, REJECTED, THINK } from "./copy.ts";
import { parseMoneyInput, timesMonths, type Money } from "./money.ts";
import { addMonths, monthOf } from "./thaiMonth.ts";

export type Form = {
  kind: InstallmentKind;
  name: string;
  platform: string;
  price: string;
  months: string;
  monthly: string;
  /** The user entered the price (else it is calculated, or empty) (UI-72). */
  priceTyped: boolean;
  /** The user entered the monthly amount (else it is calculated, or empty) (UI-72). */
  monthlyTyped: boolean;
  firstDue: string; // "" until the user picks a month
};
/** The three fields the calculation links (UI-72). */
export type LinkedKey = "price" | "months" | "monthly";
export type FieldKey = "price" | "months" | "monthly" | "firstDue" | "platform";
/** A 422 can name the item name too, which the form never refuses itself. */
export type RejectedKey = FieldKey | "name";
export type Errors = Partial<Record<FieldKey, string>>;

const MONTHS = /^([1-9][0-9]{0,2})$/;
export const PLATFORM_MAX = 60;

export function emptyForm(): Form {
  return {
    kind: "purchase",
    name: "",
    platform: "",
    price: "",
    months: "",
    monthly: "",
    priceTyped: false,
    monthlyTyped: false,
    firstDue: "",
  };
}

/** The two first-due choices: this month and next month ("YYYY-MM"). */
export function firstDueChoices(today: Date): { thisMonth: string; nextMonth: string } {
  const thisMonth = monthOf(today);
  return { thisMonth, nextMonth: addMonths(thisMonth, 1) };
}

/** Quick picks under จำนวนเดือนที่ผ่อน: a tap fills the field, typing still works (UI-37). */
export const MONTH_CHIPS = [3, 6, 10, 12] as const;

/**
 * "ประเมินภาระผ่อน" stays disabled until every required field is valid: the price
 * (or the cash amount), the months, the monthly amount and the first due month,
 * which has no default (UI-18, UI-37).
 */
export function canPreview(form: Form): boolean {
  return toEntry(form, "").ok;
}

/**
 * The errors to show: a field's own once the user has left it with something typed
 * (an empty field is only not done yet; the bar's hint says so), or every error after
 * a check that could not be sent (UI-37).
 */
export function shownErrors(form: Form, touched: ReadonlySet<FieldKey> | "all"): Errors {
  const built = toEntry(form, "");
  if (built.ok) return {};
  if (touched === "all") return built.errors;
  // A price calculated from the monthly amount is the user's once they leave that field:
  // its one possible error (too large) shows under it then (UI-72).
  const seen = new Set(touched);
  if (form.monthlyTyped && !form.priceTyped && seen.has("monthly")) seen.add("price");
  const shown: Errors = {};
  for (const key of seen) {
    const error = built.errors[key];
    if (error !== undefined && form[key].trim() !== "") shown[key] = error;
  }
  return shown;
}

function monthCount(form: Form): number {
  const months = form.months.trim();
  return MONTHS.test(months) ? Number(months) : 0; // ui-06-allow: a count of months
}

export function toEntry(form: Form, requestId: string): { ok: true; entry: ManualEntryIn } | { ok: false; errors: Errors } {
  const errors: Errors = {};
  const price = parseMoneyInput(form.price);
  const monthly = parseMoneyInput(form.monthly);
  const count = monthCount(form);
  const platform = form.platform.trim();
  if (!price.ok) errors.price = MONEY_ERRORS[price.reason];
  if (!monthly.ok) errors.monthly = MONEY_ERRORS[monthly.reason];
  if (count < 1 || count > 600) errors.months = THINK.monthsError;
  if (form.firstDue === "") errors.firstDue = THINK.firstDueError;
  if ([...platform].length > PLATFORM_MAX) errors.platform = THINK.platformTooLong;
  if (!price.ok || !monthly.ok || Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    entry: {
      client_request_id: requestId,
      kind: form.kind,
      item_price: price.value,
      months: count,
      monthly_amount: monthly.value,
      first_due_month: form.firstDue,
      item_name: form.name.trim(),
      platform_name: platform === "" ? null : platform,
    },
  };
}

const FIELD_OF_API: Record<string, RejectedKey> = {
  item_name: "name",
  platform_name: "platform",
  item_price: "price",
  months: "months",
  monthly_amount: "monthly",
  first_due_month: "firstDue",
};

/**
 * The fields a 422 refused (ApiError.fields), as the form's fields, each with the
 * same words. Null when it named none of them: the screen then says the check failed.
 */
export function rejectedErrors(fields: readonly string[]): Partial<Record<RejectedKey, string>> | null {
  const keys = fields.flatMap((name) => FIELD_OF_API[name] ?? []);
  return keys.length === 0 ? null : Object.fromEntries(keys.map((key) => [key, REJECTED]));
}

// ---- the two-way link: price, months, monthly amount (UI-72) ----------------------

type Ask = { price: Money; months: number };

/** What to ask the API for, or null when the user typed the monthly amount or the inputs are not ready. */
export function suggestionRequest(form: Form): Ask | null {
  if (form.monthlyTyped) return null;
  const price = parseMoneyInput(form.price);
  const count = monthCount(form);
  if (!price.ok || count < 1 || count > 600) return null;
  return { price: price.value, months: count };
}

const sameAsk = (a: Ask | null, b: Ask | null) => a !== null && b !== null && a.price === b.price && a.months === b.months;

/** Prefill the suggestion only if it still matches the form and the monthly amount is still not typed. */
export function applySuggestion(form: Form, asked: Ask, monthly: Money): Form {
  return sameAsk(suggestionRequest(form), asked) ? { ...form, monthly } : form;
}

/** monthly x months, exact; null while either is not valid. */
function priceFromMonthly(form: Form): Money | null {
  const monthly = parseMoneyInput(form.monthly);
  const count = monthCount(form);
  return monthly.ok && count >= 1 && count <= 600 ? timesMonths(monthly.value, count) : null;
}

/**
 * The user typed in the price, the months or the monthly amount (a month chip too).
 * Typing something in the price or the monthly amount marks it typed; clearing it
 * (empty) marks it calculated again. Then:
 * - both typed: neither is recalculated, whatever changed (the months included);
 * - only the monthly amount typed: the price is monthly x months now, or empty while
 *   it cannot be calculated;
 * - only the price typed: the monthly amount is emptied whenever the suggestion it held
 *   no longer answers the price and months, and the API's answer fills it again
 *   (applySuggestion); an old answer never stands for a new price;
 * - neither typed: nothing to calculate from, so both are empty.
 */
export function typeLinked(form: Form, key: LinkedKey, value: string): Form {
  const typed = value.trim() !== "";
  const next: Form = {
    ...form,
    [key]: value,
    ...(key === "price" ? { priceTyped: typed } : key === "monthly" ? { monthlyTyped: typed } : {}),
  };
  if (next.priceTyped && next.monthlyTyped) return next;
  if (next.monthlyTyped) return { ...next, price: priceFromMonthly(next) ?? "" };
  if (!next.priceTyped) return { ...next, price: "", monthly: "" };
  const stillAnswers = !form.monthlyTyped && sameAsk(suggestionRequest(form), suggestionRequest(next));
  return stillAnswers ? next : { ...next, monthly: "" };
}

/** The fields a keystroke in a linked field changes: that field, and any it recalculated. */
export function changedBy(form: Form, key: LinkedKey, value: string): LinkedKey[] {
  const next = typeLinked(form, key, value);
  const recalculated = (["price", "monthly"] as const).filter((field) => field !== key && next[field] !== form[field]);
  return [key, ...recalculated];
}

/**
 * The API's refusals (422) left once these fields changed: a changed field holds a new
 * value, so its refusal goes, a recalculated field's too (review F3).
 */
export function withoutRejected(
  rejected: Partial<Record<RejectedKey, string>>,
  keys: readonly string[],
): Partial<Record<RejectedKey, string>> {
  if (!keys.some((key) => key in rejected)) return rejected;
  return Object.fromEntries(Object.entries(rejected).filter(([key]) => !keys.includes(key)));
}

/**
 * The one line under the calculated field, while it holds a calculated value (UI-72):
 * THINK.fromPrice under the monthly amount, THINK.fromMonthly under the price. Null
 * when both are typed (nothing is calculated), and before there is a value: the
 * monthly amount then keeps its usual help while it is not typed.
 */
export function calculatedNote(form: Form): { field: "price" | "monthly"; text: string } | null {
  if (form.priceTyped && form.monthlyTyped) return null;
  if (form.monthlyTyped) return form.price === "" ? null : { field: "price", text: THINK.fromMonthly };
  return form.monthly === "" || suggestionRequest(form) === null ? null : { field: "monthly", text: THINK.fromPrice };
}

// ---- stages ---------------------------------------------------------------------

export type Stage =
  | { name: "form" }
  | { name: "checking"; entry: ManualEntryIn }
  | { name: "verdict"; entry: ManualEntryIn; verdict: PreviewOut };

export function startPreview(entry: ManualEntryIn): Stage {
  return { name: "checking", entry };
}

/** Any edit makes a new entry: a pending or shown verdict no longer applies. */
export function edit(_stage: Stage): Stage {
  return { name: "form" };
}

/** Show the answer only if the screen still waits for this request. */
export function answerPreview(stage: Stage, requestId: string, verdict: PreviewOut): Stage {
  if (stage.name !== "checking" || stage.entry.client_request_id !== requestId) return stage;
  return { name: "verdict", entry: stage.entry, verdict };
}

/** What "บันทึก" sends: the previewed entry, unchanged, every time it is tapped. */
export function entryToRecord(stage: Stage): ManualEntryIn | null {
  return stage.name === "verdict" ? stage.entry : null;
}

// ---- the draft kept between the form and the result screen ------------------------

export type Draft = { form: Form; stage: Stage };

let draft: Draft | null = null;

/** The form and its verdict survive the move to the result screen and back ("แก้ไข"). */
export function getDraft(): Draft | null {
  return draft;
}

export function setDraft(next: Draft | null): void {
  draft = next;
}
