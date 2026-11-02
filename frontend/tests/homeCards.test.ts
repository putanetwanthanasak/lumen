/**
 * Home's cards as drawn, rendered with react-dom/server (no browser, no extra package):
 * UI-38: the bank's offer card. A white card with a solid blue header band; one
 *   benefit line from the API's monthly_reduction, never worked out on screen and
 *   left out at 0.00; each total as large as its monthly amount; the extra-cost line
 *   and the old top line gone.
 * UI-35 (markup): every tinted card that meets the page carries its EDGE, so it stands
 *   out from the page at least 3:1 (contrast.test.ts measures the colours): on Home,
 *   and the buffer screen's balance card, the same wallet.
 * UI-42 (markup): the hero is one card: a chevron, a bar with the budget marked, one
 *   warning line and one buffer line with its link; no inner box, no month chips, no total.
 * UI-43: the installments list: where each one is in its plan, from GET /debts/months
 *   (on main since #39), and the paid-off ones folded into one line.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ACCENT, EDGE, FILL, SOLID } from "../src/accent.ts";
import type { AssistantPlanOut, BufferOut, ConsolidationOut, DebtSummary, MonthsOut, SettingsOut, ShortfallsOut } from "../src/api-types.ts";
import { ConsolidationCard } from "../src/components/AssistantCards.tsx";
import { ASSIST, HOME } from "../src/copy.ts";
import { consolidationView } from "../src/homeLayout.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { MoneyFormatError } from "../src/money.ts";
import { BufferBody } from "../src/screens/Buffer.tsx";
import { HomeBody } from "../src/screens/Home.tsx";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

/** The plan's consolidation in the over_budget_now scene: offered (UI-28). */
function offered(): ConsolidationOut {
  scene("over_budget_now");
  const c = (call("GET", "/assistant/plan").body as AssistantPlanOut).consolidation;
  assert.ok(c.estimate !== null);
  return c;
}

function card(c: ConsolidationOut): string {
  return renderToStaticMarkup(createElement(ConsolidationCard, { view: consolidationView(c) }));
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
  const html = card(c);
  // One line at body size; its last phrase moves down whole, never split after "กลับ".
  const benefit = paragraphs(html).filter((p) => p.text.startsWith("ค่างวดลดลง"));
  assert.deepEqual(benefit, [{ cls: "text-body text-pretty text-ink", text: "ค่างวดลดลงเดือนละ 4,130.12 บาท ทุกเดือนกลับมาอยู่ในงบ" }]);
  assert.ok(html.includes('ค่างวดลดลงเดือนละ 4,130.12 บาท <span class="whitespace-nowrap">ทุกเดือนกลับมาอยู่ในงบ</span></p>'));
  // The screen shows the API's number, never its own: a value no subtraction gives.
  assert.ok(c.estimate !== null);
  const odd = card({ ...c, estimate: { ...c.estimate, monthly_reduction: "1.23" } });
  assert.ok(paragraphs(odd).some((p) => p.text === "ค่างวดลดลงเดือนละ 1.23 บาท ทุกเดือนกลับมาอยู่ในงบ"));
  assert.ok(!odd.includes("4,130.12"));
});

test("UI_38_no_benefit_line_unless_the_reduction_is_above_zero", () => {
  const c = offered();
  assert.ok(c.estimate !== null);
  const at = (reduction: string) => consolidationView({ ...c, estimate: { ...c.estimate!, monthly_reduction: reduction } });
  const zero = at("0.00");
  assert.ok(zero.kind === "offer" && zero.benefit === null);
  assert.ok(!card({ ...c, estimate: { ...c.estimate, monthly_reduction: "0.00" } }).includes("ค่างวดลดลง"));
  const satang = at("0.01");
  assert.ok(satang.kind === "offer" && satang.benefit === "ค่างวดลดลงเดือนละ 0.01 บาท ทุกเดือนกลับมาอยู่ในงบ");
  // Not an API money string: an error, never a guessed line (as formatBaht).
  assert.throws(() => at("-5.00"), MoneyFormatError);
});

