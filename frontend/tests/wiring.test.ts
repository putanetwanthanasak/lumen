/**
 * Session 17: the screens on the real API.
 * UI-47: the buffer's move for a month over budget: one request per amount and month,
 *   `for_month` only on that move, the three steps and the brief's words, and "ย้าย"
 *   between the user's own accounts, never "โอน".
 * UI-48: ภาระผ่อนรายเดือน: each month over budget shows its buffer state, and one quiet
 *   line at the bottom says what to do when the app's amount differs.
 * UI-49: the Demo panel switches between the backend's seeded personas (X-Demo-User)
 *   and shows only while the demo endpoints are on.
 * UI-50: the build calls the API (no mock), with the persona's header; a 422 names its
 *   fields next to the form's fields; SETTINGS_REQUIRED is recognised; the assistant's
 *   example is worded from the real plan.
 * UI-51 (critical): no money arithmetic in screen code: amounts are compared, never
 *   added, subtracted, multiplied or divided outside src/money.ts and the mock.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FILL } from "../src/accent.ts";
import {
  answerFromMock,
  ApiError,
  demoEndpointsEnabled,
  demoEndpointsOnce,
  getAssistantSummary,
  getMonths,
  needsSettings,
  rejectedFields,
  USE_MOCK,
} from "../src/api.ts";
import type { AssistantPlanOut, BufferOut, MonthsOut, MoveIn, MovedOut, ShortfallsOut } from "../src/api-types.ts";
import { bufferPlanLines, exampleSummary } from "../src/assistantText.ts";
import { latestOnly, moveBody, mover, moverRegistry, moveRequest, type MoveLock } from "../src/bufferMove.ts";
import { cardMove, shortfallView, shortfallsByMonth } from "../src/bufferState.ts";
import { DemoButton } from "../src/components/DemoPanel.tsx";
import { BUFFER, BUFFER_STATE, MONTHS_VIEW, REJECTED } from "../src/copy.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { demoUser, PERSONAS, setDemoUser, startingUser } from "../src/personas.ts";
import { BufferBody } from "../src/screens/Buffer.tsx";
import { MonthList } from "../src/screens/Months.tsx";
import { rejectedErrors as settingsRejected } from "../src/settingsForm.ts";
import { emptyForm, rejectedErrors as formRejected, toEntry } from "../src/thinkFirstForm.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
const plain = (html: string) => html.replace(/<[^>]+>/g, "");

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

// ---- a fake fetch: the real path of src/api.ts, without a server --------------------

type Seen = { url: string; method: string; headers: Record<string, string>; body: string | null };
const realFetch = globalThis.fetch;

/** Answer every request with `answer(url)`, or reject it as a network error when it gives null. */
function fakeFetch(answer: (url: string) => { status: number; body: unknown } | null): Seen[] {
  const seen: Seen[] = [];
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    seen.push({
      url,
      method: init?.method ?? "GET",
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: typeof init?.body === "string" ? init.body : null,
    });
    const a = answer(url);
    if (a === null) throw new TypeError("Failed to fetch");
    return { status: a.status, json: async () => a.body } as Response;
  }) as typeof fetch;
  return seen;
}

afterEach(() => {
  globalThis.fetch = realFetch;
  answerFromMock(false);
  setDemoUser("demo-mon");
});

// ---- UI-47: the move for a month -----------------------------------------------------

test("UI_47_one_request_per_amount_and_month_and_for_month_only_on_that_move", () => {
  const nov = moveRequest(null, "1500.00", "id-1", "2026-11");
  assert.deepEqual(nov, { amount: "1500.00", id: "id-1", forMonth: "2026-11" });
  // A retry of the same move (lost answer) reuses the id, so the money moves once.
  assert.equal(moveRequest(nov, "1500", "id-2", "2026-11").id, "id-1");
  // Another month, or the free move, is another request.
  assert.equal(moveRequest(nov, "1500.00", "id-3", "2026-12").id, "id-3");
  assert.deepEqual(moveRequest(nov, "1500.00", "id-4"), { amount: "1500.00", id: "id-4" });
  // The body: for_month for the month's move, no key at all for the free move.
  assert.deepEqual(moveBody(nov), { client_request_id: "id-1", amount: "1500.00", for_month: "2026-11" });
  assert.deepEqual(moveBody({ amount: "800.00", id: "id-5" }), { client_request_id: "id-5", amount: "800.00" });
  assert.ok(!("for_month" in moveBody({ amount: "800.00", id: "id-5" })));
});

