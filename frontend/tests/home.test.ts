/**
 * Home's visual hierarchy (Session 15-UI):
 * UI-33: the state rules, which card shows and which shrinks (homeLayout.ts).
 * UI-34: no colour-only meaning: every accent has an icon and text, the new accent
 *   classes live in accent.ts only, and every coloured item on Home has both.
 * UI-41: the months over budget, counted from the API's rows into one line that says
 *   how many and from when to when (monthStatus.ts), on Home and under the result's bars.
 * UI-42 (rules): the hero's one warning line and one buffer line. Expected months are
 *   worked out by hand from the persona (DESIGN.md section 10), not by the mock.
 * UI-46 (rules): the buffer line is a month over budget and whether money was moved
 *   for it, from GET /buffer/shortfalls (bufferState.ts).
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, test } from "node:test";
import { ACCENT, type Marked } from "../src/accent.ts";
import type { AssistantPlanOut, BufferOut, MonthsOut, PreviewOut, ShortfallMonth, ShortfallsOut } from "../src/api-types.ts";
import { shortfallView } from "../src/bufferState.ts";
import { ASSIST, BUFFER_STATE, HOME, THINK } from "../src/copy.ts";
import { aiBubble, consolidationView, heroView, homeView, walletView, type HomeView } from "../src/homeLayout.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock, SLOW_SUMMARY_MS } from "../src/mock/server.ts";
import { overRange } from "../src/monthStatus.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
const months = (path = "/debts/months") => (call("GET", path).body as MonthsOut).months;
const plan = () => call("GET", "/assistant/plan").body as AssistantPlanOut;
const shortfalls = () => call("GET", "/buffer/shortfalls").body as ShortfallsOut;

/** Home as the screen builds it, from the mock's answers: every month, as Home loads them. */
function home(withPlan: "with plan" | "no plan" = "with plan"): HomeView {
  return homeView({
    months: months(),
    plan: withPlan === "no plan" ? null : plan(),
    buffer: call("GET", "/buffer").body as BufferOut,
    shortfalls: shortfalls(),
  });
}

/** Records a one-month installment of `monthly` due in `month`. */
function recordOne(id: string, month: string, monthly: string): void {
  const out = call("POST", "/installments", {
    client_request_id: id,
    kind: "purchase",
    item_name: "",
    item_price: monthly,
    months: 1,
    monthly_amount: monthly,
    first_due_month: month,
    platform_name: null,
  });
  assert.equal(out.status, 201);
}

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

// ---- UI-33: which card shows, which shrinks -----------------------------------------

test("UI_33_all_in_budget_the_hero_is_one_status_line_and_consolidation_a_banner", () => {
  // 3,500.00 to Dec, then 1,500.00 to Jun 2027 (ตู้เย็น's last month): nine months, all within 5,000.00.
  const view = home();
  assert.equal(view.hero?.status, "all_in");
  assert.equal(view.hero?.barOver, false);
  assert.deepEqual(view.hero?.line, { accent: "debt", icon: "check", text: "เดือนนี้และอีก 8 เดือนอยู่ในงบ" });
  // Nothing to act on: no warning, no buffer line.
  assert.deepEqual([view.hero?.warning, view.hero?.buffer], [null, null]);
  assert.deepEqual(view.consolidation, {
    kind: "banner",
    line: { accent: "quiet", icon: "info", text: "ตอนนี้ยังไม่จำเป็นต้องรวมหนี้" },
    reason: ASSIST.reason.NOT_NEEDED,
  });
  assert.equal(view.assistant, true);
  // 4,800.00 / 3,500.00 a month: 1 month.
  assert.deepEqual([view.wallet.balance, view.wallet.filled, view.wallet.caption], ["4800.00", 1, "พอ 1 เดือน"]);
});

