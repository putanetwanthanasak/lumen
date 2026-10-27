/** The คิดก่อน form and its stages (screen 3): UI-16. Review round 2, F2, F3 and F5. */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import type { RecordedOut, VerdictOut } from "../src/api-types.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import {
  answerPreview,
  edit,
  emptyForm,
  entryToRecord,
  startPreview,
  toEntry,
  type Form,
  type Stage,
} from "../src/thinkFirstForm.ts";

const TODAY = new Date(2026, 9, 27);
const FORM: Form = { ...emptyForm(TODAY), price: "12000", months: "10", monthly: "1200" };
const VERDICT: VerdictOut = { verdict: "GREEN", months: [], over_budget_months: [], monthly_total: "3500.00" };

function built(form: Form, id: string) {
  const result = toEntry(form, id);
  assert.ok(result.ok);
  return result.entry;
}

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

test("UI_16_first_due_month_defaults_to_next_month", () => {
  assert.equal(emptyForm(TODAY).firstDue, "2026-11");
  assert.equal(emptyForm(new Date(2026, 11, 31)).firstDue, "2027-01");
});

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