test("UI_47_a_double_tap_moves_once_and_the_month_turns_prepared_with_its_numbers_unchanged", () => {
  // The contract the screen relies on, in the mock as in the backend (BF-11, BS-05).
  scene("over_budget");
  const before = call("GET", "/buffer/shortfalls").body as ShortfallsOut;
  const body = moveBody(moveRequest(null, "1500.00", "tap", "2026-11"));
  const first = call("POST", "/buffer/move-to-main", body);
  const again = call("POST", "/buffer/move-to-main", body);
  assert.deepEqual([first.status, again.status], [201, 200]);
  assert.equal((again.body as MovedOut).status, "duplicate");
  assert.equal((call("GET", "/buffer").body as BufferOut).balance, "6300.00"); // 7,800.00 - 1,500.00, once
  // The same id for another month is refused, never a second move.
  assert.equal(call("POST", "/buffer/move-to-main", { ...body, for_month: "2026-12" }).status, 409);
  const after = call("GET", "/buffer/shortfalls").body as ShortfallsOut;
  assert.deepEqual(
    after.months.map((m) => [m.month, m.total, m.budget, m.shortfall, m.prepared, m.remaining_gap, m.state]),
    [
      ["2026-11", "6500.00", "5000.00", "1500.00", "1500.00", "0.00", "prepared"],
      ["2026-12", "6500.00", "5000.00", "1500.00", "0.00", "1500.00", "not_prepared"],
    ],
  );
  assert.equal(after.shortfall, before.shortfall); // the budget numbers never change
});

function bufferScreen(): string {
  return renderToStaticMarkup(
    createElement(BufferBody, {
      buffer: call("GET", "/buffer").body as BufferOut,
      shortfalls: call("GET", "/buffer/shortfalls").body as ShortfallsOut,
      onMoved: () => undefined,
    }),
  );
}

test("UI_47_the_buffer_screen_shows_each_month_with_three_steps_and_the_brief_words", () => {
  scene("over_budget");
  const html = bufferScreen();
  const text = plain(html);
  for (const words of [
    "พ.ย. 2569 เกินงบ 1,500.00 บาท",
    "ใช้กันชน 1,500.00 บาท",
    "ย้ายเข้าบัญชีหลัก +1,500.00 บาท",
    "จ่ายค่างวดในแอปผ่อน (ผู้ใช้ทำเอง) ค่างวด พ.ย. 2569 6,500.00 บาท",
    "จ่ายค่างวดในแอปผ่อน (ผู้ใช้ทำเอง) ค่างวด ธ.ค. 2569 6,500.00 บาท",
    "ย้ายก่อนวันที่แอปผ่อนตัดเงิน แนะนำทำในวันเงินเดือนเข้า",
  ]) {
    assert.ok(text.includes(words), words);
  }
  // The steps in order, in one list per month: ① ② ③.
  const lists = [...html.matchAll(/<ol aria-label="ขั้นตอน"[^>]*>(.*?)<\/ol>/g)].map((m) => plain(m[1] ?? ""));
  assert.equal(lists.length, 2);
  const nov = lists[0] ?? "";
  assert.ok(nov.indexOf("ใช้กันชน") < nov.indexOf("ย้ายเข้าบัญชีหลัก") && nov.indexOf("ย้ายเข้าบัญชีหลัก") < nov.indexOf("จ่ายค่างวด"));
  // The primary is the buffer's filled button, once per month; the free move is the outlined one.
  const prime = [...html.matchAll(/<button type="button"[^>]*? class="([^"]*)">.*?ใช้กันชนจ่ายส่วนที่เกิน<\/button>/g)];
  assert.equal(prime.length, 2);
  for (const m of prime) assert.ok(FILL.buffer.split(" ").every((c) => (m[1] ?? "").split(" ").includes(c)), m[1]);
  assert.match(html, /<button type="submit"[^>]*? class="[^"]*border-leaf-700[^"]*">.*?ย้ายกลับบัญชีหลัก<\/button>/);
});

