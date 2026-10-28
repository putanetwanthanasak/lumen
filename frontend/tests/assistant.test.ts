/**
 * The assistant plan, spread over the screens (Session 14-UI part 4):
 * UI-28 (critical, money): mock GET /assistant/plan follows the merged backend's
 *   rules (backend/app/assistant/plan.py, L69, L70). Expected numbers were worked
 *   out with Python Decimal using the backend's own formula, not with this mock.
 * UI-29: the words around the plan's numbers (assistantText.ts).
 * UI-30: two features and the check: three tabs, no payoff or consolidation screen.
 * UI-31: "สนใจรวมหนี้" sends nothing, and the mock's summary is the plan's own words
 *   (Session 18: the backend's fallback when it has no model, AI-20).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, test } from "node:test";
import type { AssistantPlanOut, AssistantSummaryOut } from "../src/api-types.ts";
import { bufferPlanLines, formHint, planLines, ratePercent } from "../src/assistantText.ts";
import { ASSIST } from "../src/copy.ts";
import { amortisedPayment, assistantPlan, type PlanDebt } from "../src/mock/assistant.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { fromSatang, toSatang } from "../src/mock/satang.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { NAV_TABS, navActive } from "../src/navStyle.ts";
import { ROUTES } from "../src/router.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const plan = () => call("GET", "/assistant/plan").body as AssistantPlanOut;
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
const debt = (first_due_month: string, months: number, monthly_amount: string): PlanDebt => ({
  first_due_month,
  months,
  monthly_amount,
});
// income 20,000.00, budget 5,000.00, no buffer, unless a test says otherwise.
const build = (debts: PlanDebt[], income = "20000.00", budget = "5000.00", buffer = "0.00") =>
  assistantPlan(debts, "2026-10", income, budget, buffer);

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

// ---- UI-28: the plan's numbers (critical) ------------------------------------------

test("UI_28_persona_every_month_in_budget", () => {
  // 3,500.00 to Dec, then 1,500.00 to Jun 2027: never over 5,000.00.
  const p = plan();
  assert.equal(p.back_in_budget_month, null);
  assert.equal(p.pause_until, null);
  assert.equal(p.safe_new_monthly, "1500.00"); // 5,000.00 - 3,500.00
  assert.equal(p.safe_new_from, "2026-10");
  assert.equal(p.safe_new_months, 12);
  assert.deepEqual(p.buffer_plan, { shortfall: "0.00", remaining_gap: "0.00", balance: "4800.00", covered: true, still_short: "0.00" });
  assert.deepEqual(p.consolidation, { eligible: false, reason: "NOT_NEEDED", estimate: null });
  assert.equal(p.months[0]?.month, "2026-10");
  assert.equal(p.months.at(-1)?.month, "2027-06");
  assert.equal(p.months_truncated, false);
});

test("UI_28_two_months_over_later_buffer_covers_no_consolidation", () => {
  // The laptop (3,000.00 x 10 from Nov): Nov and Dec are 6,500.00, then 4,500.00.
  scene("over_budget");
  const p = plan();
  assert.equal(p.back_in_budget_month, "2027-01");
  assert.equal(p.pause_until, null); // this month is 3,500.00
  assert.equal(p.safe_new_from, "2027-01");
  assert.equal(p.safe_new_monthly, "500.00");
  assert.deepEqual(p.buffer_plan, { shortfall: "3000.00", remaining_gap: "3000.00", balance: "7800.00", covered: true, still_short: "0.00" });
  assert.equal(p.consolidation.reason, "NOT_NEEDED"); // a run of 2, not 3
});

test("UI_28_over_budget_now_pauses_is_still_short_and_can_consolidate", () => {
  // The motorbike (4,000.00 x 12 from Oct): Oct-Dec 7,500.00, Jan-Jun 2027 5,500.00,
  // Jul-Sep 4,000.00. Nine months over in a row.
  scene("over_budget_now");
  const p = plan();
  assert.equal(p.back_in_budget_month, "2027-07");
  assert.equal(p.pause_until, "2027-07");
  assert.equal(p.safe_new_from, "2027-07");
  assert.equal(p.safe_new_monthly, "1000.00"); // Jul-Sep: 5,000.00 - 4,000.00
  // 3 x 2,500.00 + 6 x 500.00 over; 4,800.00 + 4,800.00 saved on the motorbike.
  assert.deepEqual(p.buffer_plan, { shortfall: "10500.00", remaining_gap: "10500.00", balance: "9600.00", covered: false, still_short: "900.00" });
  assert.equal(p.consolidation.reason, "ELIGIBLE");
  // 3 x 2,000.00 + 9 x 1,500.00 + 12 x 4,000.00 left from this month on.
  assert.deepEqual(p.consolidation.estimate, {
    principal: "67500.00",
    annual_rate: "0.18",
    rate_is_example: true,
    rate_note: "example, not a real rate",
    term_months: 24,
    first_due_month: "2026-11",
    monthly_payment: "3369.88",
    total_cost: "80877.12",
    current_remaining_total: "67500.00",
    extra_cost: "13377.12",
    // This month (Oct): 2,000.00 + 1,500.00 + 4,000.00 = 7,500.00, the hero's total,
    // minus 3,369.88 (UI-38; backend AS-11).
    current_monthly_total: "7500.00",
    monthly_reduction: "4130.12",
  });
});

test("UI_28_amortised_payment_matches_the_backend_formula", () => {
  // Python Decimal, backend amortised_payment: exact, rounded UP to the satang.
  const cases: [string, string, number, string][] = [
    ["67500.00", "0.18", 24, "3369.88"],
    ["4.00", "0.06", 1, "4.02"], // exact: must not round up to 4.03 (backend review)
    ["1000.00", "0", 3, "333.34"], // a 0 rate is P / n, rounded up
    ["10000.00", "0.18", 12, "916.80"],
    ["123456.78", "0.075", 36, "3840.28"],
    ["0.01", "0.18", 24, "0.01"],
    ["9999999999.99", "0.18", 24, "499241019.70"],
  ];
  for (const [principal, rate, term, expected] of cases) {
    assert.equal(fromSatang(amortisedPayment(toSatang(principal), rate, term)), expected, `${principal} ${rate} ${term}`);
  }
});

test("UI_28_exactly_the_budget_is_not_over", () => {
  const p = build([debt("2026-10", 6, "5000.00")]);
  assert.equal(p.back_in_budget_month, null);
  assert.equal(p.months[0]?.over_budget, false);
  assert.equal(p.months[0]?.headroom, "0.00");
  assert.equal(p.safe_new_monthly, "0.00");
  const over = build([debt("2026-10", 6, "5000.01")]);
  assert.equal(over.months[0]?.over_budget, true);
  assert.equal(over.months[0]?.headroom, "0.00"); // never negative
  assert.equal(over.pause_until, "2027-04");
});

test("UI_28_a_buffer_of_exactly_the_shortfall_covers_it", () => {
  // Three months 100.00 over: a shortfall of 300.00 (B-UI-68 found no test at the edge).
  const over = [debt("2026-11", 3, "5100.00")];
  const exact = build(over, "20000.00", "5000.00", "300.00").buffer_plan;
  assert.deepEqual(exact, { shortfall: "300.00", remaining_gap: "300.00", balance: "300.00", covered: true, still_short: "0.00" });
  const short = build(over, "20000.00", "5000.00", "299.99").buffer_plan;
  assert.deepEqual(short, { shortfall: "300.00", remaining_gap: "300.00", balance: "299.99", covered: false, still_short: "0.01" });
});

test("UI_28_safe_amount_also_stays_within_a_third_of_income_rounded_down", () => {
  // Budget 10,000.00 is above a third of 10,000.00: the third decides.
  // (10,000.00 - 3 x 1,000.01) / 3 = 2,333.3233..., rounded DOWN to 2,333.32.
  const p = build([debt("2026-10", 12, "1000.01")], "10000.00", "10000.00");
  assert.equal(p.safe_new_monthly, "2333.32");
  // Above a third already: nothing fits, never a negative amount.
  assert.equal(build([debt("2026-10", 12, "4000.00")], "10000.00", "10000.00").safe_new_monthly, "0.00");
});

test("UI_28_safe_window_is_the_smallest_month_of_twelve", () => {
  // Fits 1,500.00 now, but month 12 has a 4,900.00 plan: only 100.00 fits every month.
  const p = build([debt("2026-10", 3, "3500.00"), debt("2027-09", 1, "4900.00")]);
  assert.equal(p.safe_new_from, "2026-10");
  assert.equal(p.safe_new_monthly, "100.00");
  // The 13th month is outside the window.
  assert.equal(build([debt("2026-10", 3, "3500.00"), debt("2027-10", 1, "4900.00")]).safe_new_monthly, "1500.00");
});

test("UI_28_consolidation_needs_three_months_over_in_a_row", () => {
  const over = (first: string, months: number) => debt(first, months, "5100.00");
  assert.equal(build([over("2026-11", 2)]).consolidation.reason, "NOT_NEEDED");
  // Two runs of 2 with a gap are not a run of 3.
  assert.equal(build([over("2026-11", 2), over("2027-02", 2)]).consolidation.reason, "NOT_NEEDED");
  assert.equal(build([over("2026-11", 3)]).consolidation.reason, "ELIGIBLE");
  // Adjacent plans join into one run (backend has_run).
  assert.equal(build([over("2026-11", 2), over("2027-01", 1)]).consolidation.reason, "ELIGIBLE");
});

test("UI_28_consolidation_payment_above_budget_and_too_large", () => {
  // 3 x 30,000.00 = 90,000.00 over 24 months is 4,493.17: within 5,000.00.
  assert.equal(build([debt("2026-10", 3, "30000.00")]).consolidation.reason, "ELIGIBLE");
  // 3 x 40,000.00 = 120,000.00 is 5,990.90 a month: above the budget.
  const above = build([debt("2026-10", 3, "40000.00")]).consolidation;
  assert.deepEqual(above, { eligible: false, reason: "PAYMENT_ABOVE_BUDGET", estimate: null });
  // A principal above Numeric(12,2) is never estimated.
  const big = build([debt("2026-10", 600, "9999999999.99")], "99999999999.99", "100.00").consolidation;
  assert.equal(big.reason, "ESTIMATE_TOO_LARGE");
});

test("UI_28_consolidation_payment_above_one_third_of_income", () => {
  // As the backend's (b), round 1 review F3: the loan must not make a month L65 RED.
  // 90,000.00 over 24 months is 4,493.17 a month (Python Decimal, backend formula),
  // and 3 x 4,493.17 = 13,479.51. Exactly one third of income is not RED.
  const debts = [debt("2026-10", 3, "30000.00")];
  assert.equal(build(debts, "13479.51").consolidation.reason, "ELIGIBLE");
  assert.deepEqual(build(debts, "13479.50").consolidation, { eligible: false, reason: "PAYMENT_ABOVE_ONE_THIRD_OF_INCOME", estimate: null });
});

test("UI_28_months_stop_at_600_and_say_so", () => {
  const p = build([debt("2026-11", 600, "100.00")]);
  assert.equal(p.months.length, 600);
  assert.equal(p.months_truncated, true);
  assert.equal(build([debt("2026-10", 600, "100.00")]).months_truncated, false);
});

test("UI_28_no_settings_is_409", () => {
  resetMock(TODAY);
  assert.equal(call("GET", "/assistant/plan").status, 409);
  assert.equal(call("GET", "/assistant/summary").status, 409);
});

// ---- UI-29: words around the numbers -------------------------------------------------

test("UI_29_monthly_view_lines", () => {
  scene("over_budget_now");
  const lines = planLines(plan());
  assert.equal(lines.back, "กลับมาอยู่ในงบเดือน ก.ค. 2570");
  assert.equal(lines.pauseNow, true);
  assert.equal(lines.safe, "ตอนนี้ยังไม่ควรผ่อนเพิ่ม ตั้งแต่ ก.ค. 2570 ผ่อนเพิ่มได้ไม่เกินเดือนละ 1,000.00 บาท");
  scene("over_budget");
  const later = planLines(plan());
  assert.equal(later.pauseNow, false); // over budget later, not now: no pause line
  assert.equal(later.safe, "ตั้งแต่ ม.ค. 2570 ผ่อนเพิ่มได้ไม่เกินเดือนละ 500.00 บาท");
  scene("persona");
  assert.equal(planLines(plan()).back, "ทุกเดือนอยู่ในงบ");
});

test("UI_29_form_hint_and_nothing_fits", () => {
  assert.equal(formHint(plan()), "ผ่อนเพิ่มได้ไม่เกินเดือนละ 1,500.00 บาท ตั้งแต่ ต.ค. 2569");
  const full = build([debt("2026-10", 6, "5000.00")]);
  assert.equal(formHint(full), "ตั้งแต่ ต.ค. 2569 ยังผ่อนเพิ่มไม่ได้โดยไม่เกินงบ");
  assert.equal(planLines(full).safe, "ตั้งแต่ ต.ค. 2569 ยังผ่อนเพิ่มไม่ได้โดยไม่เกินงบ");
});

test("UI_29_buffer_plan_covered_or_still_short", () => {
  assert.deepEqual(bufferPlanLines({ shortfall: "0.00", remaining_gap: "0.00", balance: "10.00", covered: true, still_short: "0.00" }), {
    tone: "ok",
    lines: ["ทุกเดือนอยู่ในงบ ยังไม่ต้องใช้กันชน"],
  });
  assert.deepEqual(bufferPlanLines({ shortfall: "3000.00", remaining_gap: "3000.00", balance: "3000.00", covered: true, still_short: "0.00" }), {
    tone: "ok",
    lines: ["ค่างวดส่วนที่เกินงบรวมทุกเดือน 3,000.00 บาท", "กันชน 3,000.00 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด"],
  });
  assert.deepEqual(bufferPlanLines({ shortfall: "10500.00", remaining_gap: "10500.00", balance: "9600.00", covered: false, still_short: "900.00" }), {
    tone: "warn",
    lines: ["ค่างวดส่วนที่เกินงบรวมทุกเดือน 10,500.00 บาท", "กันชน 9,600.00 บาท ยังขาดอีก 900.00 บาท"],
  });
});

test("UI_29_rate_shown_as_percent_without_arithmetic", () => {
  for (const [rate, shown] of [
    ["0.18", "18"],
    ["0.075", "7.5"],
    ["0.1", "10"],
    ["0", "0"],
    ["1.5", "150"],
    ["0.0001", "0.01"],
  ]) {
    assert.equal(ratePercent(rate ?? ""), shown, rate);
  }
});

test("UI_29_every_reason_has_plain_words", () => {
  for (const [reason, text] of Object.entries(ASSIST.reason)) {
    if (reason === "ELIGIBLE") continue;
    assert.ok(text.length > 0, reason);
  }
  // The estimate is always labelled an example, and its rate as not real.
  assert.match(ASSIST.exampleTag, /ตัวอย่าง/);
  assert.match(ASSIST.terms(24, "18"), /ไม่ใช่อัตราจริง/);
});

// ---- UI-30: three tabs ------------------------------------------------------------

test("UI_30_three_tabs_and_no_payoff_or_consolidation_screen", () => {
  assert.deepEqual(
    NAV_TABS.map((t) => t.route),
    ["home", "think", "buffer"],
  );
  assert.deepEqual(
    NAV_TABS.filter((t) => t.primary).map((t) => t.route),
    ["think"],
  );
  assert.ok(!(ROUTES as readonly string[]).includes("payoff"));
  assert.ok(!(ROUTES as readonly string[]).includes("consolidate"));
  // ภาระผ่อนรายเดือน belongs to feature 1 (Home); the result to the check.
  assert.ok(navActive("home", "months"));
  assert.ok(navActive("think", "result"));
  assert.ok(!navActive("think", "home"));
  assert.ok(!navActive("buffer", "alerts"));
});

// ---- UI-31: no request on "สนใจรวมหนี้", the mock's summary is the plan's words ---------

test("UI_31_interest_in_consolidation_sends_nothing", () => {
  const src = readFileSync("src/components/AssistantCards.tsx", "utf8");
  const card = src.slice(src.indexOf("export function ConsolidationCard"), src.indexOf("export function AiBubbleCard"));
  assert.ok(card.length > 0 && card.includes("setInterested(true)"));
  for (const banned of ["await", "fetch(", "api.ts", "getAssistant", "post", "POST"]) {
    assert.ok(!card.includes(banned), `ConsolidationCard must not call anything: ${banned}`);
  }
  // The only API the cards import is the summary.
  assert.match(src, /import \{ getAssistantSummary \} from "\.\.\/api\.ts";/);
  assert.equal(ASSIST.bankWillCall, "ธนาคารจะติดต่อกลับเพื่อพิจารณา");
});

test("UI_31_the_mock_summary_is_the_plans_own_words_for_points_1_to_4", () => {
  scene("over_budget_now");
  const out = call("GET", "/assistant/summary").body as AssistantSummaryOut;
  // The mock has no model: it answers as the backend does without a key.
  assert.deepEqual([out.source, out.reason], ["fallback", "no_key"]);
  const p = plan();
  const lines = planLines(p);
  for (const part of [
    lines.back,
    lines.safe,
    ...bufferPlanLines(p.buffer_plan).lines,
    ASSIST.worth,
    "3,369.88 บาท",
    "80,877.12 บาท",
  ]) {
    assert.ok(out.text.includes(part), part);
  }
  scene("persona");
  const calm = (call("GET", "/assistant/summary").body as AssistantSummaryOut).text;
  // The same words as Home's banner: not needed, then why.
  assert.ok(calm.includes(ASSIST.notNeeded));
  assert.ok(calm.includes(ASSIST.reason.NOT_NEEDED));
});