test("UI_33_upcoming_months_over_only_and_the_buffer_covers", () => {
  // The laptop from Nov (3,000.00): Nov and Dec are 6,500.00, over 5,000.00; Jan on 4,500.00.
  scene("over_budget");
  const view = home();
  assert.equal(view.hero?.status, "later_over");
  assert.equal(view.hero?.barOver, false); // this month is 3,500.00
  assert.deepEqual(view.hero?.line, { accent: "debt", icon: "check", text: HOME.withinBudgetNow });
  assert.deepEqual(view.hero?.warning, { accent: "warn", icon: "alert", text: "เกินงบ 2 เดือน (พ.ย. 2569 ถึง ธ.ค. 2569)" });
  // The first month over: Nov, 6,500.00 - 5,000.00 = 1,500.00 over, nothing moved yet.
  // Buffer 4,800.00 + 3,000.00 saved = 7,800.00, so the move is the whole gap.
  const buffer = view.hero?.buffer;
  assert.ok(buffer);
  const { row, ...shown } = buffer; // the API's row as it came, for the bar
  assert.deepEqual([row.month, row.state], ["2026-11", "not_prepared"]);
  assert.deepEqual(shown, {
    month: "2026-11",
    state: "not_prepared",
    total: "6500.00",
    line: { accent: "warn", icon: "alert", text: "พ.ย. 2569 เกินงบ 1,500.00 บาท" },
    prepare: { month: "2026-11", amount: "1500.00", total: "6500.00" },
  });
  assert.equal(view.consolidation?.kind, "banner"); // 2 months in a row, not 3
});

test("UI_33_this_month_over_budget_the_buffer_falls_short_and_the_offer_card_shows", () => {
  // The motorbike from Oct (4,000.00): Oct to Dec 7,500.00, Jan to Jun 5,500.00, then 4,000.00.
  scene("over_budget_now");
  const view = home();
  assert.equal(view.hero?.status, "now_over");
  assert.equal(view.hero?.barOver, true);
  // One warning line covers this month too: no second line saying this month is over.
  assert.equal(view.hero?.line, null);
  assert.deepEqual(view.hero?.warning, { accent: "warn", icon: "alert", text: "เกินงบ 9 เดือน (ต.ค. 2569 ถึง มิ.ย. 2570)" });
  // Oct is 7,500.00, 2,500.00 over; buffer 4,800.00 + 4,800.00 = 9,600.00 holds it.
  assert.deepEqual(view.hero?.buffer?.line, { accent: "warn", icon: "alert", text: "ต.ค. 2569 เกินงบ 2,500.00 บาท" });
  assert.deepEqual(view.hero?.buffer?.prepare, { month: "2026-10", amount: "2500.00", total: "7500.00" });
  const offer = view.consolidation;
  assert.equal(offer?.kind, "offer");
  if (offer?.kind !== "offer") return;
  assert.deepEqual(offer.title, { accent: "bank", icon: "bank", text: "ทางเลือกจากธนาคาร" });
  // Now: 7,500.00 a month, 67,500.00 left; consolidated: 3,369.88 x 24 = 80,877.12 (UI-28).
  assert.deepEqual(
    [offer.currentMonthly, offer.estimate.current_remaining_total, offer.estimate.monthly_payment, offer.estimate.total_cost],
    ["7500.00", "67500.00", "3369.88", "80877.12"],
  );
  // One benefit line, the API's monthly_reduction as is (UI-38): 7,500.00 - 3,369.88.
  assert.equal(offer.benefit, "ค่างวดลดลงเดือนละ 4,130.12 บาท ทุกเดือนกลับมาอยู่ในงบ");
});

