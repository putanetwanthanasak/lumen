/**
 * Session 22: บัญชีหลัก (#/account) reads as a bank app's home at first glance.
 * UI-64 (break test): every example control (the header's profile, bell and power, the
 *   tabs บัตร, สินเชื่อ and ลงทุน, "บัญชีของฉัน", seven shortcuts, three bar items) shows
 *   the note "ปุ่มตัวอย่าง ใช้ไม่ได้ในเดโม" and changes nothing else.
 * UI-65 (break test): KidNee opens from its shortcut, its card and the bar, and only
 *   those three lead to #/home.
 * UI-66 (break test): "ดูรายการล่าสุด ›" scrolls to รายการล่าสุด and focuses it.
 * UI-67 (break test): "ข้อมูล ณ เวลา HH:MM น." is the Bangkok time the data loaded.
 * UI-68: the account card is a passbook of our own: its words in order, a spine and
 *   horizontal rules only, no image, no diagonal, no red.
 */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { BufferOut, MainAccountOut, MonthsOut } from "../src/api-types.ts";
import { answerFromMock } from "../src/api.ts";
import { HOST } from "../src/accent.ts";
import { ACCOUNT } from "../src/copy.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { AccountBody, AccountContent, loadAccount, Movements, Passbook, RECENT_ID, showRecent, type AccountData } from "../src/screens/Account.tsx";
import { thaiTime } from "../src/thaiMonth.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string) => handle(method, path, undefined, "demo-mon");
const plain = (html: string) => html.replace(/<[^>]+>/g, "");
const read = (...path: string[]) => readFileSync(join("src", ...path), "utf8");
const LOADED = new Date("2026-11-04T07:05:00Z"); // 14:05 in Bangkok

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));
afterEach(() => answerFromMock(false));

function data(loadedAt = LOADED): AccountData {
  return {
    account: call("GET", "/bank/main-account").body as MainAccountOut,
    buffer: call("GET", "/buffer").body as BufferOut,
    month: (call("GET", "/debts/months?count=1").body as MonthsOut).months[0] ?? null,
    loadedAt,
  };
}

const screen = (note = false, d = data()) =>
  renderToStaticMarkup(createElement(AccountContent, { load: { state: "ready", data: d }, onRetry: () => undefined, note }));

/** Each <button>: its aria-label, or its text. */
const buttons = (html: string) =>
  [...html.matchAll(/<button([^>]*)>(.*?)<\/button>/g)].map((m) => /aria-label="([^"]+)"/.exec(m[1] ?? "")?.[1] ?? plain(m[2] ?? ""));

const EXAMPLES = [
  "โปรไฟล์",
  "การแจ้งเตือน",
  "ออกจากระบบ",
  "บัตร",
  "สินเชื่อ",
  "ลงทุน",
  "บัญชีของฉัน",
  "โอนเงิน",
  "จ่ายบิล",
  "เติมเงิน",
  "สแกนจ่าย",
  "ถอนไม่ใช้บัตร",
  "รายการเดินบัญชี",
  "ตั้งเป้าออม",
  "ธุรกรรม",
  "สแกน",
  "โปรไฟล์",
];

// ---- UI-64: example controls only show the note --------------------------------------

test("UI_64_the_screen_has_seventeen_example_buttons_and_one_real_one", () => {
  const html = screen();
  // Every button on the screen is an example, except "ดูรายการล่าสุด" (the Demo button
  // appears only once the API has answered, so not in a static render).
  assert.deepEqual(buttons(html).sort(), [...EXAMPLES, ACCOUNT.seeRecent].sort());
  for (const attrs of [...html.matchAll(/<button([^>]*)>/g)].map((m) => m[1] ?? "")) {
    assert.match(attrs, /type="button"/);
    assert.ok(!attrs.includes("href"), attrs);
  }
  // บัญชี is the selected tab, not a button.
  assert.match(html, /<span aria-current="page"[^>]*>บัญชี<\/span>/);
  // The header's icon-only buttons each have a label.
  assert.equal(EXAMPLES.length, 17);
});

