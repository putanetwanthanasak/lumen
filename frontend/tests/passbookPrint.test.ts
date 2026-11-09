/**
 * Session 23: the passbook page prints the newest movement on a band.
 * UI-70 (break test, money): the line is the API's first movement (GET /bank/main-account
 *   lists them newest first, MA-02), with the date, a short label per kind, and the
 *   amount with + or − (U+2212) from the API's `direction`, never from the kind and never
 *   computed. No running balance, no other amount. No movement: "ยังไม่มีรายการ" on the
 *   same band.
 * UI-71 (break test): the date is "DD ม.ค. YY" with the Buddhist year, the Bangkok date
 *   whatever the instant's offset and the machine's time zone.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { MainAccountOut, Movement } from "../src/api-types.ts";
import { HOST } from "../src/accent.ts";
import { ACCOUNT } from "../src/copy.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { AccountBody, Passbook, PrintedLine } from "../src/screens/Account.tsx";
import { printDate } from "../src/thaiMonth.ts";

const plain = (html: string) => html.replace(/<[^>]+>/g, "");
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");

function movement(fields: Partial<Movement>): Movement {
  return {
    id: crypto.randomUUID(),
    at: "2026-11-04T09:00:00+07:00",
    kind: "withdrawal",
    direction: "in",
    amount: "1500.00",
    for_month: "2026-11",
    ...fields,
  };
}

/** The band's text, or "" when the card has none. */
function band(latest: Movement | null): string {
  const html = renderToStaticMarkup(createElement(PrintedLine, { latest }));
  assert.match(html, new RegExp(`^<p class="[^"]*${HOST.band.replace(/[/.]/g, "\\$&")}">`));
  return plain(html);
}

beforeEach(() => resetMock(new Date(2026, 9, 27), PERSONA_SETTINGS));

// ---- UI-70: the printed line ---------------------------------------------------------

test("UI_70_the_line_is_the_apis_first_movement", () => {
  const newest = movement({ amount: "1500.00", at: "2026-11-04T09:00:00+07:00" });
  const older = [movement({ kind: "auto_save", direction: "out", amount: "300.00", at: "2026-11-03T09:00:00+07:00" }), movement({ kind: "auto_save", direction: "out", amount: "200.00", at: "2026-11-02T09:00:00+07:00" })];
  const account: MainAccountOut = { balance: "6500.00", movements: [newest, ...older], movements_truncated: false };
  const html = renderToStaticMarkup(createElement(Passbook, { balance: account.balance, latest: account.movements[0] ?? null }));
  assert.ok(plain(html).includes("04 พ.ย. 69 ย้ายจากกันชน+1,500.00"), plain(html));
  // The screen hands the card the first movement of the answer, as the API ordered it.
  const screen = plain(
    renderToStaticMarkup(
      createElement(AccountBody, {
        account,
        buffer: { balance: "4200.00", monthly_total: "5000.00", months_covered: 1 },
        month: null,
        shortfalls: null,
        loadedAt: new Date("2026-11-04T07:05:00Z"),
      }),
    ),
  );
  assert.ok(screen.includes("ยังไม่มีรายการ") === false, "the band is not empty");
  assert.ok(screen.includes("6,500.00") && !screen.includes("5,000.00"), screen);
  const printed = /บาท(.*?)ข้อมูลจำลองสำหรับเดโม/.exec(screen)?.[1];
  assert.equal(printed, "04 พ.ย. 69 ย้ายจากกันชน+1,500.00");
});

test("UI_70_each_kind_has_its_short_label", () => {
  assert.equal(band(movement({ kind: "auto_save", direction: "out", amount: "300.00" })), "04 พ.ย. 69 กันเงินเข้ากันชน−300.00");
  assert.equal(band(movement({ kind: "leftover_save", direction: "out", amount: "250.50" })), "04 พ.ย. 69 เก็บงบเข้ากันชน−250.50");
  assert.equal(band(movement({ kind: "withdrawal", direction: "in", amount: "1500.00" })), "04 พ.ย. 69 ย้ายจากกันชน+1,500.00");
  assert.deepEqual(ACCOUNT.printed, { auto_save: "กันเงินเข้ากันชน", leftover_save: "เก็บงบเข้ากันชน", withdrawal: "ย้ายจากกันชน" });
});