test("UI_33_an_empty_buffer_gets_no_buffer_line_and_the_wallet_shows_it_empty", () => {
  scene("over_budget_empty_buffer");
  const view = home();
  assert.equal(view.hero?.status, "later_over");
  assert.deepEqual(view.hero?.warning?.text, "เกินงบ 2 เดือน (พ.ย. 2569 ถึง ธ.ค. 2569)");
  // The month still says it is over, but nothing in the buffer to move: no button.
  assert.deepEqual(view.hero?.buffer?.line.text, "พ.ย. 2569 เกินงบ 1,500.00 บาท");
  assert.equal(view.hero?.buffer?.prepare, null);
  assert.deepEqual([view.wallet.balance, view.wallet.filled, view.wallet.caption], ["0.00", 0, "ยังไม่พอ 1 เดือน"]);
});

test("UI_33_the_empty_buffer_scene_moves_the_buffer_to_the_main_account", () => {
  // Main 9,500.00 - 3,000.00 saved for the laptop = 6,500.00; the 7,800.00 buffer moved
  // back makes it 14,300.00 (review F5). A 61,000.00 item saves 10% = 6,100.00 and
  // leaves 8,200.00, above the 500.00 safety net. Had the buffer been deleted instead,
  // 6,500.00 - 6,100.00 = 400.00 would skip the saving.
  scene("over_budget_empty_buffer");
  const preview = call("POST", "/installments/preview", {
    client_request_id: "after-empty-buffer",
    kind: "purchase",
    item_name: "",
    item_price: "61000.00",
    months: 10,
    monthly_amount: "6100.00",
    first_due_month: "2026-11",
    platform_name: null,
  });
  assert.equal(preview.status, 200);
  assert.equal((preview.body as PreviewOut).saving_if_recorded, "6100.00");
});

test("UI_33_without_the_plan_the_assistant_and_consolidation_cards_are_left_out", () => {
  scene("over_budget");
  const view = home("no plan");
  assert.equal(view.assistant, false);
  assert.equal(view.consolidation, null);
  // The hero needs no plan: the months over and the buffer line come from their own answers.
  assert.equal(view.hero?.warning?.text, "เกินงบ 2 เดือน (พ.ย. 2569 ถึง ธ.ค. 2569)");
  assert.equal(view.hero?.buffer?.month, "2026-11");
});

test("UI_33_hero_edges_no_rows_and_a_single_month", () => {
  assert.equal(heroView([], null), null);
  const one = months("/debts/months?count=1");
  assert.equal(one.length, 1);
  // No month after this one: "this month is in budget", never "and 0 more months".
  assert.deepEqual(heroView(one, null)?.line?.text, HOME.withinBudgetNow);
});

test("UI_33_wallet_segments_follow_the_api_month_count_capped_at_six", () => {
  const wallet = (months_covered: number | null) => {
    const w = walletView({ balance: "9000.00", monthly_total: "1000.00", months_covered });
    return [w.filled, w.caption];
  };
  assert.deepEqual(wallet(null), [0, "ไม่มีค่างวด"]);
  assert.deepEqual(wallet(0), [0, "ยังไม่พอ 1 เดือน"]);
  assert.deepEqual(wallet(6), [6, "พอ 6 เดือน"]);
  assert.deepEqual(wallet(9), [6, "พอ 9 เดือน"]); // the caption keeps the API's number
});

test("UI_33_banner_wording_per_reason", () => {
  const reasons = ["OVERDUE_DEBT", "DISPUTED_DEBT", "ESTIMATE_TOO_LARGE", "PAYMENT_ABOVE_BUDGET", "PAYMENT_ABOVE_ONE_THIRD_OF_INCOME"] as const;
  for (const reason of reasons) {
    const view = consolidationView({ eligible: false, reason, estimate: null });
    assert.equal(view.kind, "banner");
    if (view.kind !== "banner") continue;
    assert.equal(view.line.text, ASSIST.notWorth, reason);
    assert.equal(view.reason, ASSIST.reason[reason]);
    assert.ok(view.reason.length > 0, `${reason}: the banner opens to words, never to nothing`);
  }
});

