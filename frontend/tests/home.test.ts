/**
 * Home's visual hierarchy (Session 15-UI):
 * UI-33: the state rules, which card shows and which shrinks (homeLayout.ts).
 * UI-34: no colour-only meaning: every accent has an icon and text, the new accent
 *   classes live in accent.ts only, and every coloured item on Home has both.
 * UI-36 (critical, money): the mock's over_by on GET /debts/months rows. Expected
 *   amounts are worked out by hand from the persona (DESIGN.md section 10), not by
 *   the mock.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, test } from "node:test";
import { ACCENT, type Marked } from "../src/accent.ts";
import type { AssistantPlanOut, BufferOut, DebtSummary, MonthsOut, PreviewOut } from "../src/api-types.ts";
import { ASSIST, HOME } from "../src/copy.ts";
import { aiBubble, consolidationView, heroView, homeView, walletView, type HomeView } from "../src/homeLayout.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock, SLOW_SUMMARY_MS } from "../src/mock/server.ts";
import { toSatang } from "../src/money.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mint");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
const months = (path = "/debts/months") => (call("GET", path).body as MonthsOut).months;

/** Home as the screen builds it, from the mock's answers. */
function home(plan: "with plan" | "no plan" = "with plan"): HomeView {
  return homeView({
    months: months("/debts/months?count=6"),
    plan: plan === "no plan" ? null : (call("GET", "/assistant/plan").body as AssistantPlanOut),
    buffer: call("GET", "/buffer").body as BufferOut,
    monthlyTotal: (call("GET", "/debts/summary").body as DebtSummary).monthly_total,
  });
}

const chips = (view: HomeView) => view.hero?.strip?.chips.map((c) => [c.text, c.amount]) ?? [];

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

// ---- UI-33: which card shows, which shrinks -----------------------------------------

test("UI_33_all_in_budget_the_hero_is_one_status_line_and_consolidation_a_banner", () => {
  // 3,500.00 to Dec, then 1,500.00: the six months shown are all within 5,000.00.
  const view = home();
  assert.equal(view.hero?.status, "all_in");
  assert.equal(view.hero?.barOver, false);
  assert.deepEqual(view.hero?.line, { accent: "debt", icon: "check", text: "เดือนนี้และอีก 5 เดือนอยู่ในงบ" });
  assert.equal(view.hero?.strip, null); // nothing to act on: no strip
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
  // The laptop from Nov (3,000.00): Nov and Dec are 6,500.00, 1,500.00 over each.
  scene("over_budget");
  const view = home();
  assert.equal(view.hero?.status, "later_over");
  assert.equal(view.hero?.barOver, false); // this month is 3,500.00
  assert.deepEqual(view.hero?.line, { accent: "debt", icon: "check", text: HOME.withinBudgetNow });
  assert.deepEqual(chips(view), [
    ["พ.ย. 2569", "+1,500.00 บาท"],
    ["ธ.ค. 2569", "+1,500.00 บาท"],
  ]);
  // Buffer 4,800.00 + 3,000.00 saved = 7,800.00 covers the 3,000.00 over in all.
  assert.equal(view.hero?.strip?.more, null); // no month after Dec is over
  assert.equal(view.hero?.strip?.shortfall, "ค่างวดส่วนที่เกินงบรวมทุกเดือน 3,000.00 บาท");
  assert.deepEqual(view.hero?.strip?.buffer, { accent: "buffer", icon: "shield", text: "กันชน 7,800.00 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด" });
  assert.deepEqual(view.hero?.strip?.link, { accent: "buffer", icon: "shield", text: HOME.useBuffer, route: "buffer" });
  assert.equal(view.consolidation?.kind, "banner"); // 2 months in a row, not 3
});

