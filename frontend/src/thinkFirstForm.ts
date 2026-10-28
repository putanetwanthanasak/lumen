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
 * the app's summary page says (UI-18). The monthly amount is prefilled with the
 * API's 0% suggestion until the user edits it, and an edited value is never
 * overwritten (UI-18).
 */
import type { InstallmentKind, ManualEntryIn, PreviewOut } from "./api-types.ts";
import { MONEY_ERRORS, THINK } from "./copy.ts";
import { parseMoneyInput, type Money } from "./money.ts";
import { addMonths, monthOf } from "./thaiMonth.ts";

export type Form = {
  kind: InstallmentKind;
  name: string;
  platform: string;
  price: string;
  months: string;
  monthly: string;
  /** True once the user typed in the monthly field: a suggestion never replaces it. */
  monthlyEdited: boolean;
  firstDue: string; // "" until the user picks a month
};
export type Errors = Partial<Record<"price" | "months" | "monthly" | "firstDue" | "platform", string>>;

const MONTHS = /^([1-9][0-9]{0,2})$/;
export const PLATFORM_MAX = 60;

export function emptyForm(): Form {
  return { kind: "purchase", name: "", platform: "", price: "", months: "", monthly: "", monthlyEdited: false, firstDue: "" };
}

/** The two first-due choices: this month and next month ("YYYY-MM"). */
export function firstDueChoices(today: Date): { thisMonth: string; nextMonth: string } {
  const thisMonth = monthOf(today);
  return { thisMonth, nextMonth: addMonths(thisMonth, 1) };
}

/** "ประเมินภาระผ่อน" stays disabled until a first due month is chosen. */
export function canPreview(form: Form): boolean {
  return form.firstDue !== "";
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

// ---- the 0% suggestion ----------------------------------------------------------

/** What to ask the API for, or null when the monthly field is the user's own or the inputs are not ready. */
export function suggestionRequest(form: Form): { price: Money; months: number } | null {
  if (form.monthlyEdited) return null;
  const price = parseMoneyInput(form.price);
  const count = monthCount(form);
  if (!price.ok || count < 1 || count > 600) return null;
  return { price: price.value, months: count };
}

/** Prefill the suggestion only if it still matches the form and the user has not edited the field. */
export function applySuggestion(form: Form, asked: { price: Money; months: number }, monthly: Money): Form {
  const now = suggestionRequest(form);
  if (now === null || now.price !== asked.price || now.months !== asked.months) return form;
  return { ...form, monthly };
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
