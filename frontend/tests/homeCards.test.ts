/**
 * Home's cards as drawn, rendered with react-dom/server (no browser, no extra package):
 * UI-38: the bank's offer card. A white card with a solid blue header band; one
 *   benefit line from the API's monthly_reduction (TODO(backend), mock only), never
 *   worked out on screen and left out at 0.00; each total as large as its monthly
 *   amount; the extra-cost line and the old top line gone.
 * UI-35 (markup): every tinted card that meets the page carries its EDGE, so it stands
 *   out from the page at least 3:1 (contrast.test.ts measures the colours): on Home,
 *   and the buffer screen's balance card, the same wallet.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ACCENT, EDGE, SOLID } from "../src/accent.ts";
import type { AssistantPlanOut, BufferOut, ConsolidationOut, DebtSummary, MonthsOut, SettingsOut } from "../src/api-types.ts";
import { ConsolidationCard } from "../src/components/AssistantCards.tsx";
import { ASSIST } from "../src/copy.ts";
import { consolidationView } from "../src/homeLayout.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { MoneyFormatError } from "../src/money.ts";
import { BufferBody } from "../src/screens/Buffer.tsx";
import { HomeBody } from "../src/screens/Home.tsx";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mint");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

/** The plan's consolidation in the over_budget_now scene: offered (UI-28). */
function offered(): ConsolidationOut {
  scene("over_budget_now");
  const c = (call("GET", "/assistant/plan").body as AssistantPlanOut).consolidation;
  assert.ok(c.estimate !== null);
  return c;
}

const monthlyTotal = () => (call("GET", "/debts/summary").body as DebtSummary).monthly_total;

function card(c: ConsolidationOut, currentMonthly: string): string {
  return renderToStaticMarkup(createElement(ConsolidationCard, { view: consolidationView(c, currentMonthly) }));
}

/** Every element's opening tag: its class list and the text right after it. */
function elements(html: string): { classes: Set<string>; text: string }[] {
  return [...html.matchAll(/<[a-z0-9]+\b[^>]*\bclass="([^"]*)"[^>]*>([^<]*)/g)].map((m) => ({
    classes: new Set((m[1] ?? "").split(/\s+/)),
    text: m[2] ?? "",
  }));
}

const tokens = (cls: string) => cls.split(/\s+/);
const hasAll = (classes: Set<string>, cls: string) => tokens(cls).every((c) => classes.has(c));
/** The paragraphs of the markup: their class list and their text, tags removed. */
function paragraphs(html: string): { cls: string; text: string }[] {
  return [...html.matchAll(/<p class="([^"]*)">(.*?)<\/p>/g)].map((m) => ({ cls: m[1] ?? "", text: (m[2] ?? "").replace(/<[^>]+>/g, "") }));
}

/** The class list of the element whose own text is exactly `text`. */
function classOf(html: string, text: string): string[] {
  const found = elements(html).filter((e) => e.text === text);
  assert.equal(found.length, 1, `one element with the text ${text}`);
  return [...(found[0]?.classes ?? [])].sort();
}

test("UI_38_monthly_reduction_comes_from_the_api_and_the_card_shows_it_as_is", () => {
  const c = offered();
  // Worked out by hand, not by the mock: 2,000.00 + 1,500.00 + 4,000.00 a month
  // replaced, minus the loan's 3,369.88 (UI-28).
  assert.equal(c.estimate?.monthly_reduction, "4130.12");
  const html = card(c, monthlyTotal());
  // One line at body size; its last phrase moves down whole, never split after "กลับ".
  const benefit = paragraphs(html).filter((p) => p.text.startsWith("ค่างวดลดลง"));
  assert.deepEqual(benefit, [{ cls: "text-body text-pretty text-ink", text: "ค่างวดลดลงเดือนละ 4,130.12 บาท ทุกเดือนกลับมาอยู่ในงบ" }]);
  assert.ok(html.includes('ค่างวดลดลงเดือนละ 4,130.12 บาท <span class="whitespace-nowrap">ทุกเดือนกลับมาอยู่ในงบ</span></p>'));
  // The screen shows the API's number, never its own: a value no subtraction gives.
  assert.ok(c.estimate !== null);
  const odd = card({ ...c, estimate: { ...c.estimate, monthly_reduction: "1.23" } }, monthlyTotal());
  assert.ok(paragraphs(odd).some((p) => p.text === "ค่างวดลดลงเดือนละ 1.23 บาท ทุกเดือนกลับมาอยู่ในงบ"));
  assert.ok(!odd.includes("4,130.12"));
});