test("UI_38_each_total_is_as_large_as_its_monthly_amount", () => {
  const html = card(offered());
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
  const html = card(offered());
  assert.ok(!html.includes("จ่ายรวมมากกว่าแผนเดิม"), "the extra-cost line");
  assert.ok(!html.includes("13,377.12"), "its amount");
  assert.ok(!html.includes("รวมหนี้อาจช่วยให้ทุกเดือนกลับมาอยู่ในงบ"), "the old top line");
  assert.equal("extraCost" in ASSIST, false);
});

test("UI_38_the_offer_is_a_white_card_with_a_solid_blue_header_band", () => {
  const html = card(offered());
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

/** Home as drawn in a scene, from the mock's answers (the screen's own loads; `change` edits the summary). */
function homeIn(name: string, change?: (summary: DebtSummary) => void): string {
  scene(name);
  const summary = call("GET", "/debts/summary").body as DebtSummary;
  change?.(summary);
  return renderToStaticMarkup(
    createElement(HomeBody, {
      settings: call("GET", "/settings").body as SettingsOut,
      summary,
      buffer: call("GET", "/buffer").body as BufferOut,
      months: call("GET", "/debts/months").body as MonthsOut,
      plan: call("GET", "/assistant/plan").body as AssistantPlanOut,
      shortfalls: call("GET", "/buffer/shortfalls").body as ShortfallsOut,
    }),
  );
}

test("UI_35_every_tinted_card_on_home_carries_its_edge", () => {
  // The tint of each card that meets the page, and the edge it must have.
  const cards = [
    { name: "buffer", tint: ACCENT.buffer.tint, edge: EDGE.buffer }, // the wallet, in every scene
    { name: "ai", tint: ACCENT.ai.tint, edge: EDGE.ai },
    { name: "quiet", tint: ACCENT.quiet.tint, edge: EDGE.quiet },
  ];
  const expected: Record<string, string[]> = {
    persona: ["buffer", "ai", "quiet"], // in budget: the banner
    over_budget: ["buffer", "ai", "quiet"], // upcoming months over: the hero says so, still the banner
    over_budget_now: ["buffer", "ai", "offer"], // the offer card instead of the banner
    over_budget_empty_buffer: ["buffer", "ai", "quiet"], // as over_budget, the wallet empty: it keeps its edge
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
    const html = renderToStaticMarkup(createElement(BufferBody, {
        buffer: call("GET", "/buffer").body as BufferOut,
        shortfalls: call("GET", "/buffer/shortfalls").body as ShortfallsOut,
        onMoved: () => undefined,
      }));
    // The balance card is the screen's tinted section; its edge is the wallet's on Home.
    const cards = [...html.matchAll(/<section class="([^"]*)">/g)].map((m) => new Set(tokens(m[1] ?? ""))).filter((c) => hasAll(c, ACCENT.buffer.tint));
    assert.equal(cards.length, 1, name);
    assert.ok(hasAll(cards[0] ?? new Set(), EDGE.buffer), `${name}: ${[...(cards[0] ?? [])].join(" ")}`);
    assert.ok(!cards[0]?.has(tokens(ACCENT.buffer.line)[0] ?? ""), "not the old light line");
  }
});

// ---- UI-42 (markup): the hero, one card -------------------------------------------------

/** The hero's markup: the first card on Home, the one that is `relative` for its stretched button. */
function heroOf(html: string): string {
  const found = /<section class="relative [^"]*">[\s\S]*?<\/section>/.exec(html)?.[0];
  assert.ok(found !== undefined, "the hero card");
  return found;
}

const NEXT = 'd="m9 18 6-6-6-6"'; // the chevron's path (Icon.tsx "next")

test("UI_42_the_hero_is_one_card_with_a_chevron_and_the_whole_card_opens_the_months", () => {
  for (const name of ["persona", "over_budget", "over_budget_now", "over_budget_empty_buffer"]) {
    const hero = heroOf(homeIn(name));
    // One card: nothing inside it has a border, a shadow or a tint of its own (the old strip had all three).
    const inside = elements(hero.replace(/^<section[^>]*>/, ""));
    const boxed = inside.filter((e) => [...e.classes].some((c) => /^(border|rounded-field|shadow)|^bg-warn-bg$/.test(c)));
    assert.deepEqual(boxed, [], name);
    // The chevron at the top right replaces "ดูทุกเดือน ›"; its words stay for screen readers.
    assert.ok(hero.includes(NEXT), `${name}: the chevron`);
    assert.ok(hero.includes(`<span class="sr-only">${HOME.seeAllMonths}</span>`), name);
    assert.ok(!hero.includes("ดูทุกเดือน ›"), name);
    // The whole card is the button: its ::after covers the card, which it is positioned in.
    const main = /^<section class="([^"]*)"><button type="button" class="([^"]*)"/.exec(hero);
    assert.ok(main !== null, `${name}: the card opens with its button`);
    assert.ok(tokens(main[1] ?? "").includes("relative"), name);
    assert.ok(hasAll(new Set(tokens(main[2] ?? "")), "after:absolute after:inset-0"), name);
  }
});

/** The bar's parts: the green, the amber and the red (if any), the budget mark, with their style. */
function barOf(hero: string): { green: string; amber: string | null; red: string | null; mark: string } {
  const bar = /<span class="relative my-1 block h-3 [^"]*" role="presentation">(.*?)<\/span><\/span>(?:<\/span>)?/.exec(hero)?.[1] ?? "";
  const style = (cls: string) => new RegExp(`<span class="[^"]*\\b${cls}\\b[^"]*" style="([^"]*)"`).exec(bar)?.[1] ?? null;
  return { green: style("bg-bar-ok") ?? "", amber: style("bg-bar-over"), red: style("bg-bar-risk"), mark: style("bg-ink") ?? "" };
}