test("UI_64_the_example_handler_shows_the_note_and_does_nothing_else", () => {
  const host = read("components", "HostScreen.tsx");
  const example = /export function ExampleButton[\s\S]*?\n}\n/.exec(host)?.[0] ?? "";
  assert.deepEqual([...example.matchAll(/onClick=\{([^}]*)\}/g)].map((m) => m[1]), ["() => show()"]);
  assert.match(host, /<ShowNote\.Provider value=\{\(\) => setShown\(true\)\}>/);
  assert.ok(!/navigate|href|location|fetch|get[A-Z]|move/.test(example), example);
  // Every example is an ExampleButton: the shell's one <button> is ExampleButton's own,
  // and the screen's one <button> is "ดูรายการล่าสุด".
  assert.equal([...host.matchAll(/<button\b/g)].length, 1);
  const account = read("screens", "Account.tsx");
  assert.deepEqual([...account.matchAll(/<button\b[\s\S]*?onClick=\{([^}]*)\}/g)].map((m) => m[1]), ["showRecent"]);
});

test("UI_64_with_the_note_shown_everything_else_is_the_same", () => {
  const closed = screen(false);
  const open = screen(true);
  assert.ok(!plain(closed).includes(ACCOUNT.shortcutNote));
  const strip = /<div role="status"[^>]*>(.*?)<\/div><nav/.exec(open)?.[1] ?? "";
  assert.equal(plain(strip), "ปุ่มตัวอย่าง ใช้ไม่ได้ในเดโม");
  // Take the strip away and the screen is unchanged: same balance, links and list.
  assert.equal(open.replace(strip, ""), closed);
  assert.ok(plain(open).includes("9,500.00"));
});

// ---- UI-65: the ways into KidNee ------------------------------------------------------

test("UI_65_kidnee_opens_from_its_shortcut_its_card_and_the_bar_only", () => {
  const html = screen();
  const links = [...html.matchAll(/<a href="#\/home"[^>]*>(.*?)<\/a>/g)].map((m) => plain(m[1] ?? ""));
  assert.equal(links.length, 3);
  const [shortcut, card, bar] = links;
  assert.equal(shortcut, "ใหม่KidNee"); // the 8th shortcut, with its "ใหม่" badge
  assert.ok(card?.startsWith("KidNeeคิดหนี้") && card.includes("กันชน"), card);
  assert.equal(bar, "KidNee");
  // In that order: the shortcuts, then บริการแนะนำ's card, then the bar.
  const at = (s: string) => html.indexOf(s);
  assert.ok(at(`aria-label="${ACCOUNT.shortcutsLabel}"`) < at(ACCOUNT.services));
  const recent = `>${ACCOUNT.recent}</h2>`; // the heading, not "ดูรายการล่าสุด" on the card
  assert.ok(at(ACCOUNT.services) < at(recent) && at(recent) < at("<nav"));
});

// ---- UI-66: "ดูรายการล่าสุด ›" -----------------------------------------------------------

test("UI_66_see_recent_scrolls_to_the_movements_and_focuses_them", () => {
  const list = renderToStaticMarkup(createElement(Movements, { movements: [] }));
  assert.match(list, new RegExp(`^<section id="${RECENT_ID}" tabindex="-1"`));
  assert.ok(plain(list).startsWith(ACCOUNT.recent));
  const calls: string[] = [];
  const target = {
    scrollIntoView: (o: ScrollIntoViewOptions) => calls.push(`scroll ${o.behavior} ${o.block}`),
    focus: (o: FocusOptions) => calls.push(`focus ${String(o.preventScroll)}`),
  };
  const g = globalThis as Record<string, unknown>;
  const reduce = { matches: false };
  g.document = { getElementById: (id: string) => (id === RECENT_ID ? target : null) };
  g.window = { matchMedia: () => reduce };
  try {
    showRecent();
    reduce.matches = true; // reduced motion: no smooth scroll
    showRecent();
  } finally {
    delete g.document;
    delete g.window;
  }
  assert.deepEqual(calls, ["scroll smooth start", "focus true", "scroll auto start", "focus true"]);
  // The link sits on the card and says what it does.
  const card = plain(renderToStaticMarkup(createElement(Passbook, { balance: "1.00" })));
  assert.ok(card.endsWith(ACCOUNT.seeRecent), card);
});

// ---- UI-67: the time the data loaded --------------------------------------------------