test("UI_38_no_benefit_line_unless_the_reduction_is_above_zero", () => {
  const c = offered();
  assert.ok(c.estimate !== null);
  const at = (reduction: string) => consolidationView({ ...c, estimate: { ...c.estimate!, monthly_reduction: reduction } }, "7500.00");
  const zero = at("0.00");
  assert.ok(zero.kind === "offer" && zero.benefit === null);
  assert.ok(!card({ ...c, estimate: { ...c.estimate, monthly_reduction: "0.00" } }, "7500.00").includes("ค่างวดลดลง"));
  const satang = at("0.01");
  assert.ok(satang.kind === "offer" && satang.benefit === "ค่างวดลดลงเดือนละ 0.01 บาท ทุกเดือนกลับมาอยู่ในงบ");
  // Not an API money string: an error, never a guessed line (as formatBaht).
  assert.throws(() => at("-5.00"), MoneyFormatError);
});

test("UI_38_each_total_is_as_large_as_its_monthly_amount", () => {
  const html = card(offered(), monthlyTotal());
  // Now: 7,500.00 a month, 67,500.00 left; consolidated: 3,369.88 a month, 80,877.12.
  const amounts = ["7,500.00 บาท", "67,500.00 บาท", "3,369.88 บาท", "80,877.12 บาท"].map((text) => classOf(html, text));
  for (const cls of amounts) assert.deepEqual(cls, amounts[0]);
  assert.ok(amounts[0]?.includes("text-lead") && amounts[0].includes("font-bold"), String(amounts[0]));
  // Both columns keep their "ยอดรวมทั้งหมด", the example tag and the 18% note.
  assert.equal(html.split(`>${ASSIST.totalAll}</span>`).length - 1, 2);
  assert.ok(html.includes(`>${ASSIST.exampleTag}</span>`));
  assert.ok(paragraphs(html).some((p) => p.text === "ผ่อน 24 เดือน ดอกเบี้ยสมมติ 18% ต่อปี (ไม่ใช่อัตราจริง)"));
  assert.ok(html.includes('<span class="whitespace-nowrap">(ไม่ใช่อัตราจริง)</span></p>'), "the note stays whole");
});

test("UI_38_the_extra_cost_line_and_the_old_top_line_are_gone", () => {
  const html = card(offered(), monthlyTotal());
  assert.ok(!html.includes("จ่ายรวมมากกว่าแผนเดิม"), "the extra-cost line");
  assert.ok(!html.includes("13,377.12"), "its amount");
  assert.ok(!html.includes("รวมหนี้อาจช่วยให้ทุกเดือนกลับมาอยู่ในงบ"), "the old top line");
  assert.equal("extraCost" in ASSIST, false);
});

test("UI_38_the_offer_is_a_white_card_with_a_solid_blue_header_band", () => {
  const html = card(offered(), monthlyTotal());
  const section = /^<section class="([^"]*)">/.exec(html)?.[1];
  assert.ok(section !== undefined, html.slice(0, 120));
  // Framed in blue; the blue behind the band is the card's own (no pale corner hairline).
  const own = new Set(tokens(section));
  assert.ok(own.has("overflow-hidden") && hasAll(own, EDGE.bank) && hasAll(own, SOLID.bank), section);
  // The band comes first: the white title with the bank icon, on that blue.
  const band = /^<section[^>]*><div class="([^"]*)"><h2 class="([^"]*)"><svg[^>]*>.*?<\/svg>([^<]*)<\/h2>/.exec(html);
  assert.ok(band !== null, "the header band");
  assert.ok(!tokens(band[1] ?? "").some((c) => c.startsWith("bg-")), `the band shows the card's blue: ${band[1]}`);
  assert.equal(band[3], "ทางเลือกจากธนาคาร");
  // No colour of its own (text-lead is its size): white, from the card.
  const colour = /^text-(ink|white|bank|leaf|teal|ai|quiet|warn|ok|risk|info)\b/;
  assert.ok(!tokens(band[2] ?? "").some((c) => colour.test(c)), `white, from the card: ${band[2]}`);
  assert.ok(colour.test("text-bank-800") && !colour.test("text-lead"), "the pattern tells a colour from a size");
  // The body after it is white, with ink text; the two comparison boxes stay light blue on it.
  const body = /^<section[^>]*><div[^>]*>.*?<\/div><div class="([^"]*)">/.exec(html)?.[1];
  assert.ok(body !== undefined && hasAll(new Set(tokens(body)), "bg-card text-ink"), body);
  const boxes = elements(html).filter((e) => e.classes.has("rounded-field") && e.classes.has(tokens(ACCENT.bank.tint)[0] ?? ""));
  assert.equal(boxes.length, 2);
});

