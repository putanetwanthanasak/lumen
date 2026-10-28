/**
 * How Home labels an installment by its status (UI-12, review F4), and where it is in
 * its plan, from GET /debts/months (UI-43).
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { InstallmentLine, MonthDetail } from "../src/api-types.ts";
import { lineStatus, scheduleText } from "../src/installmentStatus.ts";

const ACTIVE: InstallmentLine = {
  id: "a",
  vendor: "shopdemo",
  contract_id: "SD-1",
  kind: "purchase",
  item_name: "หูฟัง",
  principal: "12000.00",
  monthly_amount: "2000.00",
  months: 6,
  paid_amount: "8000.00",
  late_fees_accrued: "0.00",
  remaining: "4000.00",
  status: "active",
  disputed_at: null,
  owed: true,
  platform_name: null,
  first_due_date: "2026-07-01",
  last_due_date: "2026-12-01",
};

test("UI_12_active_owed_line_has_no_label_and_counts", () => {
  assert.deepEqual(lineStatus(ACTIVE), { label: null, counted: true });
});

test("UI_12_paid_off_and_cancelled_lines_are_labelled_and_not_counted", () => {
  assert.deepEqual(lineStatus({ ...ACTIVE, status: "paid_off", remaining: "0.00", owed: false }), {
    label: "ผ่อนครบแล้ว",
    counted: false,
  });
  assert.deepEqual(lineStatus({ ...ACTIVE, status: "cancelled", owed: false }), {
    label: "ยกเลิกแล้ว",
    counted: false,
  });
});

test("UI_12_cancelled_after_not_me_keeps_the_dispute_history", () => {
  // L59(3): "cancelled after you reported it".
  const line = { ...ACTIVE, status: "cancelled" as const, owed: false, disputed_at: "2026-10-20T10:00:00Z" };
  assert.deepEqual(lineStatus(line), { label: "ยกเลิกแล้ว หลังจากคุณแจ้งว่าไม่ใช่รายการของคุณ", counted: false });
});

test("UI_12_disputed_line_says_so_and_counts_while_owed", () => {
  // L43: disputed with something left to pay is still in the monthly total.
  assert.deepEqual(lineStatus({ ...ACTIVE, status: "disputed", disputed_at: "2026-10-20T10:00:00Z" }), {
    label: "คุณแจ้งว่าไม่ใช่รายการของคุณ",
    counted: true,
  });
});

// ---- UI-43: "งวดที่ x จาก y · หมด {month}", looked up in the API's rows -----------------

/** A month row listing installments as [id, its number that month, its months, its last month?]. */
function due(month: string, items: [string, number, number, boolean][]): MonthDetail {
  return {
    month,
    total: "0.00", // not read
    over_budget: false,
    over_one_third: false,
    budget: "5000.00", // not read
    over_by: "0.00", // not read
    installments: items.map(([installment_id, installment_no, installments_total, is_last]) => ({
      installment_id,
      item_name: "",
      platform_name: null,
      monthly_amount: "1.00",
      installment_no,
      installments_total,
      is_last,
      last_month: "2027-01", // not read
    })),
  };
}

test("UI_43_the_number_comes_from_this_months_row_and_the_end_from_the_row_marked_last", () => {
  const rows = [
    due("2026-10", [["a", 4, 6, false], ["b", 2, 10, false]]),
    due("2026-11", [["a", 5, 6, false], ["b", 3, 10, false]]),
    due("2026-12", [["a", 6, 6, true], ["b", 4, 10, false]]),
  ];
  assert.equal(scheduleText("a", rows), "งวดที่ 4 จาก 6 · หมด ธ.ค. 2569");
  // The rows end before its last month: no end month, never a guessed one.
  assert.equal(scheduleText("b", rows), "งวดที่ 2 จาก 10");
  // Numbers as the API sends them, never counted here: an odd one shows as sent.
  assert.equal(scheduleText("c", [due("2026-10", [["c", 7, 9, true]])]), "งวดที่ 7 จาก 9 · หมด ต.ค. 2569");
});

test("UI_43_one_that_starts_later_says_when_and_one_not_in_the_rows_gets_null", () => {
  const rows = [due("2026-10", [["a", 4, 6, false]]), due("2026-11", [["later", 1, 2, false]]), due("2026-12", [["later", 2, 2, true]])];
  assert.equal(scheduleText("later", rows), "เริ่ม พ.ย. 2569 · หมด ธ.ค. 2569");
  assert.equal(scheduleText("later", rows.slice(0, 2)), "เริ่ม พ.ย. 2569");
  assert.equal(scheduleText("gone", rows), null); // Home then keeps "ผ่อน {months} เดือน"
  assert.equal(scheduleText("a", []), null);
});
