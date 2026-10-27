/** How Home labels an installment by its status (UI-12, review F4). */
import assert from "node:assert/strict";
import { test } from "node:test";
import type { InstallmentLine } from "../src/api-types.ts";
import { lineStatus } from "../src/installmentStatus.ts";

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