test("UI_33_ai_bubble_loading_and_the_first_line", () => {
  const p = plan();
  assert.deepEqual(aiBubble({ state: "loading" }, p), { state: "loading" });
  assert.deepEqual(aiBubble({ state: "ready", data: { text: "หนึ่ง\nสอง\n\nสาม", source: "ai", reason: "ok" } }, p), {
    state: "done",
    first: "หนึ่ง",
    rest: ["สอง", "สาม"],
  });
  // The Demo panel's states: slow (loading) and failing (the plan's own words, AI-29).
  scene("ai_slow");
  assert.equal(call("GET", "/assistant/summary").delayMs, SLOW_SUMMARY_MS);
  scene("ai_failing");
  assert.equal(call("GET", "/assistant/summary").status, 503);
  scene("persona");
  const answer = call("GET", "/assistant/summary");
  assert.deepEqual([answer.status, answer.delayMs], [200, undefined]);
});

// ---- UI-34: never colour only --------------------------------------------------------

test("UI_34_every_accent_has_its_own_icon_and_thai_text", () => {
  const looks = Object.values(ACCENT);
  for (const look of looks) {
    assert.ok(look.icon.length > 0, "icon"); // an IconName: the compiler checks it exists
    assert.match(look.label, /[฀-๿]/, `Thai label: ${look.label}`);
  }
  assert.equal(new Set(looks.map((l) => l.icon)).size, looks.length, "one icon per accent");
});

// The accent families added for this design: anywhere else they could colour
// something without the icon and text that accent.ts pairs them with.
// host-: the host shell of #/account (Session 21), whose classes live in accent.ts HOST.
const ACCENT_CLASS = /\b(?:bg|text|border|from|via|to|ring|outline|fill|stroke|divide)-(?:teal|bank|ai|quiet|host)-/;

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? sources(path) : /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

test("UI_34_accent_classes_are_only_in_accent_ts", () => {
  const hits = sources("src")
    .filter((file) => file !== join("src", "accent.ts"))
    .flatMap((file) => readFileSync(file, "utf8").split("\n").filter((line) => ACCENT_CLASS.test(line)).map((line) => `${file}: ${line.trim()}`));
  assert.deepEqual(hits, []);
  // Guard the guard.
  for (const line of ['"hover:bg-teal-50"', "from-ai-from", "text-bank-800", "border-quiet-line"]) assert.ok(ACCENT_CLASS.test(line), line);
  for (const line of ["--color-teal-50: #e8f7f7;", "bg-leaf-700", "text-warn-ink"]) assert.ok(!ACCENT_CLASS.test(line), line);
});

function markedItems(view: HomeView): Marked[] {
  const hero = view.hero;
  const c = view.consolidation;
  const heroItems = hero === null ? [] : [hero.line, hero.warning, hero.buffer?.line ?? null];
  return [
    ...heroItems.filter((item): item is Marked => item !== null),
    view.wallet.title,
    ...(c === null ? [] : [c.kind === "banner" ? c.line : c.title]),
  ];
}

test("UI_34_every_coloured_item_on_home_has_an_icon_and_text_in_every_state", () => {
  for (const name of ["persona", "over_budget", "over_budget_now", "over_budget_empty_buffer"]) {
    scene(name);
    const view = home();
    const items = markedItems(view);
    assert.ok(items.length >= 3, name);
    for (const item of items) {
      assert.ok(item.accent in ACCENT, `${name}: ${item.accent}`);
      assert.ok(item.icon.length > 0, `${name}: icon for ${item.text}`);
      assert.ok(item.text.trim() !== "", `${name}: text`);
    }
  }
});

// ---- UI-41: how many months over budget, from when to when -----------------------------

const row = (month: string, over: boolean) => ({ month, over_budget: over });

