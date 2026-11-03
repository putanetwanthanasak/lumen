/**
 * Session 21: บัญชีหลัก (#/account), the host bank app's home with KidNee as its focus.
 * UI-57 (critical, money): the recent movements: the label per kind, the month, the
 *   sign from the API's `direction` (never computed), the API's order, at most 5,
 *   the empty state, and the Thai date.
 * UI-58: the KidNee card: this month's total and its status (icon and text), the
 *   buffer, and the link to KidNee's Home.
 * UI-59: the four shortcuts do nothing but show their note.
 * UI-60: the route and the ways between the host app and KidNee.
 * UI-61: nothing names a bank, product or company, or shows a real-looking number.
 * UI-63: the screen's loading and error states inside the host shell.
 * UI-62, the mock's movements, is in mainAccount.mock.test.ts.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { BufferOut, MainAccountOut, MonthRow, MonthsOut, Movement } from "../src/api-types.ts";
import { ACCOUNT, BUFFER, BUFFER_STATE, HOME, MONTHS_VIEW } from "../src/copy.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { STATUS_CHIP } from "../src/monthStatus.ts";
import { ROUTES } from "../src/router.ts";
import { AccountBody, AccountContent, KidNeeCard, movementLabel, Movements, Shortcuts, signed } from "../src/screens/Account.tsx";
import { HomeScreen } from "../src/screens/Home.tsx";
import { thaiDate } from "../src/thaiMonth.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
const plain = (html: string) => html.replace(/<[^>]+>/g, "");
const SRC = "src";
const read = (...path: string[]) => readFileSync(join(SRC, ...path), "utf8");

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

function movement(fields: Partial<Movement>): Movement {
  return {
    id: crypto.randomUUID(),
    at: "2026-11-03T09:00:00+07:00",
    kind: "auto_save",
    direction: "out",
    amount: "40.00",
    for_month: null,
    ...fields,
  };
}

function data() {
  return {
    account: call("GET", "/bank/main-account").body as MainAccountOut,
    buffer: call("GET", "/buffer").body as BufferOut,
    month: (call("GET", "/debts/months?count=1").body as MonthsOut).months[0] ?? null,
  };
}

const listItems = (html: string) => [...html.matchAll(/<li[^>]*>(.*?)<\/li>/g)].map((m) => plain(m[1] ?? ""));

// ---- UI-57 (critical): the movements ------------------------------------------------

test("UI_57_each_kind_has_its_label_and_a_month_only_when_the_api_names_one", () => {
  assert.equal(movementLabel({ kind: "auto_save", for_month: null }), "กันเงินเข้ากันชน KidNee");
  assert.equal(movementLabel({ kind: "leftover_save", for_month: "2026-10" }), "เก็บงบที่ใช้ไม่หมดเข้ากันชน สำหรับ ต.ค. 2569");
  assert.equal(movementLabel({ kind: "withdrawal", for_month: "2026-11" }), "ย้ายเงินจากกันชน KidNee สำหรับ พ.ย. 2569");
  assert.equal(movementLabel({ kind: "withdrawal", for_month: null }), "ย้ายเงินจากกันชน KidNee");
});

test("UI_57_the_sign_is_the_apis_direction_never_the_kind_and_the_amount_is_never_parsed", () => {
  assert.equal(signed({ direction: "in", amount: "1500.00" }), "+1,500.00");
  assert.equal(signed({ direction: "out", amount: "40.00" }), "−40.00");
  // The same kind with the other direction flips the sign: it comes from `direction` only.
  const html = renderToStaticMarkup(
    createElement(Movements, {
      movements: [movement({ kind: "withdrawal", direction: "out", amount: "1.00" }), movement({ kind: "auto_save", direction: "in", amount: "2.00" })],
    }),
  );
  const rows = listItems(html);
  assert.ok(rows[0]?.endsWith("−1.00"), rows[0]);
  assert.ok(rows[1]?.endsWith("+2.00"), rows[1]);
  // No hyphen-minus sign: U+2212 reads as minus.
  assert.ok(!plain(html).includes("-1.00"));
});

test("UI_57_keeps_the_apis_order_and_shows_at_most_five", () => {
  const seven = Array.from({ length: 7 }, (_, i) => movement({ amount: `${i + 1}.00` })); // ui-06-allow: test data
  const rows = listItems(renderToStaticMarkup(createElement(Movements, { movements: seven })));
  assert.equal(rows.length, 5);
  assert.deepEqual(
    rows.map((r) => r.slice(-4)),
    ["1.00", "2.00", "3.00", "4.00", "5.00"],
  );
});

test("UI_57_no_movements_says_so", () => {
  const text = plain(renderToStaticMarkup(createElement(Movements, { movements: [] })));
  assert.ok(text.includes(ACCOUNT.recent));
  assert.ok(text.includes("ยังไม่มีรายการ"));
});

test("UI_57_the_date_is_the_bangkok_date_in_thai", () => {
  assert.equal(thaiDate("2026-11-03T09:00:00+07:00"), "3 พ.ย. 2569");
  assert.equal(thaiDate("2026-11-01T00:30:00+07:00"), "1 พ.ย. 2569");
  assert.equal(thaiDate("2027-01-31T23:59:00+07:00"), "31 ม.ค. 2570");
  assert.throws(() => thaiDate("3 Nov"));
});

test("UI_57_after_a_move_the_screen_lists_it_first_with_its_month", () => {
  scene("over_budget"); // records the YELLOW laptop, which auto-saves
  call("POST", "/buffer/move-to-main", { client_request_id: "m1", amount: "1500.00", for_month: "2026-11" });
  const rows = listItems(renderToStaticMarkup(createElement(AccountBody, data())));
  const recent = rows.filter((r) => r.includes("กันชน"));
  assert.ok(recent[0]?.startsWith("ย้ายเงินจากกันชน KidNee สำหรับ พ.ย. 2569"), recent[0]);
  assert.ok(recent[0]?.endsWith("+1,500.00"), recent[0]);
  assert.ok(recent[1]?.startsWith("กันเงินเข้ากันชน KidNee"), recent[1]);
  assert.ok(recent[1]?.includes("−"), recent[1]);
});

// ---- UI-58: the KidNee card -------------------------------------------------------

const BUFFER_OUT: BufferOut = { balance: "5700.00", monthly_total: "5000.00", months_covered: 1 };
const chip = STATUS_CHIP;
// The icons' paths, as Icon.tsx draws them (check, alert and stop).
const PATHS = {
  check: "M20 6 9 17l-5-5",
  alert: "M12 3 2 20h20L12 3Zm0 6v5m0 3.5v.5",
  stop: "M8 3h8l5 5v8l-5 5H8l-5-5V8l5-5Zm4 5v5m0 3.5v.5",
} as const;
const row = (flags: Pick<MonthRow, "over_budget" | "over_one_third">): MonthRow => ({ month: "2026-11", total: "5000.00", ...flags });

test("UI_58_the_card_shows_this_months_total_its_status_and_the_buffer_and_opens_home", () => {
  for (const [flags, icon, label, tone] of [
    [{ over_budget: false, over_one_third: false }, "check", MONTHS_VIEW.ok, "ok"],
    [{ over_budget: true, over_one_third: false }, "alert", MONTHS_VIEW.over, "over"],
    [{ over_budget: true, over_one_third: true }, "stop", MONTHS_VIEW.risk, "risk"],
  ] as const) {
    const html = renderToStaticMarkup(createElement(KidNeeCard, { buffer: BUFFER_OUT, month: row(flags) }));
    const text = plain(html);
    assert.match(html, /^<a href="#\/home"/);
    assert.ok(text.includes("ภาระผ่อนเดือนนี้ 5,000.00 บาท"), text);
    assert.ok(text.includes(label), label);
    assert.ok(text.includes("กันชน 5,700.00 บาท"), text);
    assert.ok(text.includes("KidNee") && text.includes("คิดหนี้"));
    // Never colour only: the chip is its icon and its words, in its status colours.
    const escaped = label.replace(/[.()]/g, "\\$&");
    assert.match(html, new RegExp(`<span class="[^"]*rounded-pill[^"]*${chip[tone]}"><svg[^>]*><path d="${PATHS[icon]}"></path></svg>${escaped}</span>`));
    assert.ok(html.includes('aria-label="KidNee"'), "the logo");
  }
});

test("UI_58_the_mock_persona_in_budget_and_this_month_over_one_third", () => {
  const inBudget = plain(renderToStaticMarkup(createElement(AccountBody, data())));
  assert.ok(inBudget.includes(MONTHS_VIEW.ok), inBudget);
  assert.ok(inBudget.includes("ภาระผ่อนเดือนนี้ 3,500.00 บาท"), inBudget);
  scene("over_budget_now"); // a RED item due this month
  const over = plain(renderToStaticMarkup(createElement(AccountBody, data())));
  assert.ok(over.includes(MONTHS_VIEW.risk), over);
});

test("UI_58_before_kidnee_is_set_up_the_card_invites_to_start", () => {
  const text = plain(renderToStaticMarkup(createElement(KidNeeCard, { buffer: BUFFER_OUT, month: null })));
  assert.ok(text.includes(ACCOUNT.setUp));
  assert.ok(!text.includes("ภาระผ่อนเดือนนี้"));
});

test("UI_58_the_balance_is_the_apis_string_formatted", () => {
  const text = plain(renderToStaticMarkup(createElement(AccountBody, data())));
  assert.ok(text.includes("9,500.00บาท"), text); // PERSONA_MAIN_BALANCE, then "บาท" in its own span
  assert.ok(text.includes(ACCOUNT.savings) && text.includes(ACCOUNT.available) && text.includes(ACCOUNT.mockData));
});

// ---- UI-59: the shortcuts are examples only -------------------------------------------

test("UI_59_four_labelled_buttons_that_only_show_their_note", () => {
  const closed = renderToStaticMarkup(createElement(Shortcuts, {}));
  const buttons = [...closed.matchAll(/<button([^>]*)>/g)].map((m) => m[1] ?? "");
  assert.equal(buttons.length, 4);
  for (const b of buttons) {
    assert.match(b, /type="button"/);
    assert.ok(!b.includes("href"));
  }
  assert.deepEqual(listItems(closed), ["โอนเงิน", "จ่ายบิล", "เติมเงิน", "สแกน"]);
  assert.ok(!plain(closed).includes(ACCOUNT.shortcutNote));
  const open = plain(renderToStaticMarkup(createElement(Shortcuts, { note: true })));
  assert.ok(open.includes("ปุ่มตัวอย่าง ใช้ไม่ได้ในเดโม"));
});

test("UI_59_the_shortcut_handler_sets_the_note_and_nothing_else", () => {
  const source = read("screens", "Account.tsx");
  const shortcuts = source.slice(source.indexOf("export function Shortcuts"), source.indexOf("export function KidNeeCard"));
  assert.deepEqual([...shortcuts.matchAll(/onClick=\{([^}]*)\}/g)].map((m) => m[1]), ["() => setShown(true)"]);
  assert.ok(!/navigate|href|fetch|get[A-Z]|move/.test(shortcuts.replace(/aria-label=\{ACCOUNT\.shortcutsLabel\}/, "")));
});

// ---- UI-60: the route and the ways back and forth --------------------------------------

test("UI_60_account_is_a_route_and_the_default_landing_is_unchanged", () => {
  assert.ok((ROUTES as readonly string[]).includes("account"));
  // With no route the app still decides between settings and Home only.
  assert.match(read("App.tsx"), /navigate\(settings === null \? "settings" : "home"\)/);
  assert.match(read("App.tsx"), /account: AccountScreen/);
});

test("UI_60_the_host_bar_has_two_items_with_this_screen_selected", () => {
  const html = renderToStaticMarkup(createElement(AccountContent, { load: { state: "ready", data: data() }, onRetry: () => undefined }));
  const nav = /<nav[^>]*>(.*?)<\/nav>/.exec(html)?.[1] ?? "";
  const links = [...nav.matchAll(/<a href="([^"]+)"([^>]*)>/g)].map((m) => [m[1], (m[2] ?? "").includes('aria-current="page"')]);
  assert.deepEqual(links, [
    ["#/account", true],
    ["#/home", false],
  ]);
  assert.deepEqual(listItems(nav), ["หน้าแรก", "KidNee"]);
  // Selected is never colour only: bold and underlined too.
  assert.match(nav, /aria-current="page"[^>]*>.*?border-b-2 border-white font-bold/);
});

test("UI_60_kidnee_home_has_a_way_back_to_the_main_account", () => {
  const html = renderToStaticMarkup(createElement(HomeScreen));
  assert.match(html, /<a href="#\/account"[^>]*>.*?บัญชีหลัก<\/a>/);
  assert.equal(HOME.toAccount, "บัญชีหลัก");
  assert.ok(html.includes('aria-label="KidNee"'), "the KidNee logo stays on Home");
});

test("UI_60_both_buffer_success_messages_link_to_the_main_account", () => {
  const source = read("screens", "Buffer.tsx");
  // Each ok Alert after a move holds <SeeInAccount />, which opens #/account.
  const okAlerts = [...source.matchAll(/<Alert tone="ok"[\s\S]*?<\/Alert>/g)].map((m) => m[0]);
  assert.equal(okAlerts.length, 2);
  for (const alert of okAlerts) assert.ok(alert.includes("<SeeInAccount />"), alert);
  assert.match(source, /function SeeInAccount\(\)[\s\S]*?href="#\/account"[\s\S]*?BUFFER\.seeInAccount/);
  assert.equal(BUFFER.seeInAccount, "ดูในบัญชีหลัก");
  assert.ok(BUFFER_STATE.success("a", "b").length > 0);
});

// ---- UI-61: no brand, no real-looking number ------------------------------------------

const BRANDS = /KBank|KBTG|Kasikorn|กสิกร|K PLUS|K\+|\bMAKE\b|Shopee|ธนาคาร/i;
const NEW_FILES = [
  ["screens", "Account.tsx"],
  ["components", "HostScreen.tsx"],
];

test("UI_61_the_host_shell_names_no_bank_product_or_company", () => {
  for (const path of NEW_FILES) assert.ok(!BRANDS.test(read(...path)), path.join("/"));
  const strings = JSON.stringify(ACCOUNT);
  assert.ok(!BRANDS.test(strings), strings);
  const text = plain(renderToStaticMarkup(createElement(AccountContent, { load: { state: "ready", data: data() }, onRetry: () => undefined })));
  assert.ok(!BRANDS.test(text), text);
  assert.ok(!text.includes("—"), "no em dash");
});

test("UI_61_only_the_masked_placeholder_number_and_no_images", () => {
  const html = renderToStaticMarkup(createElement(AccountContent, { load: { state: "ready", data: data() }, onRetry: () => undefined }));
  const text = plain(html);
  assert.ok(text.includes("xxx-x-x1234-x"));
  // No run of 6 or more digits, the shape of a real account number (amounts have commas).
  assert.deepEqual(text.match(/[0-9]{6,}/g), null);
  assert.ok(!/<img\b/.test(html));
  assert.ok(text.includes("Concept prototype สำหรับการแข่งขัน"), "the footer");
  assert.match(html, /<h1[^>]*>บัญชีหลัก<\/h1>/);
});

// ---- UI-63: the screen's states ---------------------------------------------------------

test("UI_63_loading_and_error_stay_inside_the_host_shell", () => {
  const loading = renderToStaticMarkup(createElement(AccountContent, { load: { state: "loading" }, onRetry: () => undefined }));
  assert.match(loading, /role="status"/);
  assert.match(loading, /<h1[^>]*>บัญชีหลัก<\/h1>/);
  assert.ok(plain(loading).includes("Concept prototype สำหรับการแข่งขัน"));
  const error = plain(renderToStaticMarkup(createElement(AccountContent, { load: { state: "error", error: new Error("offline") }, onRetry: () => undefined })));
  assert.ok(error.includes("โหลดข้อมูลไม่สำเร็จ") && error.includes("ลองอีกครั้ง"), error);
});
