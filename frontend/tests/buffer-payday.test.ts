/**
 * PR B mock endpoints: the buffer move (UI-13, L66), payday (UI-14, L67), the
 * payoff plan and the consolidation estimate (UI-15, mock only). Critical: money
 * and idempotency, so each has a break test in the progress log.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import type {
  BufferOut,
  ConsolidationOut,
  DebtSummary,
  MovedOut,
  NotificationsOut,
  PaydayOut,
  PayoffPlanOut,
} from "../src/api-types.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { payoffPlan } from "../src/mock/payoff.ts";
import { handle, resetMock } from "../src/mock/server.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026: the persona owes 3,500.00 a month
const USER = "demo-mint";
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, USER);
const buffer = () => (call("GET", "/buffer").body as BufferOut).balance;

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

// ---- UI-13: move to main (L66) ---------------------------------------------------

test("UI_13_move_to_main_moves_once_per_client_request_id", () => {
  const first = call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "800.00" });
  const again = call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "800.00" });
  assert.equal(first.status, 201);
  assert.equal(again.status, 200);
  assert.equal((again.body as MovedOut).status, "duplicate");
  assert.equal((again.body as MovedOut).transaction_id, (first.body as MovedOut).transaction_id);
  assert.equal(buffer(), "4000.00"); // 4,800.00 - 800.00, once
});

test("UI_13_same_id_with_another_amount_is_409_and_moves_nothing", () => {
  call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "800.00" });
  const other = call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "900.00" });
  assert.equal(other.status, 409);
  assert.equal(buffer(), "4000.00");
});

test("UI_13_the_whole_balance_can_move_and_one_satang_more_is_422", () => {
  const above = call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "4800.01" });
  assert.equal(above.status, 422);
  assert.deepEqual(above.body, {
    detail: { code: "AMOUNT_ABOVE_BALANCE", message: "the buffer holds less than this amount" },
  });
  assert.equal(buffer(), "4800.00");
  const all = call("POST", "/buffer/move-to-main", { client_request_id: "m2", amount: "4800.00" });
  assert.equal(all.status, 201);
  assert.equal((all.body as MovedOut).balance, "0.00");
  // A repeat of a move that emptied the buffer is still the same move (B52 in Session 13).
  assert.equal(call("POST", "/buffer/move-to-main", { client_request_id: "m2", amount: "4800.00" }).status, 200);
});

// ---- UI-14: payday (L67) ------------------------------------------------------------

function payday(month: string) {
  return call("POST", "/demo/payday", { month });
}

test("UI_14_under_budget_saves_the_leftover_once_per_month", () => {
  const first = payday("2027-01"); // only the 1,500.00 plan: leftover 3,500.00
  assert.equal(first.status, 201);
  assert.deepEqual(
    (({ outcome, month_total, amount, buffer_balance }) => ({ outcome, month_total, amount, buffer_balance }))(
      first.body as PaydayOut,
    ),
    { outcome: "leftover_saved", month_total: "1500.00", amount: "3500.00", buffer_balance: "8300.00" },
  );
  const again = payday("2027-01");
  assert.equal(again.status, 200);
  assert.equal((again.body as PaydayOut).status, "duplicate");
  assert.equal(buffer(), "8300.00"); // saved once
});

test("UI_14_over_budget_alerts_with_the_shortfall_and_the_buffer", () => {
  call("POST", "/demo/scene", { scene: "over_budget" }); // records the YELLOW laptop
  const out = payday("2026-11").body as PaydayOut;
  assert.equal(out.outcome, "over_budget");
  assert.equal(out.month_total, "6500.00");
  assert.equal(out.amount, "1500.00");
  const latest = (call("GET", "/notifications").body as NotificationsOut).notifications[0];
  assert.equal(latest?.kind, "payday_shortfall");
  assert.equal(
    latest?.body,
    "เดือน พ.ย. 2569 ค่างวดรวม 6,500 บาท เกินงบ 1,500 บาท คุณมีกันชน 7,800 บาท ย้ายมาช่วยจ่ายได้",
  );
});

test("UI_14_an_empty_buffer_points_to_the_payoff_assistant", () => {
  call("POST", "/demo/scene", { scene: "over_budget" });
  call("POST", "/buffer/move-to-main", { client_request_id: "all", amount: buffer() });
  payday("2026-11");
  const latest = (call("GET", "/notifications").body as NotificationsOut).notifications[0];
  assert.equal(
    latest?.body,
    "เดือน พ.ย. 2569 ค่างวดรวม 6,500 บาท เกินงบ 1,500 บาท ลองเปิดผู้ช่วยปลดหนี้เพื่อดูแผนได้",
  );
});

test("UI_14_exactly_the_budget_is_no_leftover", () => {
  const settings = { ...PERSONA_SETTINGS, monthly_installment_budget: "1500.00" };
  resetMock(TODAY, settings);
  assert.equal((payday("2027-01").body as PaydayOut).outcome, "no_leftover");
});

test("UI_14_safety_net_allows_a_leftover_that_leaves_exactly_500", () => {
  // Main 9,500.00: a leftover of 9,000.00 leaves exactly 500.00, which L67 allows.
  const settings = { ...PERSONA_SETTINGS, income: "40000.00", monthly_installment_budget: "10500.00" };
  resetMock(TODAY, settings);
  const out = payday("2027-01").body as PaydayOut;
  assert.equal(out.outcome, "leftover_saved");
  assert.equal(out.amount, "9000.00");
});

test("UI_14_safety_net_skips_the_leftover_below_500", () => {
  // Main 9,500.00: a leftover of 9,000.01 would leave 499.99.
  const settings = { ...PERSONA_SETTINGS, income: "40000.00", monthly_installment_budget: "10500.01" };
  resetMock(TODAY, settings);
  const out = payday("2027-01").body as PaydayOut;
  assert.equal(out.outcome, "safety_net");
  assert.equal(out.amount, "0.00");
  assert.equal(buffer(), "4800.00");
});

test("UI_14_leftover_off_saves_nothing", () => {
  resetMock(TODAY, { ...PERSONA_SETTINGS, leftover_saving_enabled: false });
  assert.equal((payday("2027-01").body as PaydayOut).outcome, "leftover_off");
  assert.equal(buffer(), "4800.00");
});

// ---- UI-15: payoff plan and consolidation (mock only) --------------------------------

test("UI_15_payoff_plan_after_an_over_budget_purchase", () => {
  call("POST", "/demo/scene", { scene: "over_budget" });
  const plan = call("GET", "/payoff/plan").body as PayoffPlanOut;
  assert.equal(plan.over_budget_now, false); // October itself is 3,500.00
  assert.equal(plan.back_in_budget_month, "2027-01");
  assert.equal(plan.pause_until, "2027-01");
  assert.equal(plan.pause_beyond_horizon, false);
  // From Jan 2027 the busiest month is 4,500.00, so 500.00 a month still fits.
  assert.deepEqual(plan.headroom, { amount: "500.00", from_month: "2027-01" });
  assert.deepEqual(plan.buffer_plan.shortfalls, [
    { month: "2026-11", amount: "1500.00" },
    { month: "2026-12", amount: "1500.00" },
  ]);
  assert.equal(plan.buffer_plan.total_shortfall, "3000.00");
  assert.equal(plan.buffer_plan.covered, true); // 7,800.00 in the buffer
  assert.equal(plan.consolidation_eligible, true);
});

test("UI_15_over_budget_through_the_horizon_still_advises_a_pause", () => {
  // Review B1 F2: no month back in budget within 12 months must not read as "no need to pause".
  const big = {
    client_request_id: "big",
    kind: "purchase",
    item_price: "132000.00",
    months: 24,
    monthly_amount: "5500.00",
    first_due_month: "2026-11",
    item_name: "",
  };
  assert.equal(call("POST", "/installments", big).status, 201);
  const plan = call("GET", "/payoff/plan").body as PayoffPlanOut;
  assert.equal(plan.back_in_budget_month, null);
  assert.equal(plan.pause_beyond_horizon, true);
  assert.equal(plan.headroom, null);
});

test("UI_15_the_explanation_names_the_largest_shortfall", () => {
  // Review B2 F5: the tightest month is the one over by the most, not the first.
  const row = (month: string, total: string, over: boolean) => ({
    month,
    total,
    over_budget: over,
    over_one_third: false,
  });
  const rows = [row("2026-11", "5100.00", true), row("2026-12", "6500.00", true), row("2027-01", "4000.00", false)];
  const plan = payoffPlan(rows, "5000.00", "0.00", 2);
  assert.match(plan.explanation, /เดือนที่แน่นที่สุดเกินงบ 1,500\.00 บาท/);
});

test("UI_14_a_cash_entry_gets_the_strong_cash_alert", () => {
  // Review B2 F4, L50: the backend's manual_entry_alert uses the kind's own title and alert kind.
  for (const [kind, title] of [
    ["cash_loan", "บันทึกการกู้เงินสดแล้ว"],
    ["cash_withdrawal", "บันทึกการเบิกเงินสดแล้ว"],
    ["purchase", "บันทึกรายการผ่อนแล้ว"],
  ] as const) {
    const entry = {
      client_request_id: `c-${kind}`,
      kind,
      item_price: "10000.00",
      months: 10,
      monthly_amount: "1100.00",
      first_due_month: "2026-11",
      item_name: "",
    };
    assert.equal(call("POST", "/installments", entry).status, 201);
    const latest = (call("GET", "/notifications").body as NotificationsOut).notifications[0];
    assert.equal(latest?.kind, kind === "purchase" ? "new_debt" : kind);
    assert.equal(latest?.title, title);
  }
});

test("UI_15_no_consolidation_offer_when_every_month_fits", () => {
  const plan = call("GET", "/payoff/plan").body as PayoffPlanOut;
  assert.equal(plan.pause_until, null);
  assert.equal(plan.pause_beyond_horizon, false);
  assert.equal(plan.consolidation_eligible, false);
  assert.deepEqual(plan.headroom, { amount: "1500.00", from_month: "2026-10" });
});

test("UI_15_consolidation_shows_monthly_and_total_cost_that_agree", () => {
  const lines = (call("GET", "/debts/summary").body as DebtSummary).installments.filter((l) => l.owed);
  const res = call("POST", "/consolidation/estimate", {
    payoffs: lines.map((l) => ({ installment_id: l.id, payoff_amount: l.remaining })),
    months: 24,
    consent: true,
  });
  assert.equal(res.status, 200);
  const out = res.body as ConsolidationOut;
  // 16,000.00 at an assumed 12% flat for 2 years owes 19,840.00; 19,840.00 / 24 is
  // 826.666..., rounded up to the satang. The total is what the 24 payments add up
  // to, and the interest is that total minus the principal, so the three agree.
  assert.equal(out.principal, "16000.00");
  assert.equal(out.new_monthly_payment, "826.67");
  assert.equal(out.total_cost, "19840.08");
  assert.equal(out.total_interest, "3840.08");
  assert.equal(out.monthly_now, "3500.00");
  assert.equal(out.remaining_now, "16000.00");
  assert.equal(out.is_example, true);
});

test("UI_15_consolidation_needs_consent", () => {
  const res = call("POST", "/consolidation/estimate", { payoffs: [], months: 24, consent: false });
  assert.equal(res.status, 422);
});