test("UI_47_a_prepared_month_has_a_check_and_no_button_and_the_other_keeps_its", () => {
  scene("over_budget");
  assert.equal(call("POST", "/buffer/move-to-main", { client_request_id: "n", amount: "1500.00", for_month: "2026-11" }).status, 201);
  const html = bufferScreen();
  const text = plain(html);
  assert.ok(text.includes("พ.ย. 2569 เกินงบ 1,500.00 บาท เตรียมเงินจากกันชนแล้ว"));
  assert.equal(html.split("ใช้กันชนจ่ายส่วนที่เกิน").length - 1, 1, "only Dec still has the button");
  assert.ok(!text.includes("ค่างวด พ.ย. 2569"), "no steps left for Nov");
  // Partly prepared: the gap left, and the move is that gap.
  assert.equal(call("POST", "/buffer/move-to-main", { client_request_id: "d", amount: "600.00", for_month: "2026-12" }).status, 201);
  const partly = plain(bufferScreen());
  assert.ok(partly.includes("ธ.ค. 2569 เกินงบ 1,500.00 บาท เตรียมจากกันชนแล้ว 600.00 บาท ยังขาด 900.00 บาท"));
  assert.ok(partly.includes("ใช้กันชน 900.00 บาท"));
});

test("UI_47_the_steps_after_the_move_and_the_success_line_read_as_the_brief", () => {
  // Every number is the API's: the amount and the balance from MovedOut, "before" from GET /buffer.
  assert.equal(BUFFER_STATE.step1Done("1,500.00 บาท", "5,700.00", "4,200.00 บาท"), "ใช้กันชน 1,500.00 บาท (กันชน 5,700.00 → 4,200.00 บาท)");
  assert.equal(
    BUFFER_STATE.success("1,500.00 บาท", "4,200.00 บาท"),
    "ย้าย 1,500.00 บาทเข้าบัญชีหลักแล้ว กันชนเหลือ 4,200.00 บาท จ่ายค่างวดในแอปผ่อนได้เลย",
  );
  assert.equal(BUFFER.move, "ย้ายกลับบัญชีหลัก");
  // Between the user's own accounts it is ย้าย, never โอน.
  const words = [...Object.values(BUFFER), ...Object.values(BUFFER_STATE)].map((v) =>
    typeof v === "function" ? (v as (...a: string[]) => string)("a", "b", "c", "d") : v,
  );
  for (const w of words) assert.doesNotMatch(w, /โอน/, w);
});

// ---- UI-48: ภาระผ่อนรายเดือน -------------------------------------------------------------

test("UI_48_each_month_over_budget_shows_its_buffer_state_and_the_others_none", () => {
  scene("over_budget");
  const months = (call("GET", "/debts/months").body as MonthsOut).months;
  const shortfalls = call("GET", "/buffer/shortfalls").body as ShortfallsOut;
  const html = renderToStaticMarkup(createElement(MonthList, { months, budget: "5000.00", buffer: shortfallsByMonth(shortfalls) }));
  const cards = [...html.matchAll(/<li class="overflow-hidden[^"]*">(.*?)<\/li>(?=<li class="overflow-hidden|<\/ul>$)/g)].map((m) => plain(m[1] ?? ""));
  assert.equal(cards.length, months.length);
  const state = cards.map((c) => [c.includes("เกินงบ 1,500.00 บาท"), c.includes("ใช้กันชนจ่ายส่วนที่เกิน")]);
  // Oct in budget; Nov and Dec over, each with its line and button; the rest in budget.
  assert.deepEqual(state.slice(0, 4), [
    [false, false],
    [true, true],
    [true, true],
    [false, false],
  ]);
  assert.ok(state.slice(3).every(([line, button]) => !line && !button));
  // Without the answer, the months still show, without buffer lines.
  const bare = renderToStaticMarkup(createElement(MonthList, { months, budget: "5000.00", buffer: shortfallsByMonth(null) }));
  assert.ok(!bare.includes("ใช้กันชนจ่ายส่วนที่เกิน"));
});

