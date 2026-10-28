/**
 * Request and response types for the KidNee screens.
 *
 * Copied from the merged backend (read only; checked against docs/api/kidnee-endpoints.md
 * on 2026-10-29, Session 17). Money is always a string
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

/**
 * POST /installments/preview. `saving_if_recorded` is the amount POST /installments
 * would save for this entry right now (L63: same rule, same 500.00 safety net,
 * "0.00" when nothing would be saved).
 */
export type PreviewOut = VerdictOut & { saving_if_recorded: Money };

// ---- /installments (backend/app/installments/schemas.py) ----------------------

export type InstallmentKind = "purchase" | "cash_withdrawal" | "cash_loan";
/** What an answer may say: a consolidation loan (L72) is never in a request. */
export type LineKind = InstallmentKind | "consolidation_loan";

/** The body of both POST /installments/preview and POST /installments. */
export type ManualEntryIn = {
  client_request_id: string; // idempotency key with the user
  kind: InstallmentKind;
  item_price: Money;
  months: number; // 1-600
  monthly_amount: Money;
  first_due_month: string; // "YYYY-MM"
  item_name: string; // may be ""
  /**
   * The app the user pays through, free text, 1 to 60 characters, no control
   * characters; null when not given ("" is a 422, so the form trims and sends null).
   * Never a list of real platform names (rule 5).
   */
  platform_name: string | null;
};

/**
 * GET /installments/suggested-monthly?item_price=&months=
 * The 0% monthly amount the เช็กก่อนผ่อน form prefills: item_price / months, rounded UP
 * to 0.01 (so the payments never add up to less than the price).
 */
export type SuggestedMonthlyOut = { monthly_amount: Money };

/** POST /installments: 201 new, 200 repeat; 409 reused id or SETTINGS_REQUIRED. */
export type RecordedOut = {
  installment_id: string;
  status: "created" | "duplicate";
  saved_amount: Money; // "0.00" when nothing was saved
  monthly_total: Money; // every installment owed, this one included
  warnings: VerdictOut;
};

// ---- /debts/summary (backend/app/debts/service.py) ----------------------------

/** `consolidated`: paid off by a consolidation loan (L72), not owed, history kept. */
export type InstallmentStatus = "active" | "paid_off" | "cancelled" | "disputed" | "consolidated";

export type InstallmentLine = {
  id: string;
  vendor: string; // "manual" for entries the user recorded, "shopdemo" for the platform
  contract_id: string;
  kind: LineKind;
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
  platform_name: string | null; // null when not named; absent reads as null (apiFields.ts)
  first_due_date: string; // "YYYY-MM-DD"
  last_due_date: string; // "YYYY-MM-DD"
};

/** GET /debts/summary. */
export type DebtSummary = {
  monthly_total: Money;
  total_remaining: Money;
  debt_free_date: string | null; // "YYYY-MM-DD"
  installments: InstallmentLine[];
};

/** One installment due in a month (GET /debts/months). */
export type MonthInstallment = {
  installment_id: string;
  item_name: string;
  platform_name: string | null; // null when not named; absent reads as null (apiFields.ts)
  monthly_amount: Money;
  installment_no: number; // "งวดที่ x": 1 in the first due month
  installments_total: number; // "จาก y": the installment's months
  is_last: boolean; // its last due month
  last_month: string; // "YYYY-MM", its last due month
};

/** A month row with the budget, how far over it (`over_by`, "0.00" when not), and what is due. */
export type MonthDetail = MonthRow & { budget: Money; over_by: Money; installments: MonthInstallment[] };

/**
 * GET /debts/months[?count=N]. From this month: N months when `count` is given,
 * otherwise up to the last month with an installment due (at most 600 rows,
 * `months_truncated`). Each row is the preview's MonthRow with no candidate (the
 * L43 owed set, full monthly amount in every scheduled month, L65 flags) plus the
 * installments due that month, in the order recorded. 409 SETTINGS_REQUIRED.
 */
export type MonthsOut = { months: MonthDetail[]; months_truncated: boolean };

// ---- /buffer (backend/app/buffer/schemas.py) ----------------------------------

/** GET /buffer. */
export type BufferOut = {
  balance: Money;
  monthly_total: Money;
  months_covered: number | null; // null when nothing is owed
};

/**
 * POST /buffer/move-to-main: 201 moved, 200 repeat, 409 reused id (another amount or
 * month), 422 AMOUNT_ABOVE_BALANCE. `for_month` ("YYYY-MM") labels the money for a
 * month over budget ("ใช้กันชนจ่ายส่วนที่เกิน"); a free move leaves it out. A label
 * only: it never limits or blocks the move (L66).
 */
export type MoveIn = { client_request_id: string; amount: Money; for_month?: string };

export type MovedOut = {
  transaction_id: string;
  status: "created" | "duplicate";
  amount: Money;
  for_month: string | null;
  balance: Money; // the buffer after the move
};