test("UI_41_over_range_counts_the_rows_over_budget_and_names_the_first_and_the_last", () => {
  assert.equal(overRange([]), null);
  assert.equal(overRange([row("2026-10", false), row("2026-11", false)]), null);
  assert.deepEqual(overRange([row("2026-10", false), row("2026-11", true)]), { count: 1, first: "2026-11", last: "2026-11", together: true });
  assert.deepEqual(overRange([row("2026-10", true), row("2026-11", true), row("2026-12", false)]), {
    count: 2,
    first: "2026-10",
    last: "2026-11",
    together: true,
  });
  // A gap: two months over in a three-month span.
  assert.deepEqual(overRange([row("2026-10", true), row("2026-11", false), row("2026-12", true)]), {
    count: 2,
    first: "2026-10",
    last: "2026-12",
    together: false,
  });
});

test("UI_41_each_line_says_how_many_and_from_when_to_when_and_a_gap_says_ในช่วง", () => {
  // Home's hero (the ⚠ is its icon) and the result's plain line under the bars.
  assert.equal(HOME.overWarning(9, "ต.ค. 2569", "มิ.ย. 2570", true), "เกินงบ 9 เดือน (ต.ค. 2569 ถึง มิ.ย. 2570)");
  assert.equal(HOME.overWarning(1, "พ.ย. 2569", "พ.ย. 2569", true), "เกินงบ 1 เดือน (พ.ย. 2569)");
  assert.equal(HOME.overWarning(2, "ธ.ค. 2569", "ก.พ. 2570", false), "เกินงบ 2 เดือน (ในช่วง ธ.ค. 2569 ถึง ก.พ. 2570)");
  assert.equal(THINK.overSummary(10, "พ.ย. 2569", "ส.ค. 2570", true), "เกินงบ 10 เดือน: พ.ย. 2569 ถึง ส.ค. 2570");
  assert.equal(THINK.overSummary(1, "พ.ย. 2569", "พ.ย. 2569", true), "เกินงบ 1 เดือน: พ.ย. 2569");
  assert.equal(THINK.overSummary(2, "ธ.ค. 2569", "ก.พ. 2570", false), "เกินงบ 2 เดือน ในช่วง ธ.ค. 2569 ถึง ก.พ. 2570");
});

test("UI_41_a_gap_between_months_over_budget_never_reads_as_one_run", () => {
  // Persona: 3,500.00 to Dec, then 1,500.00. 4,000.00 more in Dec and in Feb: 7,500.00 and
  // 5,500.00, over 5,000.00; Jan stays at 1,500.00.
  recordOne("dec", "2026-12", "4000.00");
  recordOne("feb", "2027-02", "4000.00");
  assert.equal(home().hero?.warning?.text, "เกินงบ 2 เดือน (ในช่วง ธ.ค. 2569 ถึง ก.พ. 2570)");
});

test("UI_41_the_hero_counts_the_same_months_as_the_plan_its_buffer_line_is_about", () => {
  // The buffer line is the plan's `covered`, over every month the plan counts over
  // budget; the warning names that many months, never only the next few (review F1).
  for (const [name, count] of [
    ["over_budget", 2],
    ["over_budget_now", 9],
    ["over_budget_empty_buffer", 2],
  ] as const) {
    scene(name);
    assert.equal(plan().months.filter((m) => m.over_budget).length, count, name);
    assert.equal(overRange(months())?.count, count, name);
    assert.ok(home().hero?.warning?.text.startsWith(`เกินงบ ${count} เดือน `), name);
  }
});

// ---- UI-46 (rules): a month over budget and the buffer ------------------------------------

const over = (state: ShortfallMonth["state"], prepared: string, gap: string): ShortfallMonth => ({
  month: "2026-11",
  total: "6500.00",
  budget: "5000.00",
  shortfall: "1500.00",
  prepared,
  remaining_gap: gap,
  state,
  covered_by_buffer: "0.00",
  still_short: "0.00",
});