test("UI_48_one_quiet_line_at_the_bottom_says_what_to_do_when_the_app_differs", () => {
  assert.equal(
    MONTHS_VIEW.scamCheck,
    "ยอดในแอปผ่อนไม่ตรงกับที่นี่? อาจมีรายการที่คุณไม่ได้ทำ ติดต่อแอปผ่อนโดยตรงจากช่องทางในแอป อย่าโอนเงินให้ใครที่โทรมาทวง",
  );
  // After the list, small and muted: quiet, never a warning box.
  const screen = readFileSync("src/screens/Months.tsx", "utf8");
  const list = screen.indexOf("<MonthList");
  const line = screen.indexOf("{MONTHS_VIEW.scamCheck}");
  assert.ok(list > 0 && line > list);
  assert.match(screen.slice(list, line), /<p className="px-1 pt-2 text-caption text-ink-muted">$/);
});

// ---- UI-49: personas and the Demo panel ---------------------------------------------------

test("UI_49_the_personas_are_the_backend_seed_and_switching_changes_the_header", async () => {
  const seed = readFileSync(join("..", "backend", "demo", "kidnee.py"), "utf8");
  const seeded = [...seed.matchAll(/^\s+"(demo-[a-z-]+)": Persona\(/gm)].map((m) => m[1]);
  assert.deepEqual(
    PERSONAS.map((p) => p.id),
    seeded,
  );
  assert.deepEqual([PERSONAS[0]?.id, PERSONAS[0]?.name], ["demo-mon", "ม่อน"]);
  assert.equal(demoUser(), "demo-mon");
  setDemoUser("someone-else"); // not a persona: ignored
  assert.equal(demoUser(), "demo-mon");
  setDemoUser("demo-over");
  const seen = fakeFetch(() => ({ status: 200, body: { months: [], months_truncated: false } }));
  await getMonths();
  assert.equal(seen[0]?.headers["X-Demo-User"], "demo-over");
});

test("UI_49_the_demo_panel_shows_only_while_the_demo_endpoints_are_on", async () => {
  // The probe writes nothing: an empty body, which a mounted POST /demo/payday refuses (422).
  let seen = fakeFetch(() => ({ status: 422, body: { detail: [{ type: "missing", loc: ["body", "month"] }] } }));
  assert.equal(await demoEndpointsEnabled(), true);
  assert.deepEqual([seen[0]?.url, seen[0]?.method, seen[0]?.body], ["/api/demo/payday", "POST", "{}"]);
  seen = fakeFetch(() => ({ status: 404, body: { detail: "Not Found" } }));
  assert.equal(await demoEndpointsEnabled(), false);
  fakeFetch(() => null); // no answer at all: no panel
  assert.equal(await demoEndpointsEnabled(), false);
  // Before the probe answers, the header has no Demo button.
  assert.equal(renderToStaticMarkup(createElement(DemoButton)), "");
});

// ---- UI-50: the real API --------------------------------------------------------------------

test("UI_50_the_build_calls_the_api_and_only_mode_mock_answers_from_the_mock", () => {
  assert.equal(USE_MOCK, false); // no define under node --test, as in `vite build`
  const config = readFileSync("vite.config.ts", "utf8");
  assert.match(config, /define: \{ __KIDNEE_MOCK__: JSON\.stringify\(mode === "mock"\) \}/);
  assert.match(config, /host: "127\.0\.0\.1"/);
  assert.doesNotMatch(config, /0\.0\.0\.0"/);
});

test("UI_50_a_422_names_its_fields_next_to_the_forms_fields", async () => {
  const detail = [
    { type: "string_too_short", loc: ["body", "platform_name"] },
    { type: "value_error", loc: ["body", "item_price"] },
    { type: "missing", loc: ["body"] },
  ];
  const error = new ApiError(422, detail);
  assert.deepEqual(error.fields, ["platform_name", "item_price"]);
  assert.deepEqual(rejectedFields(error), ["platform_name", "item_price"]);
  assert.deepEqual(rejectedFields(new ApiError(409, { code: "SETTINGS_REQUIRED", message: "m" })), []);
  assert.deepEqual(formRejected(error.fields), { platform: REJECTED, price: REJECTED });
  assert.equal(formRejected(["client_request_id"]), null); // nothing the user can fix: "failed"
  // Settings: the saving rule's fields sit under its tag in `loc`.
  assert.deepEqual(settingsRejected(new ApiError(422, [{ loc: ["body", "saving_rule", "percent", "percent"] }]).fields), { percent: REJECTED });
  assert.deepEqual(settingsRejected(["monthly_installment_budget", "amount"]), { budget: REJECTED, fixed: REJECTED });
  // Through the real path: the fields come back on the thrown error.
  fakeFetch(() => ({ status: 422, body: { detail } }));
  await assert.rejects(getMonths(), (e: unknown) => e instanceof ApiError && e.fields.length === 2);
});

test("UI_50_settings_required_and_network_errors_are_told_apart", async () => {
  fakeFetch(() => ({ status: 409, body: { detail: { code: "SETTINGS_REQUIRED", message: "set income and budget with POST /settings first" } } }));
  await assert.rejects(getMonths(), (e: unknown) => needsSettings(e));
  fakeFetch(() => null);
  await assert.rejects(getMonths(), (e: unknown) => !needsSettings(e) && !(e instanceof ApiError)); // a retry, not settings
});

test("UI_50_a_blank_app_name_is_sent_as_null", () => {
  const form = { ...emptyForm(), price: "1000", months: "2", monthly: "500", firstDue: "2026-11" };
  for (const platform of ["", "   "]) {
    const built = toEntry({ ...form, platform }, "r");
    assert.ok(built.ok);
    assert.equal(built.entry.platform_name, null);
  }
});

test("UI_50_the_assistant_example_is_worded_from_the_real_plan_and_labelled", async () => {
  scene("over_budget_now");
  const plan = call("GET", "/assistant/plan").body as AssistantPlanOut;
  const seen = fakeFetch((url) => (url === "/api/assistant/plan" ? { status: 200, body: plan } : { status: 404, body: null }));
  const out = await getAssistantSummary();
  assert.deepEqual(out, { text: exampleSummary(plan), is_example: true });
  // No AI endpoint is called: only the plan.
  assert.deepEqual(
    seen.map((s) => [s.method, s.url]),
    [["GET", "/api/assistant/plan"]],
  );
});

// ---- UI-51 (critical): no money arithmetic in screen code ---------------------------------

const ARITHMETIC = /toSatang\([^)]*\)\s*[-+*/%]|[-+*/%]\s*toSatang\(|\b[0-9]+n\s*[-+*/%]|[-+*/%]\s*[0-9]+n\b/;

function screenFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "mock" ? [] : screenFiles(path);
    return /\.(ts|tsx)$/.test(name) && path !== join("src", "money.ts") ? [path] : [];
  });
}

