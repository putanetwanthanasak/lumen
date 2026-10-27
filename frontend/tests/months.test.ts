/** "ภาระผ่อนรายเดือน": the mock's GET /debts/months and the month status (UI-20). */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import type { MonthsOut } from "../src/api-types.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { monthStatus } from "../src/monthStatus.ts";

const TODAY = new Date(2026, 9, 27);
const months = (path = "/debts/months") => handle("GET", path, undefined, "demo-mint");

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

test("UI_20_months_run_from_this_month_to_the_last_month_due", () => {
  const out = months().body as MonthsOut;
  // หูฟัง ends Dec 2026, ตู้เย็น Jun 2027; the paid-off กระเป๋าเป้ is not counted.
  assert.deepEqual(
    out.months.map((m) => [m.month, m.total]),
    [
      ["2026-10", "3500.00"],
      ["2026-11", "3500.00"],
      ["2026-12", "3500.00"],
      ["2027-01", "1500.00"],
      ["2027-02", "1500.00"],
      ["2027-03", "1500.00"],
      ["2027-04", "1500.00"],
      ["2027-05", "1500.00"],
      ["2027-06", "1500.00"],
    ],
  );
  assert.equal((months("/debts/months?count=6").body as MonthsOut).months.length, 6);
});

test("UI_20_each_month_lists_its_installments_with_number_and_last", () => {
  const out = months().body as MonthsOut;
  const items = (month: string) =>
    out.months
      .find((m) => m.month === month)
      ?.installments.map((i) => [i.item_name, i.platform_name, i.monthly_amount, i.installment_no, i.installments_total, i.is_last]);
  assert.deepEqual(items("2026-10"), [
    ["หูฟังไร้สาย", "ShopDemo", "2000.00", 4, 6, false],
    ["ตู้เย็น", null, "1500.00", 2, 10, false],
  ]);
  assert.deepEqual(items("2026-12"), [
    ["หูฟังไร้สาย", "ShopDemo", "2000.00", 6, 6, true],
    ["ตู้เย็น", null, "1500.00", 4, 10, false],
  ]);
  assert.deepEqual(items("2027-06"), [["ตู้เย็น", null, "1500.00", 10, 10, true]]);
});

test("UI_20_a_recorded_plan_extends_the_months_and_sets_the_flags", () => {
  const entry = {
    client_request_id: "big",
    kind: "purchase",
    item_price: "48000.00",
    months: 12,
    monthly_amount: "4000.00",
    first_due_month: "2026-11",
    item_name: "มอเตอร์ไซค์",
    platform_name: null,
  };
  assert.equal(handle("POST", "/installments", entry, "demo-mint").status, 201);
  const out = months().body as MonthsOut;
  assert.equal(out.months.at(-1)?.month, "2027-10");
  const nov = out.months.find((m) => m.month === "2026-11");
  assert.equal(nov?.total, "7500.00");
  assert.equal(nov?.over_budget, true);
  assert.equal(nov?.over_one_third, true); // 7,500 x 3 > 20,000
});

test("UI_20_no_settings_is_409_and_a_bad_count_is_422", () => {
  assert.equal(months("/debts/months?count=0").status, 422);
  resetMock(TODAY);
  assert.equal(months().status, 409);
});

test("UI_20_month_status_is_icon_and_text_never_colour_only", () => {
  assert.deepEqual(monthStatus({ over_budget: false, over_one_third: false }), { tone: "ok", icon: "check", label: "อยู่ในงบ" });
  assert.deepEqual(monthStatus({ over_budget: true, over_one_third: false }), { tone: "over", icon: "alert", label: "เกินงบ" });
  // Over one third wins, even when the budget itself is above one third of income.
  assert.deepEqual(monthStatus({ over_budget: false, over_one_third: true }), {
    tone: "risk",
    icon: "stop",
    label: "เกินเกณฑ์ที่ ธปท. แนะนำ",
  });
});
