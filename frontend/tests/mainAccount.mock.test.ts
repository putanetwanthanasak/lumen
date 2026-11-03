/**
 * UI-62: the mock's GET /bank/main-account (Session 21). The mock records a movement
 * exactly where it moves money between the main account and the buffer: an
 * auto-save, the payday leftover and a move to main. Critical (money), so it has a
 * break test in the progress log. The screen's tests are in mainAccount.test.ts.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import type { MainAccountOut, ManualEntryIn, RecordedOut } from "../src/api-types.ts";
import { PERSONA_MAIN_BALANCE, PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026, as in buffer-payday.test.ts
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const account = () => call("GET", "/bank/main-account").body as MainAccountOut;
const brief = (a: MainAccountOut) => a.movements.map((m) => [m.kind, m.direction, m.amount, m.for_month]);

function entry(id: string, price = "3000.00", kind: ManualEntryIn["kind"] = "purchase"): ManualEntryIn {
  return {
    client_request_id: id,
    kind,
    item_price: price,
    months: 10,
    monthly_amount: "100.00",
    first_due_month: "2027-02",
    item_name: "หูฟัง",
    platform_name: null,
  };
}

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

test("UI_62_a_fresh_store_has_the_persona_balance_and_no_movements", () => {
  assert.deepEqual(account(), { balance: PERSONA_MAIN_BALANCE, movements: [], movements_truncated: false });
  assert.equal(call("GET", "/bank/main-account").status, 200);
  assert.equal(handle("GET", "/bank/main-account", undefined, null).status, 401);
});

test("UI_62_auto_save_payday_leftover_and_move_to_main_each_add_one_movement_newest_first", () => {
  const saved = call("POST", "/installments", entry("e1")).body as RecordedOut;
  assert.equal(saved.saved_amount, "300.00"); // 10% of 3,000.00
  assert.equal(call("POST", "/demo/payday", { month: "2027-01" }).status, 201); // leftover 3,500.00
  call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "1500.00", for_month: "2026-11" });
  call("POST", "/buffer/move-to-main", { client_request_id: "m2", amount: "200.00" });

  const out = account();
  assert.deepEqual(brief(out), [
    ["withdrawal", "in", "200.00", null],
    ["withdrawal", "in", "1500.00", "2026-11"],
    ["leftover_save", "out", "3500.00", "2027-01"],
    ["auto_save", "out", "300.00", null],
  ]);
  // 9,500.00 - 300.00 - 3,500.00 + 1,500.00 + 200.00
  assert.equal(out.balance, "7400.00");
  const at = out.movements.map((m) => m.at);
  assert.deepEqual(at, [...at].sort().reverse());
  assert.ok(at.every((a) => /^2026-10-27T[0-9]{2}:[0-9]{2}:00\+07:00$/.test(a)), at.join());
});

test("UI_62_nothing_is_recorded_when_no_money_moves", () => {
  call("POST", "/installments", entry("cash", "3000.00", "cash_withdrawal")); // cash never saves
  call("POST", "/installments/preview", entry("p1")); // a preview records nothing
  call("POST", "/buffer/move-to-main", { client_request_id: "big", amount: "99999.00" }); // 422
  call("POST", "/installments", entry("e1"));
  call("POST", "/installments", entry("e1")); // a repeat saves once
  call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "100.00" });
  call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "100.00" }); // a repeat moves once
  call("POST", "/demo/payday", { month: "2027-01" });
  call("POST", "/demo/payday", { month: "2027-01" }); // once per month
  const kinds = account().movements.map((m) => m.kind);
  assert.deepEqual(kinds, ["leftover_save", "withdrawal", "auto_save"]);
});

test("UI_62_lists_the_20_newest_and_says_there_are_more", () => {
  for (let i = 0; i < 25; i += 1) {
    call("POST", "/buffer/move-to-main", { client_request_id: `m${i}`, amount: "1.00" });
  }
  const out = account();
  assert.equal(out.movements.length, 20);
  assert.equal(out.movements_truncated, true);
  resetMock(TODAY, PERSONA_SETTINGS);
  for (let i = 0; i < 20; i += 1) {
    call("POST", "/buffer/move-to-main", { client_request_id: `m${i}`, amount: "1.00" });
  }
  assert.equal(account().movements_truncated, false);
});