test("UI_33_this_month_over_budget_the_buffer_falls_short_and_the_offer_card_shows", () => {
  // The motorbike from Oct (4,000.00): Oct to Dec 7,500.00, Jan to Mar 5,500.00.
  scene("over_budget_now");
  const view = home();
  assert.equal(view.hero?.status, "now_over");
  assert.equal(view.hero?.barOver, true);
  assert.deepEqual(view.hero?.line, { accent: "warn", icon: "alert", text: HOME.overBudgetNow });
  assert.deepEqual(chips(view), [
    ["ต.ค. 2569", "+2,500.00 บาท"],
    ["พ.ย. 2569", "+2,500.00 บาท"],
    ["ธ.ค. 2569", "+2,500.00 บาท"],
    ["ม.ค. 2570", "+500.00 บาท"],
    ["ก.พ. 2570", "+500.00 บาท"],
    ["มี.ค. 2570", "+500.00 บาท"],
  ]);
  // The chips add up to 9,000.00, but Apr to Jun 2027 are 500.00 over too, after the
  // six months shown. The buffer line counts all nine months, so the strip says so and
  // shows the total it is about; otherwise 9,600.00 "still short" reads wrong (review F1).
  assert.equal(view.hero?.strip?.more, "และอีก 3 เดือนหลังจากนั้น");
  // 3 x 2,500.00 + 6 x 500.00 = 10,500.00 over; buffer 4,800.00 + 4,800.00 = 9,600.00.
  assert.equal(view.hero?.strip?.shortfall, "ค่างวดส่วนที่เกินงบรวมทุกเดือน 10,500.00 บาท");
  assert.deepEqual(view.hero?.strip?.buffer, { accent: "warn", icon: "alert", text: "กันชน 9,600.00 บาท ยังขาดอีก 900.00 บาท" });
  assert.equal(view.hero?.strip?.link.route, "buffer");
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

test("UI_33_an_empty_buffer_does_not_cover_and_the_link_goes_to_the_months", () => {
  scene("over_budget_empty_buffer");
  const view = home();
  assert.equal(view.hero?.status, "later_over");
  assert.deepEqual(view.hero?.strip?.buffer, { accent: "warn", icon: "alert", text: "กันชน 0.00 บาท ยังขาดอีก 3,000.00 บาท" });
  assert.deepEqual(view.hero?.strip?.link, { accent: "debt", icon: "calendar", text: HOME.toMonths, route: "months" });
  assert.deepEqual([view.wallet.filled, view.wallet.caption], [0, "ยังไม่พอ 1 เดือน"]);
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
  // The hero still shows the months over; only the plan's lines are missing.
  assert.equal(view.hero?.strip?.chips.length, 2);
  assert.deepEqual([view.hero?.strip?.more, view.hero?.strip?.shortfall, view.hero?.strip?.buffer], [null, null, null]);
});

test("UI_33_the_strip_accounts_for_every_month_the_plan_counts_over_budget", () => {
  // The chips plus "และอีก N เดือน" are exactly the plan's months over budget, the
  // months its shortfall and buffer line are about (review F1).
  for (const name of ["over_budget", "over_budget_now", "over_budget_empty_buffer"]) {
    scene(name);
    const overInPlan = (call("GET", "/assistant/plan").body as AssistantPlanOut).months.filter((m) => m.over_budget).length;
    const strip = home().hero?.strip;
    assert.ok(strip != null, name);
    const after = overInPlan - strip.chips.length; // a count of months, not money
    assert.equal(strip.more, after === 0 ? null : HOME.overMoreMonths(after), name);
  }
});

test("UI_33_hero_edges_no_rows_and_a_single_month", () => {
  assert.equal(heroView([], null, "0.00"), null);
  const one = months("/debts/months?count=1");
  assert.equal(one.length, 1);
  // No month after this one: "this month is in budget", never "and 0 more months".
  assert.deepEqual(heroView(one, null, "4800.00")?.line.text, HOME.withinBudgetNow);
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
    const view = consolidationView({ eligible: false, reason, estimate: null }, "3500.00");
    assert.equal(view.kind, "banner");
    if (view.kind !== "banner") continue;
    assert.equal(view.line.text, ASSIST.notWorth, reason);
    assert.equal(view.reason, ASSIST.reason[reason]);
    assert.ok(view.reason.length > 0, `${reason}: the banner opens to words, never to nothing`);
  }
});

test("UI_33_ai_bubble_loading_failed_and_the_first_line", () => {
  assert.deepEqual(aiBubble({ state: "loading" }), { state: "loading" });
  assert.deepEqual(aiBubble({ state: "error", error: new Error("503") }), { state: "failed" });
  assert.deepEqual(aiBubble({ state: "ready", data: { text: "หนึ่ง\nสอง\n\nสาม", is_example: true } }), {
    state: "done",
    first: "หนึ่ง",
    rest: ["สอง", "สาม"],
    example: true,
  });
  // The Demo panel's states: slow (loading) and failing (error).
  scene("ai_slow");
  assert.equal(call("POST", "/assistant/summary").delayMs, SLOW_SUMMARY_MS);
  scene("ai_failing");
  assert.equal(call("POST", "/assistant/summary").status, 503);
  scene("persona");
  const answer = call("POST", "/assistant/summary");
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
const ACCENT_CLASS = /\b(?:bg|text|border|from|via|to|ring|outline|fill|stroke|divide)-(?:teal|bank|ai|quiet)-/;

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
  const strip = view.hero === null ? null : view.hero.strip;
  const c = view.consolidation;
  return [
    ...(view.hero === null ? [] : [view.hero.line]),
    ...(strip === null ? [] : [strip.title, ...strip.chips, strip.link, ...(strip.buffer === null ? [] : [strip.buffer])]),
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
    // A chip's amount is words too, for screen readers ("เกินงบ ..."), not only "+".
    for (const chip of view.hero?.strip?.chips ?? []) assert.match(chip.spoken, /^เกินงบ [0-9,]+\.[0-9]{2} บาท$/);
  }
});

// ---- UI-36: over_by on GET /debts/months rows (critical, money) -----------------------

test("UI_36_over_by_is_total_minus_budget_when_over_else_zero", () => {
  // Persona: every month in budget.
  assert.ok(months().every((m) => m.over_by === "0.00"));
  // The motorbike from Oct: 7,500.00 to Dec, 5,500.00 to Jun, then 4,000.00 to Sep 2027.
  scene("over_budget_now");
  assert.deepEqual(
    months().map((m) => [m.month, m.over_by]),
    [
      ["2026-10", "2500.00"],
      ["2026-11", "2500.00"],
      ["2026-12", "2500.00"],
      ["2027-01", "500.00"],
      ["2027-02", "500.00"],
      ["2027-03", "500.00"],
      ["2027-04", "500.00"],
      ["2027-05", "500.00"],
      ["2027-06", "500.00"],
      ["2027-07", "0.00"],
      ["2027-08", "0.00"],
      ["2027-09", "0.00"],
    ],
  );
});

test("UI_36_exactly_the_budget_is_not_over_and_one_satang_more_is_over_by_0_01", () => {
  const record = (id: string, monthly: string) =>
    assert.equal(
      call("POST", "/installments", {
        client_request_id: id,
        kind: "purchase",
        item_name: "",
        item_price: monthly,
        months: 1,
        monthly_amount: monthly,
        first_due_month: "2027-01",
        platform_name: null,
      }).status,
      201,
    );
  const jan = () => months().find((m) => m.month === "2027-01");
  record("to-the-budget", "3500.00"); // 1,500.00 + 3,500.00 = 5,000.00
  assert.deepEqual([jan()?.total, jan()?.over_budget, jan()?.over_by], ["5000.00", false, "0.00"]);
  record("one-satang-more", "0.01");
  assert.deepEqual([jan()?.total, jan()?.over_budget, jan()?.over_by], ["5000.01", true, "0.01"]);
});

test("UI_36_over_by_is_never_negative_and_positive_exactly_when_over_budget", () => {
  for (const name of ["persona", "over_budget", "over_budget_now", "over_budget_empty_buffer"]) {
    scene(name);
    for (const m of months()) {
      assert.match(m.over_by, /^(0|[1-9][0-9]*)\.[0-9]{2}$/, `${name} ${m.month}`); // no sign
      assert.equal(toSatang(m.over_by) > 0n, m.over_budget, `${name} ${m.month}`);
    }
  }
});
