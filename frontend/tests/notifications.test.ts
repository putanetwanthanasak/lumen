/**
 * The header bell (PR B). (UI-23, the payoff steps per app, went with screen 7.)
 * UI-24: the persona's alerts use the manual entry copy (never "Not me"). The API
 * keeps no read state (docs/api/kidnee-endpoints.md): `count` is every alert, and the
 * bell has no unread badge.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, test } from "node:test";
import type { NotificationsOut } from "../src/api-types.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { KIND_STYLE } from "../src/screens/Notifications.tsx";

const TODAY = new Date(2026, 9, 27);
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const alerts = () => call("GET", "/notifications").body as NotificationsOut;

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

// ---- UI-24 -------------------------------------------------------------------------

test("UI_24_persona_alert_is_the_manual_entry_copy", () => {
  const out = alerts();
  assert.equal(out.count, 1);
  assert.deepEqual(
    out.notifications.map((n) => [n.kind, n.title, n.body, n.installment_id !== null]),
    [
      [
        "new_debt",
        "บันทึกรายการผ่อนแล้ว",
        "ตู้เย็น ราคา 15,000 บาท ผ่อน 10 เดือน เดือนละ 1,500 บาท ยอดผ่อนรวมต่อเดือนตอนนี้ 3,500 บาท",
        true,
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

test("UI_24_count_is_every_alert_and_nothing_marks_them_read", () => {
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
  call("POST", "/demo/payday", { month: "2026-11" });
  const out = alerts();
  // Newest first; a payday alert names no installment.
  assert.equal(out.count, 3);
  assert.deepEqual(
    out.notifications.map((n) => [n.kind, n.installment_id === null]),
    [
      ["leftover_saved", true],
      ["new_debt", false],
      ["new_debt", false],
    ],
  );
  // There is no mark-read endpoint, and opening the list changes nothing.
  assert.equal(call("POST", "/notifications/read").status, 404);
  assert.equal(alerts().count, 3);
  // The bell and the list never read a read state the API does not send.
  for (const file of ["src/components/Screen.tsx", "src/screens/Notifications.tsx", "src/api.ts"]) {
    assert.doesNotMatch(readFileSync(file, "utf8"), /unread|\.read\b|notifications\/read/, file);
  }
});

test("UI_24_a_consolidation_loan_alert_has_the_bank_icon", () => {
  // Review round 2 F4: the bank's loan is told apart from a purchase.
  assert.deepEqual(KIND_STYLE.consolidation_loan, { icon: "bank", badge: "bg-info-bg text-info-ink" });
  assert.ok(KIND_STYLE.consolidation_loan.icon !== KIND_STYLE.new_debt.icon);
});