/** Whether the user moved money for a month over budget (Session 17); the API decides it. */
export type PreparedState = "not_prepared" | "partly_prepared" | "prepared";

/** One month over budget (GET /buffer/shortfalls). total, budget and shortfall never change after a move. */
export type ShortfallMonth = {
  month: string;
  total: Money;
  budget: Money;
  shortfall: Money; // total - budget
  prepared: Money; // moved to the main account for this month
  remaining_gap: Money; // max(0, shortfall - prepared)
  state: PreparedState;
  covered_by_buffer: Money; // what the buffer covers of remaining_gap, months in date order
  still_short: Money;
};

/** GET /buffer/shortfalls: every month over budget from this month on. 409 SETTINGS_REQUIRED. */
export type ShortfallsOut = {
  balance: Money;
  shortfall: Money;
  remaining_gap: Money;
  covered: boolean;
  still_short: Money;
  months: ShortfallMonth[];
  months_truncated: boolean;
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

// ---- Notifications (screen 5) -------------------------------------------------

export type NotificationKind =
  | "new_debt"
  | "cash_withdrawal"
  | "cash_loan"
  | "over_cap"
  | "payday_shortfall"
  | "leftover_saved"
  | "consolidation_loan";

/**
 * GET /notifications: newest first, at most the 100 newest; title and body are the
 * Thai text already written by backend/app/notifications/copy.py. There is no read
 * state: `count` is every alert the user has.
 */
export type NotificationOut = {
  id: string;
  kind: NotificationKind;
  title: string;
  body: string;
  installment_id: string | null; // null for payday alerts
  created_at: string; // ISO datetime
};
export type NotificationsOut = { notifications: NotificationOut[]; count: number };

// ---- Assistant plan (GET /assistant/plan, merged backend) -------------------------

/**
 * Copied from backend/app/assistant/schemas.py (PlanOut, read only, 2026-10-27).
 * Every number comes from code, never from AI (L69, L70). Money is a string;
 * months are "YYYY-MM". 409 SETTINGS_REQUIRED without settings.
 */
export type PlanMonth = {
  month: string;
  total: Money;
  budget: Money;
  over_budget: boolean;
  headroom: Money; // max(0, budget - total)
};

export type BufferPlanOut = {
  shortfall: Money; // total - budget, added over the months over budget
  remaining_gap: Money; // the shortfall less what was already moved for each month
  balance: Money; // the buffer (L66)
  covered: boolean; // balance >= remaining_gap
  still_short: Money; // max(0, remaining_gap - balance)
};

/** Why consolidation is or is not offered (L70), checked in this order. */
export type ConsolidationReason =
  | "NOT_NEEDED"
  | "OVERDUE_DEBT"
  | "DISPUTED_DEBT"
  | "ESTIMATE_TOO_LARGE"
  | "PAYMENT_ABOVE_BUDGET"
  | "PAYMENT_ABOVE_ONE_THIRD_OF_INCOME" // the loan would make a month L65 RED
  | "ELIGIBLE";

/** One loan replacing every counted installment. The rate and term are EXAMPLE values. */
export type EstimateOut = {
  principal: Money;
  annual_rate: string; // e.g. "0.18": an example yearly rate, not a real one
  rate_is_example: true;
  rate_note: "example, not a real rate";
  term_months: number;
  first_due_month: string;
  monthly_payment: Money; // level payment, rounded up to 0.01
  total_cost: Money; // monthly_payment x term_months
  current_remaining_total: Money; // what is left on the current plans
  extra_cost: Money; // total_cost - current_remaining_total
  // This month's total (the hero's), the offer's "ตอนนี้". Null when the answer did not
  // carry it (src/apiFields.ts): the "ตอนนี้" column then shows its total only (UI-39).
  current_monthly_total: Money | null;
  // max(0, current_monthly_total - monthly_payment). Null when the answer did not carry
  // it (src/apiFields.ts): the offer shows without its benefit line (UI-39).
  monthly_reduction: Money | null;
};

export type ConsolidationOut = {
  eligible: boolean;
  reason: ConsolidationReason;
  estimate: EstimateOut | null; // only when eligible
};

export type AssistantPlanOut = {
  months: PlanMonth[]; // this month to the last month due, at most 600
  months_truncated: boolean;
  back_in_budget_month: string | null; // null if every month already is
  pause_until: string | null; // back_in_budget_month when this month is over budget
  safe_new_monthly: Money; // for a new safe_new_months-month installment from safe_new_from
  safe_new_from: string;
  safe_new_months: number; // 12
  buffer_plan: BufferPlanOut;
  consolidation: ConsolidationOut;
};

/**
 * The assistant's summary. Not built in the backend (AI is roadmap only): an example
 * worded from the real plan's numbers, labelled ตัวอย่าง (src/api.ts).
 */
export type AssistantSummaryOut = { text: string; is_example: boolean };