test("UI_67_the_time_is_bangkok_time_in_24_hours", () => {
  assert.equal(thaiTime(new Date("2026-11-04T07:05:00Z")), "14:05");
  assert.equal(thaiTime(new Date("2026-11-04T02:03:00Z")), "09:03");
  assert.equal(thaiTime(new Date("2026-11-04T16:59:00Z")), "23:59");
  assert.equal(thaiTime(new Date("2026-11-04T17:00:00Z")), "00:00");
  assert.equal(thaiTime(new Date("2026-11-04T00:00:00+07:00")), "00:00");
});

test("UI_67_the_time_is_bangkok_time_whatever_the_machines_time_zone", () => {
  // B-UI-257 found that the test above passes without the Bangkok zone on a machine
  // already at +07. Run the formatter in a process at another zone: still Bangkok.
  const module = new URL("../src/thaiMonth.js", import.meta.url).href;
  const script = `import { thaiTime } from ${JSON.stringify(module)}; console.log(thaiTime(new Date("2026-11-04T07:05:00Z")), new Date("2026-11-04T07:05:00Z").getHours());`;
  for (const zone of ["UTC", "America/New_York"]) {
    const out = execFileSync(process.execPath, ["--input-type=module", "-e", script], { env: { ...process.env, TZ: zone }, encoding: "utf8" });
    const [time, localHour] = out.trim().split(" ");
    assert.ok(localHour !== "14", `the child really runs at ${zone}`);
    assert.equal(time, "14:05", zone);
  }
});

test("UI_67_the_line_shows_when_the_data_loaded_never_a_fixed_time", async () => {
  const at = (d: Date) => plain(renderToStaticMarkup(createElement(AccountBody, data(d))));
  assert.ok(at(LOADED).includes("ข้อมูล ณ เวลา 14:05 น."));
  assert.ok(at(new Date("2026-11-04T11:42:00Z")).includes("ข้อมูล ณ เวลา 18:42 น."));
  for (const file of [read("screens", "Account.tsx"), read("components", "HostScreen.tsx"), read("copy.ts")]) {
    assert.deepEqual(file.match(/[0-9]{1,2}:[0-9]{2} ?น\./g), null);
  }
  // loadAccount stamps the moment its answers arrived.
  answerFromMock(true);
  const before = Date.now();
  const loaded = await loadAccount();
  const after = Date.now();
  assert.ok(loaded.loadedAt.getTime() >= before && loaded.loadedAt.getTime() <= after, loaded.loadedAt.toISOString());
  assert.equal(loaded.account.balance, "9500.00");
});

// ---- UI-68: the passbook card ------------------------------------------------------------

test("UI_68_the_passbook_shows_its_words_in_order_with_the_apis_balance", () => {
  const html = renderToStaticMarkup(createElement(Passbook, { balance: "4300.00" }));
  assert.equal(plain(html), "ออมทรัพย์xxx-x-x1234-xยอดเงินที่ใช้ได้4,300.00บาทข้อมูลจำลองสำหรับเดโมดูรายการล่าสุด");
  // A darker spine first, then the ruled page; the passbook icon in the top right.
  assert.match(html, new RegExp(`^<section aria-label="ออมทรัพย์"[^>]*><span aria-hidden="true" class="[^"]*${HOST.spine}"></span><div class="[^"]*${HOST.rules}"`));
  const passbook = /passbook: "([^"]+)"/.exec(read("components", "Icon.tsx"))?.[1] ?? "";
  assert.ok(passbook !== "" && html.includes(`d="${passbook}"`));
  // The title's chevron is a drawn icon, not a character the Thai fonts may lack.
  assert.ok(!plain(html).includes("⌄"));
});

test("UI_68_the_decoration_is_horizontal_lines_only_no_image_no_diagonal_no_red", () => {
  const css = read("index.css");
  const rules = /\.host-rules \{([^}]*)\}/.exec(css)?.[1] ?? "";
  assert.match(rules, /repeating-linear-gradient\(to bottom, /);
  assert.ok(!/deg|turn|to (left|right)|to (top|bottom) (left|right)|radial|conic|url\(/.test(rules), rules);
  for (const file of [read("screens", "Account.tsx"), read("components", "HostScreen.tsx")]) {
    assert.ok(!/<img\b|clip-path|polygon|rotate|skew|url\(/.test(file));
  }
  // No green and red shapes: the host's classes use no red or amber colour.
  assert.ok(!/\b(?:risk|warn|red|amber|bar-over)\b/.test(Object.values(HOST).join(" ")), Object.values(HOST).join(" "));
});
