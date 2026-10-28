/** Which client_request_id a buffer move sends (screen 4): UI-13. Review B1 F3, F4. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { BUFFER } from "../src/copy.ts";
import { afterMoveError, moveRequest } from "../src/bufferMove.ts";

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