test("UI_42_UI_52_the_bar_marks_the_budget_and_colours_only_the_part_above_it", () => {
  // In budget: 3,500.00 of 5,000.00, on the budget's scale: green to 70%, the mark at the end.
  assert.deepEqual(barOf(heroOf(homeIn("persona"))), { green: "left:0%;width:70%", amber: null, red: null, mark: "left:100%" });
  // Over: 7,500.00 against 5,000.00, on the total's scale: green to the budget (5,000 / 7,500
  // is 666 per mille, rounded down), the gap only from there on. October is also over one
  // third of income, so the gap is red, not amber (UI-52).
  assert.deepEqual(barOf(heroOf(homeIn("over_budget_now"))), {
    green: "left:0%;width:66.6%",
    amber: null,
    red: "left:66.6%;width:33.4%",
    mark: "left:66.6%",
  });
});

test("UI_42_UI_46_one_warning_line_and_one_buffer_line_with_its_button_and_no_chips_or_total", () => {
  const html = homeIn("over_budget_now");
  const hero = heroOf(html);
  const text = hero.replace(/<[^>]+>/g, "|");
  // The one warning line, once on all of Home, each month held to its year; the old lines and the strip are gone.
  const warning = '<span>เกินงบ 9 เดือน (<span class="whitespace-nowrap">ต.ค. 2569</span> ถึง <span class="whitespace-nowrap">มิ.ย. 2570</span>)</span>';
  assert.equal(html.split(warning).length - 1, 1);
  assert.equal(html.replace(/<[^>]+>/g, "").split("เกินงบ 9 เดือน (ต.ค. 2569 ถึง มิ.ย. 2570)").length - 1, 1);
  for (const gone of ["เดือนนี้ค่างวดรวมเกินงบที่ตั้งไว้", "เดือนที่ค่างวดรวมเกินงบ", "รวมทุกเดือน", "+2,500.00", "หลังจากนั้น", "ดูภาระผ่อนรายเดือน"]) {
    assert.ok(!html.includes(gone), gone);
  }
  // One buffer line (UI-46): the first month over and its state, then the button in the
  // buffer's colour, in a positioned box after the card's own button, so above its cover.
  const plain = (h: string) => h.replace(/<[^>]+>/g, "");
  assert.ok(plain(hero).includes("ต.ค. 2569 เกินงบ 2,500.00 บาท"));
  const button = /<div class="relative"><button type="button"[^>]*? class="([^"]*)">.*?ใช้กันชนจ่ายส่วนที่เกิน<\/button><\/div>/.exec(hero);
  assert.ok(button !== null, "the button");
  assert.ok(hasAll(new Set(tokens(button[1] ?? "")), FILL.buffer), button[1]);
  assert.ok(hero.indexOf("ใช้กันชนจ่ายส่วนที่เกิน") > hero.indexOf("</button>"));
  // Every number in the card is an API string, formatted: this month's total and the budget.
  assert.ok(text.includes("|7,500.00 บาท|") && text.includes("|จากงบ 5,000.00 บาท|"));
  // Months over later: the first of them. An empty buffer keeps the line, without the button.
  assert.ok(plain(heroOf(homeIn("over_budget"))).includes("พ.ย. 2569 เกินงบ 1,500.00 บาท"));
  const empty = heroOf(homeIn("over_budget_empty_buffer"));
  assert.ok(plain(empty).includes("พ.ย. 2569 เกินงบ 1,500.00 บาท") && !empty.includes("ใช้กันชนจ่ายส่วนที่เกิน"), "no button");
  // In budget: the status line only.
  const calm = heroOf(homeIn("persona")).replace(/<[^>]+>/g, "|");
  assert.ok(calm.includes("|เดือนนี้และอีก 8 เดือนอยู่ในงบ|") && !calm.includes("เกินงบ"));
});

