/**
 * The verdict as shown (UI-05), the mock's L63/L64/L65 answers (UI-08, critical:
 * the demo must not show a wrong verdict) and Thai month names (UI-09).
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import type { ManualEntryIn, RecordedOut, SettingsOut, VerdictOut } from "../src/api-types.ts";
import { VERDICT } from "../src/copy.ts";
import { PERSONA_SETTINGS, SCENARIOS, type MockInstallment } from "../src/mock/persona.ts";
import { assess, handle, resetMock, savingFor } from "../src/mock/server.ts";
import { addMonths, thaiMonth } from "../src/thaiMonth.ts";

// The demo runs "today" = 27 Oct 2026, so the candidate starts in Nov 2026.
const TODAY = new Date(2026, 9, 27);
const USER = "demo-mon";

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

function entry(overrides: Partial<ManualEntryIn> = {}): ManualEntryIn {
  return {
    client_request_id: "req-1",
    kind: "purchase",
    item_price: "12000.00",
    months: 10,
    monthly_amount: "1200.00",
    first_due_month: "2026-11",
    item_name: "",
    platform_name: null,
    ...overrides,
  };
}

// ---- UI-05 -------------------------------------------------------------------

test("UI_05_each_verdict_has_an_icon_and_the_exact_thai_label", () => {
  assert.deepEqual(
    Object.fromEntries(Object.entries(VERDICT).map(([k, v]) => [k, [v.icon, v.label]])),
    {
      GREEN: ["check", "อยู่ในงบ"],
      YELLOW: ["alert", "บางเดือนเกินงบ"],
      RED: ["stop", "เกินเกณฑ์ที่ ธปท. แนะนำ (1 ใน 3 ของรายได้)"],
    },
  );
  for (const v of Object.values(VERDICT)) assert.ok(v.detail.length > 0);
  // L64: guidance, never a regulation.
  assert.match(VERDICT.RED.detail, /ธปท\. แนะนำ/);
  assert.doesNotMatch(VERDICT.RED.detail, /กำหนด/);
});

// ---- UI-08: the persona's three scenes ------------------------------------------

for (const [scene, expected] of [
  ["GREEN", "GREEN"],
  ["YELLOW", "YELLOW"],
  ["RED", "RED"],
] as const) {
  test(`UI_08_persona_${scene}_example_gives_${expected}`, () => {
    const s = SCENARIOS[scene];
    const res = handle("POST", "/installments/preview", entry(s), USER);
    assert.equal(res.status, 200);
    assert.equal((res.body as VerdictOut).verdict, expected);
  });
}

test("UI_08_paid_off_persona_line_is_listed_but_not_counted", () => {
  const summary = handle("GET", "/debts/summary", undefined, USER).body as {
    monthly_total: string;
    installments: { status: string; owed: boolean }[];
  };
  assert.equal(summary.monthly_total, "3500.00");
  assert.deepEqual(
    summary.installments.map((l) => [l.status, l.owed]),
    [["active", true], ["active", true], ["paid_off", false]],
  );
});

test("UI_08_green_example_month_totals_match_the_story", () => {
  const out = handle("POST", "/installments/preview", entry(), USER).body as VerdictOut;
  assert.equal(out.monthly_total, "3500.00");
  assert.deepEqual(
    out.months.map((m) => m.total),
    ["4700.00", "4700.00", "2700.00", "2700.00", "2700.00", "2700.00", "2700.00", "2700.00", "1200.00", "1200.00"],
  );
});

// ---- UI-08: L65 boundaries ---------------------------------------------------------

const PROFILE = { income: "15000.00", monthly_installment_budget: "4000.00" } as const;
const NONE: MockInstallment[] = [];
const candidate = (monthly: string) => ({ first_due_month: "2026-11", months: 1, monthly_amount: monthly });

test("UI_08_exactly_the_budget_is_green_one_satang_more_is_yellow", () => {
  assert.equal(assess(PROFILE, NONE, candidate("4000.00"), true).verdict, "GREEN");
  assert.equal(assess(PROFILE, NONE, candidate("4000.01"), true).verdict, "YELLOW");
});

test("UI_08_exactly_one_third_is_not_red_one_satang_more_is_red", () => {
  const high = { income: "15000.00", monthly_installment_budget: "9000.00" };
  assert.equal(assess(high, NONE, candidate("5000.00"), true).verdict, "GREEN");
  assert.equal(assess(high, NONE, candidate("5000.01"), true).verdict, "RED");
  // Income not divisible by 3: compared as total * 3 > income, no division.
  const odd = { income: "10000.00", monthly_installment_budget: "9000.00" };
  assert.equal(assess(odd, NONE, candidate("3333.33"), true).verdict, "GREEN");
  assert.equal(assess(odd, NONE, candidate("3333.34"), true).verdict, "RED");
});

test("UI_08_only_months_where_an_installment_is_due_are_counted", () => {
  const ends: MockInstallment = {
    id: "x",
    vendor: "manual",
    contract_id: "m-x",
    kind: "purchase",
    item_name: "",
    principal: "2000.00",
    monthly_amount: "2000.00",
    months: 1,
    paid_amount: "0.00",
    remaining: "2000.00",
    first_due_month: "2026-11",
    platform_name: null,
  };
  const out = assess(PROFILE, [ends], { ...candidate("2500.00"), months: 2 }, true);
  assert.deepEqual(out.months.map((m) => [m.month, m.total, m.over_budget]), [
    ["2026-11", "4500.00", true],
    ["2026-12", "2500.00", false],
  ]);
  assert.deepEqual(out.over_budget_months, ["2026-11"]);
  // Paid off: not counted (L43 owed set).
  const paid = { ...ends, paid_amount: "2000.00", remaining: "0.00" };
  assert.equal(assess(PROFILE, [paid], candidate("2500.00"), true).months[0]?.total, "2500.00");
});

// ---- UI-08: L63 saving and L64 warning ---------------------------------------------

const SETTINGS: SettingsOut = {
  ...PERSONA_SETTINGS,
  consent_at: "2026-10-27T00:00:00Z",
  warnings: [],
};

test("UI_08_percent_saving_rounds_down_to_the_satang", () => {
  const rule = { ...SETTINGS, saving_rule: { mode: "percent" as const, percent: 10 } };
  assert.equal(savingFor(rule, entry({ item_price: "12000.00" }), "9500.00"), "1200.00");
  assert.equal(savingFor(rule, entry({ item_price: "999.99" }), "9500.00"), "99.99");
  assert.equal(savingFor(rule, entry({ item_price: "0.09" }), "9500.00"), "0.00"); // 0.009 -> 0.00, skipped
  const seven = { ...SETTINGS, saving_rule: { mode: "percent" as const, percent: 7 } };
  assert.equal(savingFor(seven, entry({ item_price: "1234.56" }), "9500.00"), "86.41"); // 86.4192
});

test("UI_08_safety_net_skips_the_whole_saving_below_500_and_allows_exactly_500", () => {
  assert.equal(savingFor(SETTINGS, entry(), "1700.00"), "1200.00"); // leaves exactly 500.00
  assert.equal(savingFor(SETTINGS, entry(), "1699.99"), "0.00"); // would leave 499.99: none
});

test("UI_08_cash_and_auto_save_off_never_save", () => {
  assert.equal(savingFor(SETTINGS, entry({ kind: "cash_withdrawal" }), "9500.00"), "0.00");
  assert.equal(savingFor(SETTINGS, entry({ kind: "cash_loan" }), "9500.00"), "0.00");
  assert.equal(savingFor({ ...SETTINGS, auto_save_enabled: false }, entry(), "9500.00"), "0.00");
});

test("UI_08_budget_warning_from_one_satang_above_one_third", () => {
  resetMock(TODAY);
  const at = handle("POST", "/settings", { ...PERSONA_SETTINGS, income: "15000.00", monthly_installment_budget: "5000.00" }, USER);
  assert.equal(at.status, 201);
  assert.deepEqual((at.body as SettingsOut).warnings, []);
  const above = handle("PUT", "/settings", { ...PERSONA_SETTINGS, income: "15000.00", monthly_installment_budget: "5000.01" }, USER);
  assert.equal(above.status, 200);
  assert.deepEqual((above.body as SettingsOut).warnings, ["BUDGET_ABOVE_ONE_THIRD_OF_INCOME"]);
});

test("UI_08_record_is_idempotent_on_client_request_id", () => {
  const first = handle("POST", "/installments", entry(), USER);
  const again = handle("POST", "/installments", entry(), USER);
  assert.equal(first.status, 201);
  assert.equal(again.status, 200);
  const a = first.body as RecordedOut;
  const b = again.body as RecordedOut;
  assert.equal(b.status, "duplicate");
  assert.equal(b.installment_id, a.installment_id);
  assert.equal(a.saved_amount, "1200.00");
  assert.equal(b.saved_amount, "1200.00");
  assert.equal(a.monthly_total, "4700.00");
  assert.equal(b.monthly_total, "4700.00"); // recorded once
  const buffer = handle("GET", "/buffer", undefined, USER).body as { balance: string };
  assert.equal(buffer.balance, "6000.00"); // 4,800.00 + 1,200.00, once
  const other = handle("POST", "/installments", entry({ months: 12 }), USER);
  assert.equal(other.status, 409);
});

test("UI_08_preview_writes_nothing_and_settings_are_required", () => {
  const count = () => (handle("GET", "/debts/summary", undefined, USER).body as { installments: unknown[] }).installments.length;
  const before = count();
  handle("POST", "/installments/preview", entry(), USER);
  assert.equal(count(), before);
  resetMock(TODAY);
  const res = handle("POST", "/installments/preview", entry(), USER);
  assert.equal(res.status, 409);
  assert.deepEqual(res.body, {
    detail: { code: "SETTINGS_REQUIRED", message: "set income and budget with POST /settings first" },
  });
});

// ---- UI-09 -----------------------------------------------------------------------

test("UI_09_thai_month_uses_the_buddhist_era_and_rolls_over_the_year", () => {
  assert.equal(thaiMonth("2026-11"), "พ.ย. 2569");
  assert.equal(thaiMonth("2026-12"), "ธ.ค. 2569");
  assert.equal(addMonths("2026-12", 1), "2027-01");
  assert.equal(thaiMonth(addMonths("2026-12", 1)), "ม.ค. 2570");
  assert.equal(addMonths("2027-01", -1), "2026-12");
  assert.equal(addMonths("2026-10", -3), "2026-07");
  assert.throws(() => thaiMonth("2026-13"));
});