test("UI_51_screen_code_compares_amounts_and_never_adds_them_up", () => {
  const hits = screenFiles("src").flatMap((file) =>
    readFileSync(file, "utf8")
      .split("\n")
      .flatMap((line, i) => (ARITHMETIC.test(line) || /mock\/satang/.test(line) ? [`${file}:${i + 1}: ${line.trim()}`] : [])),
  );
  assert.deepEqual(hits, []);
});

test("UI_51_the_scanner_catches_arithmetic_on_amounts", () => {
  const caught = [
    "const left = toSatang(balance) - toSatang(amount);",
    "toSatang(a) + 1n",
    "const t = 3n * toSatang(total);",
    "x = gap * 100n",
  ];
  for (const line of caught) assert.ok(ARITHMETIC.test(line), line);
  const allowed = ["toSatang(amount) > 0n", "toSatang(a) <= toSatang(b) ? a : b", "toSatang(x) === 0n", "i + 1"];
  for (const line of allowed) assert.ok(!ARITHMETIC.test(line), line);
});

// ---- UI-47: one move at a time (Bugs found, Session 17 PR B) ------------------------------

function recorder(answer: (body: MoveIn) => Promise<MovedOut>) {
  const sent: MoveIn[] = [];
  let n = 0;
  const m = mover(
    (body) => {
      sent.push(body);
      return answer(body);
    },
    () => `id-${(n += 1)}`,
    (e) => (e instanceof ApiError ? e.code : null),
  );
  return { m, sent };
}

