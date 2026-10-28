/** Which client_request_id a buffer move sends (screen 4): UI-13. Review B1 F3, F4. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { BUFFER } from "../src/copy.ts";
import { afterMoveError, moveRequest } from "../src/bufferMove.ts";
import { walletFor } from "../src/homeLayout.ts";

test("UI_13_after_a_move_the_months_covered_wait_for_the_new_balance", () => {
  // Review round 1 F4: 4,800.00 against 3,500.00 a month is 1 month. After moving it
  // all, the balance shows 0.00 at once; the 1 month belongs to the old balance, so the
  // meter and its caption wait for GET /buffer instead of showing it.
  const before = { balance: "4800.00", monthly_total: "3500.00", months_covered: 1 };
  assert.equal(walletFor(before, "4800.00")?.filled, 1);
  assert.equal(walletFor(before, "0.00"), null);
  const after = { balance: "0.00", monthly_total: "3500.00", months_covered: 0 };
  assert.deepEqual([walletFor(after, "0.00")?.filled, walletFor(after, "0.00")?.caption], [0, "ยังไม่พอ 1 เดือน"]);
  // The screen reads the buffer again after a move and draws the months from it.
  const screen = readFileSync("src/screens/Buffer.tsx", "utf8");
  const success = screen.slice(screen.indexOf("const out = await moveToMain("), screen.indexOf("} catch (e) {"));
  assert.ok(success.includes("getBuffer().then(setCurrent"), "refresh after a move");
  assert.ok(screen.includes("walletFor(current, balance)"), "months only for the balance shown");
  assert.ok(!screen.includes("walletView(buffer)"), "never the months of the first load");
});

test("UI_13_a_retry_of_the_same_amount_after_a_failure_reuses_the_id", () => {
  const first = moveRequest(null, "800.00", "id-1");
  assert.deepEqual(first, { amount: "800.00", id: "id-1" });
  // The answer was lost: the request is kept, and the same amount repeats the move.
  const kept = afterMoveError(first, null);
  assert.deepEqual(moveRequest(kept, "800.00", "id-2"), { amount: "800.00", id: "id-1" });
});

test("UI_13_the_same_amount_typed_differently_is_the_same_move", () => {
  // Review B2 F3: "1500" then "1500.00" is one amount, so one id.
  const kept = afterMoveError(moveRequest(null, "1500", "id-1"), null);
  assert.equal(moveRequest(kept, "1500.00", "id-2").id, "id-1");
  assert.equal(moveRequest(kept, "1500.0", "id-3").id, "id-1");
  assert.equal(moveRequest(kept, "1500.01", "id-4").id, "id-4");
});

test("UI_13_a_new_amount_or_a_422_gets_a_new_id", () => {
  const first = moveRequest(null, "800.00", "id-1");
  assert.deepEqual(moveRequest(first, "900.00", "id-2"), { amount: "900.00", id: "id-2" });
  // 422: nothing moved, so the next try is a new request even for the same amount.
  assert.equal(afterMoveError(first, "AMOUNT_ABOVE_BALANCE"), null);
  assert.deepEqual(moveRequest(null, "800.00", "id-3"), { amount: "800.00", id: "id-3" });
});

test("UI_13_a_failed_move_never_claims_where_the_money_is", () => {
  // B1 F4: after an unknown outcome the money may already have left the buffer.
  assert.doesNotMatch(BUFFER.failed, /ยังอยู่/);
  assert.match(BUFFER.failed, /จำนวนเดิม/);
});
