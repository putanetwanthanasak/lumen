/** The next step a notification offers (screen 5): UI-17. Review B1 F6. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { alertAction } from "../src/alertAction.ts";

test("UI_17_a_shortfall_points_to_the_buffer_while_it_holds_money", () => {
  assert.equal(alertAction("payday_shortfall", "7800.00")?.route, "buffer");
  assert.equal(alertAction("payday_shortfall", "0.01")?.route, "buffer");
  assert.equal(alertAction("payday_shortfall", "0.00")?.route, "months");
});

test("UI_17_other_kinds", () => {
  assert.equal(alertAction("leftover_saved", "0.00")?.route, "buffer");
  // No "Not me" action in this demo (L62); see the open question in the log.
  assert.equal(alertAction("new_debt", "100.00"), null);
  assert.equal(alertAction("cash_loan", "100.00"), null);
});