const movedOut = (body: MoveIn): MovedOut => ({
  transaction_id: "t",
  status: "created",
  amount: body.amount,
  for_month: body.for_month ?? null,
  balance: "4200.00",
});

test("UI_47_two_presses_in_the_same_task_send_one_move", async () => {
  const { m, sent } = recorder(async (body) => movedOut(body));
  const first = m.press("1500.00", "2026-10");
  const second = m.press("1500.00", "2026-10"); // before anything re-rendered
  assert.ok(first !== null);
  assert.equal(second, null);
  await first;
  assert.deepEqual(sent, [{ client_request_id: "id-1", amount: "1500.00", for_month: "2026-10" }]);
  // Once answered, a new press is a new move with a new id.
  await m.press("1500.00", "2026-11");
  assert.deepEqual(
    sent.map((b) => [b.client_request_id, b.for_month]),
    [
      ["id-1", "2026-10"],
      ["id-2", "2026-11"],
    ],
  );
});

test("UI_47_a_retry_after_a_lost_answer_resends_the_same_id_and_a_422_starts_anew", async () => {
  let fail: unknown = new TypeError("Failed to fetch");
  const { m, sent } = recorder(async (body) => {
    if (fail !== null) throw fail;
    return movedOut(body);
  });
  await assert.rejects(m.press("1500.00", "2026-10") ?? Promise.resolve(), (e: unknown) => e instanceof TypeError);
  fail = null;
  await m.press("1500.00", "2026-10");
  assert.deepEqual(
    sent.map((b) => b.client_request_id),
    ["id-1", "id-1"],
  );
  fail = new ApiError(422, { code: "AMOUNT_ABOVE_BALANCE", message: "m" });
  await assert.rejects(m.press("900.00", "2026-11") ?? Promise.resolve(), (e: unknown) => e instanceof ApiError);
  fail = null;
  await m.press("900.00", "2026-11");
  // Nothing moved on the 422, so the next press is a new request: its own id.
  const ids = sent.map((b) => b.client_request_id);
  assert.equal(ids.length, 4);
  assert.ok(ids[2] !== "id-1" && ids[3] !== "id-1" && ids[2] !== ids[3], ids.join(","));
});

test("UI_47_the_months_button_moves_for_its_month_and_the_free_move_for_none", () => {
  // Break test B-UI-190 found no test for this: the month's button must label its move,
  // or the month never turns prepared. Each form has its own mover, on the screen's lock.
  const screen = readFileSync("src/screens/Buffer.tsx", "utf8");
  const card = screen.slice(screen.indexOf("function PrepareCard("));
  assert.match(card, /const forMonth = MOVES\.get\(view\.month\);/);
  assert.match(card, /forMonth\.press\(p\.amount, p\.month\)/);
  const free = screen.slice(screen.indexOf("async function submit("), screen.indexOf("function PrepareCard("));
  assert.match(free, /free\.press\(parsed\.value\);/);
  assert.equal(screen.split(".press(").length - 1, 2, "two moves, no other");
});

// ---- Review F1: one move at a time on the whole screen -------------------------------------

test("UI_47_a_move_for_another_month_waits_while_one_is_out", async () => {
  const lock: MoveLock = { held: false, out: null };
  const sent: MoveIn[] = [];
  let answer: (out: MovedOut) => void = () => undefined;
  const send = (body: MoveIn) => {
    sent.push(body);
    return new Promise<MovedOut>((resolve) => {
      answer = resolve;
    });
  };
  let n = 0;
  const newId = () => `id-${(n += 1)}`;
  const nov = mover(send, newId, () => null, lock);
  const dec = mover(send, newId, () => null, lock);
  const free = mover(send, newId, () => null, lock);
  const first = nov.press("1500.00", "2026-11");
  assert.ok(first !== null);
  assert.equal(dec.press("1500.00", "2026-12"), null, "Dec waits for Nov");
  assert.equal(free.press("100.00"), null, "the free move waits too");
  answer(movedOut(sent[0] as MoveIn));
  await first;
  const second = dec.press("1500.00", "2026-12");
  assert.ok(second !== null, "free again once Nov answered");
  answer(movedOut(sent[1] as MoveIn));
  await second;
  assert.deepEqual(
    sent.map((b) => b.for_month),
    ["2026-11", "2026-12"],
  );
});

