/**
 * The ตรวจสอบก่อนผ่อน form and its stages (screen 3): UI-16 (review round 2, F2, F3,
 * F5), UI-18 (first due month, the 0% suggestion), UI-19 (the app), UI-21 (saving).
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import type { InstallmentLine, PreviewOut, RecordedOut, SuggestedMonthlyOut } from "../src/api-types.ts";
import { THINK } from "../src/copy.ts";
import { groupByPlatform } from "../src/installmentStatus.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { thaiMonth } from "../src/thaiMonth.ts";
import {
  answerPreview,
  applySuggestion,
  canPreview,
  edit,
  emptyForm,
  entryToRecord,
  firstDueChoices,
  startPreview,
  suggestionRequest,
  toEntry,
  type Form,
  type Stage,
} from "../src/thinkFirstForm.ts";

const TODAY = new Date(2026, 9, 27);
const FORM: Form = { ...emptyForm(), price: "12000", months: "10", monthly: "1200", firstDue: "2026-11" };
const VERDICT: PreviewOut = {
  verdict: "GREEN",
  months: [],
  over_budget_months: [],
  monthly_total: "3500.00",
  saving_if_recorded: "1200.00",
};

const LINE: InstallmentLine = {
  id: "x",
  vendor: "manual",
  contract_id: "manual-x",
  kind: "purchase",
  item_name: "",
  principal: "100.00",
  monthly_amount: "10.00",
  months: 10,
  paid_amount: "0.00",
  late_fees_accrued: "0.00",
  remaining: "100.00",
  status: "active",
  disputed_at: null,
  owed: true,
  platform_name: null,
};

function built(form: Form, id: string) {
  const result = toEntry(form, id);
  assert.ok(result.ok);
  return result.entry;
}

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

test("UI_16_an_answer_for_a_form_edited_while_checking_is_discarded", () => {
  // F2: the user changes months while the preview is in flight.
  const entry = built(FORM, "req-a");
  const checking = startPreview(entry);
  const edited = edit(checking);
  assert.deepEqual(edited, { name: "form" });
  assert.deepEqual(answerPreview(edited, "req-a", VERDICT), { name: "form" });
});

test("UI_16_an_answer_for_an_older_preview_is_discarded", () => {
  const newer = startPreview(built(FORM, "req-b"));
  assert.equal(answerPreview(newer, "req-a", VERDICT), newer);
  const shown = answerPreview(newer, "req-b", VERDICT);
  assert.equal(shown.name, "verdict");
});

test("UI_16_record_and_its_retry_reuse_the_preview_request_id", () => {
  // F3: a retry after a lost answer must send the same client_request_id.
  const entry = built(FORM, "req-a");
  const shown: Stage = answerPreview(startPreview(entry), "req-a", VERDICT);
  const first = entryToRecord(shown);
  const retry = entryToRecord(shown);
  assert.equal(first?.client_request_id, "req-a");
  assert.deepEqual(retry, first);
  assert.equal(entryToRecord({ name: "form" }), null);
  // And the API records it once.
  const a = handle("POST", "/installments", first, "demo-mint").body as RecordedOut;
  const b = handle("POST", "/installments", retry, "demo-mint").body as RecordedOut;
  assert.equal(b.status, "duplicate");
  assert.equal(b.installment_id, a.installment_id);
});

test("UI_16_kind_is_sent_and_a_cash_loan_saves_nothing", () => {
  // F5, L62: kind is an input; L63: cash never saves.
  assert.equal(built(FORM, "r").kind, "purchase");
  const loan = built({ ...FORM, kind: "cash_loan" }, "r-loan");
  assert.equal(loan.kind, "cash_loan");
  const out = handle("POST", "/installments", loan, "demo-mint").body as RecordedOut;
  assert.equal(out.saved_amount, "0.00");
  assert.equal(built({ ...FORM, kind: "cash_withdrawal" }, "r-w").kind, "cash_withdrawal");
});

// ---- UI-18: first due month and the 0% suggestion -------------------------------

test("UI_18_first_due_month_has_no_default_and_blocks_the_preview", () => {
  const empty = emptyForm();
  assert.equal(empty.firstDue, "");
  assert.equal(canPreview(empty), false);
  assert.equal(canPreview({ ...empty, firstDue: "2026-10" }), true);
  const result = toEntry({ ...FORM, firstDue: "" }, "r");
  assert.equal(result.ok, false);
  if (!result.ok) assert.ok(result.errors.firstDue !== undefined);
});

test("UI_18_the_two_first_due_choices_are_this_month_and_next_month", () => {
  assert.deepEqual(firstDueChoices(TODAY), { thisMonth: "2026-10", nextMonth: "2026-11" });
  assert.deepEqual(firstDueChoices(new Date(2026, 11, 31)), { thisMonth: "2026-12", nextMonth: "2027-01" });
  // Two equal buttons: the word on one line, the month on a second, smaller line.
  assert.equal(THINK.firstDueThis, "เดือนนี้");
  assert.equal(THINK.firstDueNext, "เดือนหน้า");
  assert.equal(thaiMonth("2026-10"), "ต.ค. 2569");
});

test("UI_18_suggestion_is_asked_only_when_price_and_months_are_ready", () => {
  assert.equal(suggestionRequest(emptyForm()), null);
  assert.equal(suggestionRequest({ ...emptyForm(), price: "12000" }), null);
  assert.deepEqual(suggestionRequest({ ...emptyForm(), price: "1,000", months: "3" }), { price: "1000", months: 3 });
  assert.equal(suggestionRequest({ ...emptyForm(), price: "1000", months: "3", monthlyEdited: true }), null);
});

test("UI_18_a_value_the_user_edited_is_never_overwritten", () => {
  const typed = { ...emptyForm(), price: "1000", months: "3" };
  const asked = { price: "1000", months: 3 };
  assert.equal(applySuggestion(typed, asked, "333.34").monthly, "333.34");
  const edited = { ...typed, monthly: "350", monthlyEdited: true };
  assert.equal(applySuggestion(edited, asked, "333.34").monthly, "350");
  // An answer for inputs that changed since is dropped.
  assert.equal(applySuggestion({ ...typed, months: "4" }, asked, "333.34").monthly, "");
});

test("UI_18_the_api_suggests_price_over_months_rounded_up_to_the_satang", () => {
  const ask = (price: string, months: number) =>
    handle("GET", `/installments/suggested-monthly?item_price=${price}&months=${months}`, undefined, "demo-mint");
  const monthly = (price: string, months: number) => (ask(price, months).body as SuggestedMonthlyOut).monthly_amount;
  assert.equal(monthly("12000", 10), "1200.00");
  assert.equal(monthly("1000", 3), "333.34"); // 333.333... rounded UP, never down
  assert.equal(monthly("1000.01", 1), "1000.01");
  assert.equal(monthly("0.01", 3), "0.01");
  assert.equal(monthly("100", 7), "14.29");
  assert.equal(ask("1000", 0).status, 422);
  assert.equal(ask("1.234", 3).status, 422);
});

// ---- UI-19: the app the user pays through ------------------------------------------

test("UI_19_platform_name_is_optional_trimmed_and_at_most_60_characters", () => {
  assert.equal(built(FORM, "r").platform_name, null);
  assert.equal(built({ ...FORM, platform: "  ShopDemo " }, "r").platform_name, "ShopDemo");
  assert.equal(built({ ...FORM, platform: "ก".repeat(60) }, "r").platform_name, "ก".repeat(60));
  const long = toEntry({ ...FORM, platform: "ก".repeat(61) }, "r");
  assert.equal(long.ok, false);
  if (!long.ok) assert.ok(long.errors.platform !== undefined);
  const res = handle("POST", "/installments/preview", { ...built(FORM, "r"), platform_name: "a\u0007b" }, "demo-mint");
  assert.equal(res.status, 422);
});

test("UI_19_home_groups_by_app_with_no_app_last", () => {
  const line = (id: string, platform_name: string | null) => ({ ...LINE, id, platform_name });
  const groups = groupByPlatform([line("a", null), line("b", "ShopDemo"), line("c", "แอป B"), line("d", " ShopDemo ")]);
  assert.deepEqual(
    groups.map((g) => [g.label, g.lines.map((l) => l.id)]),
    [
      ["ShopDemo", ["b", "d"]],
      ["แอป B", ["c"]],
      ["ไม่ระบุแอป", ["a"]],
    ],
  );
});

// ---- UI-21: the result screen's saving line ------------------------------------------

test("UI_21_preview_says_what_recording_would_save_and_recording_saves_that", () => {
  const entry = built(FORM, "r-save");
  const preview = handle("POST", "/installments/preview", entry, "demo-mint").body as PreviewOut;
  assert.equal(preview.saving_if_recorded, "1200.00");
  const recorded = handle("POST", "/installments", entry, "demo-mint").body as RecordedOut;
  assert.equal(recorded.saved_amount, preview.saving_if_recorded);
  const cash = handle("POST", "/installments/preview", { ...entry, kind: "cash_loan" }, "demo-mint").body as PreviewOut;
  assert.equal(cash.saving_if_recorded, "0.00");
  // The safety net (L63): main 8,300.00 left; 10% of 78,000.00 would leave 500.00
  // (allowed), 10% of 78,000.10 would leave 499.99 (skipped whole). The preview says
  // so, and recording then saves exactly that.
  const near = (price: string, id: string) => ({ ...entry, client_request_id: id, item_price: price, months: 12, monthly_amount: "6500.00" });
  const atNet = handle("POST", "/installments/preview", near("78000.00", "n1"), "demo-mint").body as PreviewOut;
  assert.equal(atNet.saving_if_recorded, "7800.00");
  const belowNet = handle("POST", "/installments/preview", near("78000.10", "n2"), "demo-mint").body as PreviewOut;
  assert.equal(belowNet.saving_if_recorded, "0.00");
  const skipped = handle("POST", "/installments", near("78000.10", "n2"), "demo-mint").body as RecordedOut;
  assert.equal(skipped.saved_amount, belowNet.saving_if_recorded);
});