test("UI_46_not_prepared_partly_prepared_and_prepared_say_the_apis_state", () => {
  const not = shortfallView(over("not_prepared", "0.00", "1500.00"), "5700.00");
  assert.deepEqual(not.line, { accent: "warn", icon: "alert", text: "พ.ย. 2569 เกินงบ 1,500.00 บาท" });
  assert.deepEqual(not.prepare, { month: "2026-11", amount: "1500.00", total: "6500.00" });
  // Partly: the gap left, and the move is that gap only.
  const partly = shortfallView(over("partly_prepared", "600.00", "900.00"), "5100.00");
  assert.deepEqual(partly.line, {
    accent: "warn",
    icon: "alert",
    text: "พ.ย. 2569 เกินงบ 1,500.00 บาท เตรียมจากกันชนแล้ว 600.00 บาท ยังขาด 900.00 บาท",
  });
  assert.deepEqual(partly.prepare?.amount, "900.00");
  // Prepared: a check, the same shortfall (the budget numbers never change), no button.
  const done = shortfallView(over("prepared", "1500.00", "0.00"), "4200.00");
  assert.deepEqual(done.line, { accent: "buffer", icon: "check", text: "พ.ย. 2569 เกินงบ 1,500.00 บาท ย้ายจากกันชนเข้าบัญชีหลักแล้ว อย่าลืมจ่ายค่างวดในแอปผ่อน" });
  assert.equal(done.prepare, null);
  // The words are the brief's own.
  assert.equal(BUFFER_STATE.use, "ใช้กันชนจ่ายส่วนที่เกิน");
});

test("UI_46_the_move_is_the_smaller_of_the_gap_and_the_buffer_and_none_from_an_empty_one", () => {
  // A prepared month gets no button, however much the buffer holds.
  assert.equal(shortfallView(over("prepared", "1500.00", "0.00"), "9000.00").prepare, null);
  assert.equal(shortfallView(over("not_prepared", "0.00", "1500.00"), "1000.00").prepare?.amount, "1000.00");
  assert.equal(shortfallView(over("not_prepared", "0.00", "1500.00"), "1500.00").prepare?.amount, "1500.00");
  assert.equal(shortfallView(over("not_prepared", "0.00", "1500.00"), "1500.01").prepare?.amount, "1500.00");
  assert.equal(shortfallView(over("not_prepared", "0.00", "1500.00"), "0.01").prepare?.amount, "0.01");
  assert.equal(shortfallView(over("not_prepared", "0.00", "1500.00"), "0.00").prepare, null);
  assert.equal(shortfallView(over("partly_prepared", "600.00", "900.00"), "0.00").prepare, null);
});

test("UI_46_the_hero_shows_the_first_month_over_budget_and_it_turns_prepared_after_the_move", () => {
  scene("over_budget");
  const rows = months();
  assert.equal(heroView(rows, null)?.buffer, null); // no answer, no line
  assert.equal(heroView(rows, shortfalls())?.buffer?.state, "not_prepared");
  // Move the gap for Nov, as the buffer screen does: Nov is prepared, Dec is untouched.
  const moved = call("POST", "/buffer/move-to-main", { client_request_id: "nov", amount: "1500.00", for_month: "2026-11" });
  assert.equal(moved.status, 201);
  const after = shortfalls();
  assert.deepEqual(
    after.months.map((m) => [m.month, m.total, m.shortfall, m.state]),
    [
      ["2026-11", "6500.00", "1500.00", "prepared"],
      ["2026-12", "6500.00", "1500.00", "not_prepared"],
    ],
  );
  assert.deepEqual(heroView(rows, after)?.buffer?.line, {
    accent: "buffer",
    icon: "check",
    text: "พ.ย. 2569 เกินงบ 1,500.00 บาท ย้ายจากกันชนเข้าบัญชีหลักแล้ว อย่าลืมจ่ายค่างวดในแอปผ่อน",
  });
  // The months themselves never change after a move: the hero's total and warning stay.
  assert.deepEqual(months(), rows);
  // No month over budget: no line at all.
  scene("persona");
  assert.equal(heroView(months(), shortfalls())?.buffer, null);
});
