/**
 * Request and response types for the KidNee screens.
 *
 * Copied from the merged backend (read only, 2026-10-27). Money is always a string
 * ("1500.00"): pydantic serialises Decimal as a JSON string, and requests must send
 * strings with at most 2 decimals (L49). Source file next to each type.
 */
import type { Money } from "./money.ts";

// ---- Errors (backend/app/errors.py) -------------------------------------------

/** Session 13 on: {"detail": {"code", "message"}}. Older errors: a plain string. */
export type CodedDetail = { code: string; message: string };
export type ErrorBody = { detail: CodedDetail | string | unknown[] };

export type ErrorCode =
  | "SETTINGS_REQUIRED"
  | "AMOUNT_ABOVE_BALANCE"
  | "NOT_ME_UNAVAILABLE_FOR_MANUAL_ENTRY";

// ---- /settings (backend/app/user_settings/schemas.py) -------------------------

export type PercentRule = { mode: "percent"; percent: number }; // integer 1-100
export type FixedRule = { mode: "fixed"; amount: Money }; // > 0
/** L63: exactly one mode, never both. */
export type SavingRule = PercentRule | FixedRule;

/** POST /settings (201, 409 if they exist) and PUT /settings (200, 404 if none). */
export type SettingsIn = {
  income: Money;
  payday: number; // day of month, 1-31
  monthly_installment_budget: Money;
  saving_rule: SavingRule;
  auto_save_enabled: boolean;
  auto_save_consent: boolean; // required true when auto_save_enabled
  leftover_saving_enabled: boolean;
};

export const BUDGET_ABOVE_ONE_THIRD_OF_INCOME = "BUDGET_ABOVE_ONE_THIRD_OF_INCOME";

/** GET /settings (404 "settings not found" when none). */
export type SettingsOut = {
  income: Money;
  payday: number;
  monthly_installment_budget: Money;
  saving_rule: SavingRule;
  auto_save_enabled: boolean;
  consent_at: string | null; // ISO datetime
  leftover_saving_enabled: boolean;
  warnings: string[]; // L64: ["BUDGET_ABOVE_ONE_THIRD_OF_INCOME"] or []
};

// ---- Verdict (backend/app/affordability/schemas.py) ---------------------------

export type Verdict = "GREEN" | "YELLOW" | "RED";

export type MonthRow = {
  month: string; // "YYYY-MM"
  total: Money; // installments due that month, the candidate included
  over_budget: boolean;
  over_one_third: boolean;
};

/** POST /installments/preview (200), and RecordedOut.warnings. 409 SETTINGS_REQUIRED. */
export type VerdictOut = {
  verdict: Verdict;
  months: MonthRow[];
  over_budget_months: string[];
  monthly_total: Money; // what is owed per month now (L43)
};

// ---- /installments (backend/app/installments/schemas.py) ----------------------

export type InstallmentKind = "purchase" | "cash_withdrawal" | "cash_loan";

/** The body of both POST /installments/preview and POST /installments. */
export type ManualEntryIn = {
  client_request_id: string; // idempotency key with the user
  kind: InstallmentKind;
  item_price: Money;
  months: number; // 1-600
  monthly_amount: Money;
  first_due_month: string; // "YYYY-MM"
  item_name: string; // may be ""
};

/** POST /installments: 201 new, 200 repeat; 409 reused id or SETTINGS_REQUIRED. */
export type RecordedOut = {
  installment_id: string;
  status: "created" | "duplicate";
  saved_amount: Money; // "0.00" when nothing was saved
  monthly_total: Money; // every installment owed, this one included
  warnings: VerdictOut;
};

// ---- /debts/summary (backend/app/debts/service.py) ----------------------------

export type InstallmentStatus = "active" | "paid_off" | "cancelled" | "disputed";

export type InstallmentLine = {
  id: string;
  vendor: string; // "manual" for entries the user recorded, "shopdemo" for the platform
  contract_id: string;
  kind: InstallmentKind;
  item_name: string;
  principal: Money;
  monthly_amount: Money;
  months: number;
  paid_amount: Money;
  late_fees_accrued: Money;
  remaining: Money;
  status: InstallmentStatus;
  disputed_at: string | null;
  owed: boolean;
};

/** GET /debts/summary. */
export type DebtSummary = {
  monthly_total: Money;
  total_remaining: Money;
  debt_free_date: string | null; // "YYYY-MM-DD"
  installments: InstallmentLine[];
};

/**
 * TODO(backend, Session 15): GET /debts/months?from=YYYY-MM&count=N.
 * Not built yet. Expected shape: the preview's MonthRow per month with no candidate,
 * so Home can list upcoming over-budget months. Mocked until then.
 */
export type UpcomingMonthsOut = { months: MonthRow[] };

// ---- /buffer (backend/app/buffer/schemas.py) ----------------------------------

/** GET /buffer. */
export type BufferOut = {
  balance: Money;
  monthly_total: Money;
  months_covered: number | null; // null when nothing is owed
};

/** POST /buffer/move-to-main: 201 moved, 200 repeat, 409 reused id, 422 AMOUNT_ABOVE_BALANCE. */
export type MoveIn = { client_request_id: string; amount: Money };

export type MovedOut = {
  transaction_id: string;
  status: "created" | "duplicate";
  amount: Money;
  balance: Money; // the buffer after the move
};

// ---- /demo/payday (backend/app/payday/router.py) ------------------------------

export type PaydayIn = { month: string }; // "YYYY-MM"

export type PaydayOutcome =
  | "over_budget"
  | "leftover_saved"
  | "no_leftover"
  | "leftover_off"
  | "safety_net";

/** POST /demo/payday: 201 first run, 200 repeat, 409 SETTINGS_REQUIRED, 404 when demo endpoints are off. */
export type PaydayOut = {
  month: string;
  status: "created" | "duplicate";
  outcome: PaydayOutcome;
  month_total: Money;
  budget: Money;
  amount: Money; // the shortfall or the leftover saved
  buffer_balance: Money;
};