/** Home as drawn in a scene, from the mock's answers (the screen's own loads). */
function homeIn(name: string): string {
  scene(name);
  return renderToStaticMarkup(
    createElement(HomeBody, {
      settings: call("GET", "/settings").body as SettingsOut,
      summary: call("GET", "/debts/summary").body as DebtSummary,
      buffer: call("GET", "/buffer").body as BufferOut,
      upcoming: call("GET", "/debts/months?count=6").body as MonthsOut,
      plan: call("GET", "/assistant/plan").body as AssistantPlanOut,
    }),
  );
}

test("UI_35_every_tinted_card_on_home_carries_its_edge", () => {
  // The tint of each card that meets the page, and the edge it must have.
  const cards = [
    { name: "buffer", tint: ACCENT.buffer.tint, edge: EDGE.buffer }, // the wallet, in every scene
    { name: "ai", tint: ACCENT.ai.tint, edge: EDGE.ai },
    { name: "quiet", tint: ACCENT.quiet.tint, edge: EDGE.quiet },
    { name: "warn", tint: ACCENT.warn.tint, edge: EDGE.warn },
  ];
  const expected: Record<string, string[]> = {
    persona: ["buffer", "ai", "quiet"], // in budget: the banner, no strip
    over_budget: ["buffer", "ai", "quiet", "warn"], // upcoming months over: the strip, still the banner
    over_budget_now: ["buffer", "ai", "warn", "offer"], // the offer card instead of the banner
    over_budget_empty_buffer: ["buffer", "ai", "quiet", "warn"], // as over_budget, the wallet empty: it keeps its edge
  };
  for (const [name, wanted] of Object.entries(expected)) {
    const all = elements(homeIn(name));
    const seen = cards.flatMap((c) => {
      const tinted = all.filter((e) => hasAll(e.classes, c.tint));
      for (const e of tinted) assert.ok(hasAll(e.classes, c.edge), `${name}: ${c.name} without ${c.edge}: ${[...e.classes].join(" ")}`);
      return tinted.length > 0 ? [c.name] : [];
    });
    const offers = all.filter((e) => hasAll(e.classes, SOLID.bank) && hasAll(e.classes, EDGE.bank));
    assert.deepEqual([...seen, ...(offers.length > 0 ? ["offer"] : [])], wanted, name);
  }
});

test("UI_35_the_buffer_screens_balance_card_carries_the_wallets_edge", () => {
  for (const name of ["persona", "over_budget_empty_buffer"]) {
    scene(name);
    const html = renderToStaticMarkup(createElement(BufferBody, { buffer: call("GET", "/buffer").body as BufferOut, onMoved: () => undefined }));
    // The balance card is the screen's tinted section; its edge is the wallet's on Home.
    const cards = [...html.matchAll(/<section class="([^"]*)">/g)].map((m) => new Set(tokens(m[1] ?? ""))).filter((c) => hasAll(c, ACCENT.buffer.tint));
    assert.equal(cards.length, 1, name);
    assert.ok(hasAll(cards[0] ?? new Set(), EDGE.buffer), `${name}: ${[...(cards[0] ?? [])].join(" ")}`);
    assert.ok(!cards[0]?.has(tokens(ACCENT.buffer.line)[0] ?? ""), "not the old light line");
  }
});