test("UI_47_an_older_balance_never_replaces_a_newer_one", () => {
  const reads = latestOnly();
  const afterNov = reads.take();
  const afterDec = reads.take();
  // Nov's GET /buffer answers last: it is not shown.
  assert.deepEqual([afterNov(), afterDec()], [false, true]);
  const screen = readFileSync("src/screens/Buffer.tsx", "utf8");
  // One registry for the page, every mover from it; "before" is the balance when the move starts.
  assert.equal(screen.split("moverRegistry(").length - 1, 1);
  assert.match(screen, /const free = MOVES\.get\("free"\);/);
  assert.equal(screen.split("mover(").length - 1, 1, "no mover outside the registry");
  assert.match(screen, /const before = moves\.balanceNow\(\);/);
  assert.match(screen, /disabled=\{moves\.moving\}/);
  assert.match(screen, /disabled=\{moving\}/);
});

// ---- Review F2: the buffer summary adds up once a month is prepared ------------------------

test("UI_47_the_buffer_summary_says_the_gap_left_once_a_month_is_prepared", () => {
  const plan = { shortfall: "3000.00", remaining_gap: "3000.00", balance: "2000.00", covered: false, still_short: "1000.00" };
  assert.deepEqual(bufferPlanLines(plan).lines, ["ค่างวดส่วนที่เกินงบรวมทุกเดือน 3,000.00 บาท", "กันชน 2,000.00 บาท ยังขาดอีก 1,000.00 บาท"]);
  // Nov's 1,500.00 moved: 1,500.00 not prepared, 500.00 in the buffer, 1,000.00 short.
  const partly = bufferPlanLines({ ...plan, remaining_gap: "1500.00", balance: "500.00" });
  assert.deepEqual(partly, {
    tone: "warn",
    lines: ["ค่างวดส่วนที่เกินงบรวมทุกเดือน 3,000.00 บาท", "ยังไม่ได้เตรียม 1,500.00 บาท", "กันชน 500.00 บาท ยังขาดอีก 1,000.00 บาท"],
  });
  // Every month prepared and the buffer at 0.00: never "พอจ่ายส่วนที่เกินได้ทั้งหมด" with 0.00.
  const all = bufferPlanLines({ ...plan, remaining_gap: "0.00", balance: "0.00", covered: true, still_short: "0.00" });
  assert.deepEqual(all, { tone: "ok", lines: ["ค่างวดส่วนที่เกินงบรวมทุกเดือน 3,000.00 บาท", "เตรียมเงินจากกันชนครบทุกเดือนที่เกินงบแล้ว"] });
});

// ---- Review F3, F4: the persona in the mock, and a probe without an answer ------------------

test("UI_49_the_mock_always_starts_as_mon_whatever_the_api_choice_kept", () => {
  assert.equal(startingUser(true, "demo-over"), "demo-mon");
  assert.equal(startingUser(false, "demo-over"), "demo-over");
  assert.equal(startingUser(false, "someone-else"), "demo-mon");
  assert.equal(startingUser(false, null), "demo-mon");
});

test("UI_49_a_probe_without_an_answer_is_asked_again", async () => {
  let seen = fakeFetch(() => null); // the API is not up yet
  assert.equal(await demoEndpointsOnce(), false);
  // What the Vite proxy answers while the backend is down: asked again too (round 2 F3).
  seen = fakeFetch(() => ({ status: 502, body: null }));
  assert.equal(await demoEndpointsOnce(), false);
  assert.equal(seen.length, 1);
  seen = fakeFetch(() => ({ status: 422, body: { detail: [] } }));
  assert.equal(await demoEndpointsOnce(), true);
  assert.equal(seen.length, 1, "asked again");
  seen = fakeFetch(() => ({ status: 404, body: null }));
  assert.equal(await demoEndpointsOnce(), true, "kept once the API answered");
  assert.equal(seen.length, 0);
});