// ---- UI-43: the installments list ----------------------------------------------------------

/** The installments section: the last card on Home. */
const installmentsOf = (html: string) => /<section class="[^"]*border border-line[^"]*">[\s\S]*<\/section>$/.exec(html)?.[0] ?? "";

/** A row's line as drawn: each part whole, a line breaking only at the dot. */
const parts = (...text: string[]) => text.map((t) => `<span class="whitespace-nowrap">${t}</span>`).join(" · ");

test("UI_43_each_counted_row_says_which_instalment_of_how_many_and_when_it_ends", () => {
  const list = installmentsOf(homeIn("persona"));
  // หูฟังไร้สาย: 6 months from Jul 2026, so Oct is the 4th and Dec the last. ตู้เย็น: 10 from Sep 2026.
  assert.ok(list.includes(`>${parts("งวดที่ 4 จาก 6", "หมด ธ.ค. 2569")}</span>`), list);
  assert.ok(list.includes(`>${parts("งวดที่ 2 จาก 10", "หมด มิ.ย. 2570")}</span>`), list);
  assert.ok(!list.includes("ผ่อน 6 เดือน") && !list.includes("ผ่อน 10 เดือน"), "the old line");
  // One that starts after this month says when it starts, never "งวดที่ 1" as if due now.
  const later = installmentsOf(homeIn("over_budget"));
  assert.ok(later.includes(`>${parts("เริ่ม พ.ย. 2569", "หมด ส.ค. 2570")}</span>`), later);
});

test("UI_43_paid_off_installments_fold_into_one_line_that_opens_to_their_names", () => {
  const list = installmentsOf(homeIn("persona"));
  // The heading is gone; one button with the count and the chevron, closed.
  assert.ok(!list.includes(HOME.notCounted));
  const toggle = /<button type="button" aria-expanded="false" aria-controls="([^"]+)" class="[^"]*\bmin-h-11\b[^"]*">ผ่อนครบแล้ว 1 รายการ<svg[^>]*>(.*?)<\/svg><\/button>/.exec(list);
  assert.ok(toggle !== null, "the folded line");
  assert.ok((toggle[2] ?? "").includes(NEXT), "its chevron");
  // What it opens: the names only, each with a check, no amounts.
  const opened = new RegExp(`<ul id="${toggle[1]}" hidden="" class="[^"]*">(.*?)</ul>`).exec(list)?.[1] ?? "";
  assert.ok(opened.includes(">กระเป๋าเป้</span>"), opened);
  assert.equal(opened.split('d="M20 6 9 17l-5-5"').length - 1, 1, "a check"); // Icon.tsx "check"
  assert.ok(!opened.includes("บาท") && !opened.includes("งวด"), "the name only");
  // Paid off rows no longer show under the counted ones.
  assert.equal(list.split("กระเป๋าเป้").length - 1, 1);
});

test("UI_43_a_cancelled_line_stays_apart_never_under_paid_off", () => {
  // Cancelled is not finished: it keeps its own group and its label (L59(3)).
  const html = homeIn("persona", (summary) => {
    const line = summary.installments[0];
    assert.ok(line !== undefined);
    Object.assign(line, { status: "cancelled", owed: false });
  });
  const list = installmentsOf(html);
  assert.ok(list.includes(`>${HOME.notCounted}</h3>`));
  assert.ok(list.includes("ยกเลิกแล้ว"));
  assert.ok(list.includes(">ผ่อนครบแล้ว 1 รายการ<"), "only the paid-off one is folded");
});