test("UI_70_the_sign_is_the_apis_direction_never_the_kind", () => {
  // The API could answer any direction for a kind: the line follows `direction`.
  assert.ok(band(movement({ kind: "withdrawal", direction: "out", amount: "10.00" })).endsWith("−10.00"));
  assert.ok(band(movement({ kind: "auto_save", direction: "in", amount: "10.00" })).endsWith("+10.00"));
  // − is U+2212, as รายการล่าสุด shows it, never a hyphen.
  const out = band(movement({ direction: "out", amount: "40.00" }));
  assert.ok(out.includes("−") && !out.includes("-"), out);
});

test("UI_70_one_amount_the_apis_and_no_running_balance", () => {
  const text = band(movement({ amount: "12345.67" }));
  assert.equal(text, "04 พ.ย. 69 ย้ายจากกันชน+12,345.67");
  assert.equal(text.match(/[0-9][0-9,]*\.[0-9]{2}/g)?.length, 1);
});

test("UI_70_no_movement_prints_the_empty_line_on_the_same_band", () => {
  assert.equal(band(null), ACCOUNT.empty);
  assert.equal(ACCOUNT.empty, "ยังไม่มีรายการ");
  // The mock's ม่อน has no movement yet.
  const account = call("GET", "/bank/main-account").body as MainAccountOut;
  assert.deepEqual(account.movements, []);
});

test("UI_70_after_a_move_the_mock_prints_it", () => {
  assert.equal(call("POST", "/demo/scene", { scene: "over_budget" }).status, 200); // auto-saves
  assert.equal(call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "1500.00", for_month: "2026-11" }).status, 201);
  const account = call("GET", "/bank/main-account").body as MainAccountOut;
  const text = band(account.movements[0] ?? null);
  assert.ok(text.endsWith("ย้ายจากกันชน+1,500.00"), text);
});

// ---- UI-71: the printed date ----------------------------------------------------------

test("UI_71_the_date_is_two_digit_day_thai_month_and_two_digit_buddhist_year", () => {
  assert.equal(printDate("2026-11-04T09:00:00+07:00"), "04 พ.ย. 69");
  assert.equal(printDate("2027-01-31T23:59:00+07:00"), "31 ม.ค. 70");
  assert.equal(printDate("2057-12-01T08:00:00+07:00"), "01 ธ.ค. 00"); // 2600 BE
  assert.throws(() => printDate("4 Nov"));
});

test("UI_71_the_date_is_the_bangkok_date_across_utc_midnight", () => {
  // 01:00 in Bangkok is still the day before in UTC.
  assert.equal(printDate("2026-11-04T01:00:00+07:00"), "04 พ.ย. 69");
  assert.equal(printDate("2026-11-03T18:00:00Z"), "04 พ.ย. 69");
  assert.equal(printDate("2026-11-03T16:59:00Z"), "03 พ.ย. 69");
});

test("UI_71_the_date_is_the_bangkok_date_whatever_the_machines_time_zone", () => {
  // As UI-67: a machine at +07 would pass the test above without the zone.
  const module = new URL("../src/thaiMonth.js", import.meta.url).href;
  const at = "2026-11-04T01:00:00+07:00";
  const script = `import { printDate } from ${JSON.stringify(module)}; console.log(printDate(${JSON.stringify(at)}) + "|" + new Date(${JSON.stringify(at)}).getDate());`;
  for (const zone of ["UTC", "America/New_York"]) {
    const out = execFileSync(process.execPath, ["--input-type=module", "-e", script], { env: { ...process.env, TZ: zone }, encoding: "utf8" });
    const [date, localDay] = out.trim().split("|");
    assert.ok(localDay !== "4", `the child really runs at ${zone}`);
    assert.equal(date, "04 พ.ย. 69", zone);
  }
});