// ---- Review round 2: an unknown outcome keeps its retry, and a reopened screen its lock -----

function registry(answer: (body: MoveIn) => Promise<MovedOut>) {
  const sent: MoveIn[] = [];
  let n = 0;
  const moves = moverRegistry((lock) =>
    mover(
      (body) => {
        sent.push(body);
        return answer(body);
      },
      () => `id-${(n += 1)}`,
      (e) => (e instanceof ApiError ? e.code : null),
      lock,
    ),
  );
  return { moves, sent };
}

test("UI_47_a_move_with_an_unknown_outcome_keeps_its_button_and_its_id", async () => {
  // The ledger commits, then the bank call fails (500): the API now says Nov is
  // prepared, but only a retry under the same id finishes the move.
  let fail = true;
  const { moves, sent } = registry(async (body) => {
    if (fail) throw new ApiError(500, null);
    return movedOut(body);
  });
  await assert.rejects(moves.get("2026-11").press("1500.00", "2026-11") ?? Promise.resolve(), (e: unknown) => e instanceof ApiError);
  const prepared = shortfallView(
    { month: "2026-11", total: "6500.00", budget: "5000.00", shortfall: "1500.00", prepared: "1500.00", remaining_gap: "0.00", state: "prepared", covered_by_buffer: "0.00", still_short: "0.00" },
    "4200.00",
  );
  assert.equal(prepared.prepare, null, "the API's answer alone would leave no button");
  const retry = cardMove(prepared, moves.get("2026-11").kept());
  assert.deepEqual(retry, { month: "2026-11", amount: "1500.00", total: "6500.00" });
  fail = false;
  await moves.get("2026-11").press(retry?.amount ?? "", retry?.month);
  assert.deepEqual(
    sent.map((b) => [b.client_request_id, b.for_month]),
    [
      ["id-1", "2026-11"],
      ["id-1", "2026-11"],
    ],
  );
  // Answered: nothing kept, and the card goes back to the API's answer.
  assert.equal(moves.get("2026-11").kept(), null);
  assert.equal(cardMove(prepared, null), null);
  // The card offers that move (Buffer.tsx), and says the outcome is unknown.
  const screen = readFileSync("src/screens/Buffer.tsx", "utf8");
  assert.match(screen, /const prepare: Prepare \| null = done === null \? cardMove\(view, kept\) : null;/);
  assert.match(screen, /kept !== null && !busy \? BUFFER\.failed/);
  // A 422 moved nothing: nothing kept either.
  const above = registry(async () => {
    throw new ApiError(422, { code: "AMOUNT_ABOVE_BALANCE", message: "m" });
  });
  await assert.rejects(above.moves.get("2026-12").press("1500.00", "2026-12") ?? Promise.resolve(), () => true);
  assert.equal(above.moves.get("2026-12").kept(), null);
});

test("UI_47_a_screen_reopened_while_a_move_is_out_cannot_send_a_second_one", async () => {
  let answer: (out: MovedOut) => void = () => undefined;
  const { moves, sent } = registry(
    (body) =>
      new Promise<MovedOut>((resolve) => {
        answer = () => resolve(movedOut(body));
      }),
  );
  const first = moves.get("2026-11").press("1500.00", "2026-11");
  assert.ok(first !== null);
  // Leave and come back: the screen gets its movers from the same registry.
  assert.equal(moves.lock.held, true);
  assert.equal(moves.get("2026-11").press("1500.00", "2026-11"), null);
  assert.equal(moves.get("free").press("100.00"), null);
  assert.ok(moves.lock.out instanceof Promise, "the reopened screen can wait for it");
  answer(movedOut(sent[0] as MoveIn));
  await first;
  await moves.lock.out;
  assert.equal(moves.lock.held, false);
  assert.equal(sent.length, 1);
  // The screen waits for it and reads again (Buffer.tsx).
  const screen = readFileSync("src/screens/Buffer.tsx", "utf8");
  assert.match(screen, /const out = MOVES\.lock\.out;[\s\S]*?setMoving\(false\);\n\s+refresh\(\);/);
  assert.match(screen, /useState\(MOVES\.lock\.held\)/);
});
