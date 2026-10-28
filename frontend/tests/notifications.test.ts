/**
 * The header bell (PR B). (UI-23, the payoff steps per app, went with screen 7.)
 * UI-24: the persona's alerts use the manual entry copy (never "Not me"), and the
 * unread count comes from the API and drops to 0 once the list is opened.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, test } from "node:test";
import type { NotificationsOut } from "../src/api-types.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";

const TODAY = new Date(2026, 9, 27);
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mint");
const alerts = () => call("GET", "/notifications").body as NotificationsOut;

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

// ---- UI-24 -------------------------------------------------------------------------

test("UI_24_persona_alert_is_the_manual_entry_copy_and_unread", () => {
  const out = alerts();
  assert.equal(out.unread_count, 1);
  assert.deepEqual(
    out.notifications.map((n) => [n.kind, n.title, n.body, n.read]),
    [
      [
        "new_debt",
        "บันทึกรายการผ่อนแล้ว",
        "ตู้เย็น ราคา 15,000 บาท ผ่อน 10 เดือน เดือนละ 1,500 บาท ยอดผ่อนรวมต่อเดือนตอนนี้ 3,500 บาท",
        false,
      ],
    ],
  );
});

test("UI_24_no_alert_and_no_source_offers_not_me", () => {
  // Record one of each kind, then a payday: no alert body offers "Not me" (L68).
  for (const kind of ["purchase", "cash_withdrawal", "cash_loan"]) {
    const entry = {
      client_request_id: `k-${kind}`,
      kind,
      item_price: "1000.00",
      months: 2,
      monthly_amount: "500.00",
      first_due_month: "2026-11",
      item_name: "",
      platform_name: null,
    };
    assert.equal(call("POST", "/installments", entry).status, 201);
  }
  call("POST", "/demo/payday", { month: "2026-11" });
  for (const n of alerts().notifications) assert.doesNotMatch(n.body, /ถ้าไม่ใช่คุณ/);
  // Nor does any frontend source (the webhook alert stays in the backend only).
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? walk(path) : [path];
    });
  const hits = walk(join(process.cwd(), "src")).filter((f) => readFileSync(f, "utf8").includes("ถ้าไม่ใช่คุณ"));
  assert.deepEqual(hits, []);
});

test("UI_24_opening_the_list_marks_every_alert_read", () => {
  const entry = {
    client_request_id: "r1",
    kind: "purchase",
    item_price: "1000.00",
    months: 2,
    monthly_amount: "500.00",
    first_due_month: "2026-11",
    item_name: "",
    platform_name: null,
  };
  call("POST", "/installments", entry);
  assert.equal(alerts().unread_count, 2);
  const read = call("POST", "/notifications/read").body as NotificationsOut;
  assert.equal(read.unread_count, 0);
  assert.ok(read.notifications.every((n) => n.read));
  assert.equal(alerts().unread_count, 0);
  // A new alert after that is unread again; the old ones stay read.
  call("POST", "/installments", { ...entry, client_request_id: "r2" });
  const after = alerts();
  assert.equal(after.unread_count, 1);
  assert.deepEqual(
    after.notifications.map((n) => n.read),
    [false, true, true],
  );
});
