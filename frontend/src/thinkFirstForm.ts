/**
 * The คิดก่อน form and its stages as data (screen 3), kept apart from React so they
 * can be tested (UI-16). Money stays the string the user typed (L49).
 *
 * A preview answer is shown only if the screen is still waiting for that very
 * request: editing the form while it is in flight drops the answer, so "บันทึก"
 * never records a plan the screen does not show (review round 2, F2). Recording
 * sends the previewed entry unchanged, so a retry reuses its client_request_id and
 * records once (F3).
 */
import type { InstallmentKind, ManualEntryIn, VerdictOut } from "./api-types.ts";
import { MONEY_ERRORS, THINK } from "./copy.ts";
import { parseMoneyInput } from "./money.ts";
import { addMonths, monthOf } from "./thaiMonth.ts";

export type Form = {
  kind: InstallmentKind;
  name: string;
  price: string;
  months: string;
  monthly: string;
  firstDue: string;
};
export type Errors = Partial<Record<"price" | "months" | "monthly", string>>;

const MONTHS = /^([1-9][0-9]{0,2})$/;

export function emptyForm(today: Date): Form {
  return { kind: "purchase", name: "", price: "", months: "", monthly: "", firstDue: addMonths(monthOf(today), 1) };
}

export function toEntry(form: Form, requestId: string): { ok: true; entry: ManualEntryIn } | { ok: false; errors: Errors } {
  const errors: Errors = {};
  const price = parseMoneyInput(form.price);
  const monthly = parseMoneyInput(form.monthly);
  const months = form.months.trim();
  if (!price.ok) errors.price = MONEY_ERRORS[price.reason];
  if (!monthly.ok) errors.monthly = MONEY_ERRORS[monthly.reason];
  const count = MONTHS.test(months) ? Number(months) : 0; // ui-06-allow: a count of months
  if (count < 1 || count > 600) errors.months = THINK.monthsError;
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
    },
  };
}

export type Stage =
  | { name: "form" }
  | { name: "checking"; entry: ManualEntryIn }
  | { name: "verdict"; entry: ManualEntryIn; verdict: VerdictOut };

export function startPreview(entry: ManualEntryIn): Stage {
  return { name: "checking", entry };
}

/** Any edit makes a new entry: a pending or shown verdict no longer applies. */
export function edit(_stage: Stage): Stage {
  return { name: "form" };
}

/** Show the answer only if the screen still waits for this request. */
export function answerPreview(stage: Stage, requestId: string, verdict: VerdictOut): Stage {
  if (stage.name !== "checking" || stage.entry.client_request_id !== requestId) return stage;
  return { name: "verdict", entry: stage.entry, verdict };
}

/** What "บันทึก" sends: the previewed entry, unchanged, every time it is tapped. */
export function entryToRecord(stage: Stage): ManualEntryIn | null {
  return stage.name === "verdict" ? stage.entry : null;
}
