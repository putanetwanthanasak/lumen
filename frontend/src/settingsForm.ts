/**
 * The settings form as data (screen 1), kept apart from React so it can be tested.
 * Money stays the string the user typed; nothing is rounded (L49).
 */
import type { SettingsIn, SettingsOut } from "./api-types.ts";
import { MONEY_ERRORS, REJECTED, SETTINGS } from "./copy.ts";
import { parseMoneyInput } from "./money.ts";

export type Form = {
  income: string;
  payday: string;
  budget: string;
  mode: "percent" | "fixed";
  percent: string;
  fixed: string;
  autoSave: boolean;
  leftover: boolean;
  consent: boolean;
};

export const EMPTY: Form = {
  income: "",
  payday: "",
  budget: "",
  mode: "percent",
  percent: "10",
  fixed: "",
  autoSave: true,
  leftover: true,
  consent: false,
};

export function fromSettings(s: SettingsIn | SettingsOut): Form {
  return {
    income: s.income,
    payday: String(s.payday),
    budget: s.monthly_installment_budget,
    mode: s.saving_rule.mode,
    percent: s.saving_rule.mode === "percent" ? String(s.saving_rule.percent) : "10",
    fixed: s.saving_rule.mode === "fixed" ? s.saving_rule.amount : "",
    autoSave: s.auto_save_enabled,
    leftover: s.leftover_saving_enabled,
    consent: "consent_at" in s ? s.consent_at !== null : s.auto_save_consent,
  };
}

export type Errors = Partial<Record<"income" | "payday" | "budget" | "percent" | "fixed" | "consent", string>>;

const INT_1_TO_31 = /^([1-9]|[12][0-9]|3[01])$/;
const INT_1_TO_100 = /^([1-9][0-9]?|100)$/;
const DEFAULT_RULE = { mode: "percent", percent: 10 } as const;

const FIELD_OF_API: Record<string, keyof Errors> = {
  income: "income",
  payday: "payday",
  monthly_installment_budget: "budget",
  percent: "percent",
  amount: "fixed",
  auto_save_consent: "consent",
};

/** The fields a 422 refused (ApiError.fields), as the form's; null when it named none of them. */
export function rejectedErrors(fields: readonly string[]): Errors | null {
  const keys = fields.flatMap((name) => FIELD_OF_API[name] ?? []);
  return keys.length === 0 ? null : Object.fromEntries(keys.map((key) => [key, REJECTED]));
}

/** Build the request, or the errors to show. Money stays the string the user typed. */
export function toRequest(form: Form): { ok: true; body: SettingsIn } | { ok: false; errors: Errors } {
  const errors: Errors = {};
  const income = parseMoneyInput(form.income);
  const budget = parseMoneyInput(form.budget);
  const fixed = parseMoneyInput(form.fixed);
  if (!income.ok) errors.income = MONEY_ERRORS[income.reason];
  if (!budget.ok) errors.budget = MONEY_ERRORS[budget.reason];
  if (!INT_1_TO_31.test(form.payday.trim())) errors.payday = SETTINGS.paydayError;
  const percentOk = INT_1_TO_100.test(form.percent.trim());
  // The rule fields are shown only while auto-save is on, so only then are they
  // checked (review F3: a hidden error made the form impossible to save).
  if (form.autoSave) {
    if (form.mode === "percent" && !percentOk) errors.percent = SETTINGS.percentError;
    if (form.mode === "fixed" && !fixed.ok) errors.fixed = MONEY_ERRORS[fixed.reason];
    if (!form.consent) errors.consent = SETTINGS.consentError;
  }
  if (!income.ok || !budget.ok || Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    body: {
      income: income.value,
      payday: Number(form.payday.trim()), // ui-06-allow: a day of the month
      monthly_installment_budget: budget.value,
      // L63: exactly one mode is sent, never both. The API needs a rule even with
      // auto-save off; then an unfinished one falls back to the default 10%.
      saving_rule:
        form.mode === "fixed" && fixed.ok
          ? { mode: "fixed", amount: fixed.value }
          : form.mode === "percent" && percentOk
            ? { mode: "percent", percent: Number(form.percent.trim()) } // ui-06-allow: a whole percent
            : DEFAULT_RULE,
      auto_save_enabled: form.autoSave,
      auto_save_consent: form.autoSave && form.consent,
      leftover_saving_enabled: form.leftover,
    },
  };
}

