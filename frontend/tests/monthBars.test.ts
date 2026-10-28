/**
 * The result's month bars (DESIGN.md section 5.4), rendered with react-dom/server:
 * UI-40: bars, labels and the budget line share one grid of equal columns; a label
 *   every k-th month, so none clips or touches the next; solid fills, no hatch; a ⚠
 *   above every bar over one third of income; this item's share is the pale top of
 *   each bar, with its own legend entry.
 * UI-41 (result): one plain line under the bars says how many months are over budget
 *   and from when to when. The verdict card holds the warning; nothing else repeats it.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ManualEntryIn, MonthRow, PreviewOut } from "../src/api-types.ts";
import { KeepMonths } from "../src/components/ui.tsx";
import { labelStep, MonthBars } from "../src/components/Verdict.tsx";
import { THINK } from "../src/copy.ts";
import { PERSONA_SETTINGS, SCENARIOS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { Result } from "../src/screens/Result.tsx";
import { addMonths, THAI_MONTHS } from "../src/thaiMonth.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026: a plan starts in Nov
beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

const BUDGET = "5000.00";

/** `n` months from Nov 2026, each [total, over budget, over one third]. */
function rows(totals: [string, boolean, boolean][]): MonthRow[] {
  return totals.map(([total, over_budget, over_one_third], i) => ({ month: addMonths("2026-11", i), total, over_budget, over_one_third }));
}
const same = (n: number, row: [string, boolean, boolean]) => rows(Array.from({ length: n }, () => row));
/** The words a reader sees: the tags removed (the screen-reader table too). */
const plain = (html: string) => html.replace(/<table class="sr-only">.*?<\/table>/, "").replace(/<[^>]+>/g, "");

function bars(months: MonthRow[], candidate: string | null = null): string {
  return renderToStaticMarkup(createElement(MonthBars, { months, budget: BUDGET, candidate }));
}

/** The plot: the grid with the bars and the labels. */
function plotOf(html: string): { style: string; inner: string } {
  const m = /<div class="grid grid-rows-\[10rem_auto\] pt-6" style="([^"]*)" aria-hidden="true">(.*?)<\/div><p /.exec(html);
  assert.ok(m !== null, "the plot");
  return { style: m[1] ?? "", inner: m[2] ?? "" };
}
/** The bars: their class and style, in order. */
const barsOf = (inner: string) =>
  [...inner.matchAll(/<div class="relative row-start-1 ([^"]*)" style="([^"]*)">/g)].map((m) => ({ cls: m[1] ?? "", style: m[2] ?? "" }));
/** The month labels: their style and text, in order. */
const labelsOf = (inner: string) =>
  [...inner.matchAll(/<span class="row-start-2 ([^"]*)" style="([^"]*)">([^<]*)<\/span>/g)].map((m) => ({ cls: m[1] ?? "", style: m[2] ?? "", text: m[3] ?? "" }));

const ALERT = 'd="M12 3 2 20h20L12 3Zm0 6v5m0 3.5v.5"'; // Icon.tsx "alert"

test("UI_40_bars_labels_and_the_budget_line_share_one_grid_of_equal_columns", () => {
  const plot = plotOf(bars(same(10, ["3000.00", false, false])));
  assert.equal(plot.style, "grid-template-columns:repeat(10, minmax(0, 1fr))");
  // The budget line spans every column, drawn first, behind the bars: at the top when
  // the budget is the largest value (the scale), lower when a month is above it.
  const line = '<div class="col-span-full row-start-1 self-end border-t-2 border-dashed border-ink-muted" style="height:';
  assert.ok(plot.inner.startsWith(`${line}100%">`), plot.inner.slice(0, 160));
  assert.ok(plotOf(bars(rows([["7500.00", true, true]]))).inner.startsWith(`${line}66.6%">`));
  // Bar i in column i; each label in its own bar's column, centred, on one line.
  assert.deepEqual(
    barsOf(plot.inner).map((b) => /grid-column:(\d+)/.exec(b.style)?.[1]),
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
  );
  const labels = labelsOf(plot.inner);
  assert.deepEqual(
    labels.map((l) => [/grid-column:(\d+)/.exec(l.style)?.[1], l.text]),
    [["1", "พ.ย."], ["3", "ม.ค."], ["5", "มี.ค."], ["7", "พ.ค."], ["9", "ก.ค."]],
  );
  for (const l of labels) {
    assert.ok(l.cls.split(" ").includes("justify-self-center") && l.cls.split(" ").includes("whitespace-nowrap"), l.cls);
    // Plain: no bold or amber label for a month over budget (the bar's colour says it).
    assert.ok(!/font-bold|warn/.test(l.cls), l.cls);
  }
});

test("UI_40_a_label_every_kth_month_leaves_room_between_labels_at_370px", () => {
  // In the 370px frame the plot is 298px wide (measured in Chrome); the widest Thai month
  // label at 14px is 29px in Noto Sans Thai, 34px allowing for other system fonts. So
  // label centres must be at least 42px apart: k columns of 298 / n px each.
  for (let n = 1; n <= 600; n += 1) {
    const k = labelStep(n);
    assert.ok(k >= 1, `${n}`);
    assert.ok(k * 298 >= 42 * n, `${n} months, every ${k}: too close`);
    const shown = (n - 1 - ((n - 1) % k)) / k + 1; // labels at 0, k, 2k, ... (integers)
    assert.ok(n <= 7 ? shown === n : shown >= 4 && shown <= 7, `${n} months: ${shown} labels`);
  }
  assert.deepEqual([1, 7, 8, 12, 24, 36].map(labelStep), [1, 1, 2, 2, 4, 6]);
});

test("UI_40_bars_are_solid_and_a_marker_sits_above_each_bar_over_one_third", () => {
  const months = rows([
    ["4000.00", false, false],
    ["6500.00", true, false],
    ["7500.00", true, true],
    ["7500.00", true, true],
    ["3000.00", false, false],
  ]);
  const html = bars(months);
  // No hatch anywhere, no tinted column behind a bar.
  assert.ok(!/repeating-linear-gradient|background-image/.test(html));
  const drawn = barsOf(plotOf(html).inner);
  assert.deepEqual(
    drawn.map((b) => b.cls.split(" ").find((c) => c.startsWith("bg-"))),
    ["bg-bar-ok", "bg-bar-over", "bg-bar-risk", "bg-bar-risk", "bg-bar-ok"],
  );
  // One ⚠ per bar over one third, inside that bar; one more in the legend.
  const inner = plotOf(html).inner;
  assert.equal(inner.split(ALERT).length - 1, 2);
  assert.equal(html.split(ALERT).length - 1, 3);
  // Each bar's own height from the API's totals, on the largest total's scale.
  assert.deepEqual(
    drawn.map((b) => /height:([\d.]+%)/.exec(b.style)?.[1]),
    ["53.3%", "86.6%", "100%", "100%", "40%"],
  );
});

test("UI_40_this_items_share_is_the_pale_top_of_each_bar_with_its_own_legend_entry", () => {
  const months = rows([
    ["6500.00", true, false],
    ["4500.00", false, false],
    ["7500.00", true, true],
  ]);
  const html = bars(months, "3000.00");
  const shares = [...plotOf(html).inner.matchAll(/<div class="shrink-0 rounded-t-md border-2 border-b-0 ([^"]*)" style="height:([\d.]+%)"><\/div>/g)].map(
    (m) => [m[1], m[2]],
  );
  // Its height is its share of that month's bar: 3,000 of 6,500, of 4,500, of 7,500 (per mille, rounded down).
  assert.deepEqual(shares, [
    ["border-bar-over bg-warn-bg", "46.1%"],
    ["border-bar-ok bg-leaf-100", "66.6%"],
    ["border-bar-risk bg-risk-bg", "40%"],
  ]);
  assert.ok(html.includes(`${THINK.legendCandidate}</li>`));
  // Without an item (no candidate), no pale top and no legend entry.
  const none = bars(months);
  assert.ok(!none.includes("border-b-0") && !none.includes(THINK.legendCandidate));
});

test("UI_41_the_line_under_the_bars_is_plain_and_says_from_when_to_when", () => {
  const html = bars(rows([["4000.00", false, false], ["6500.00", true, false], ["6500.00", true, false], ["3000.00", false, false]]));
  const line = /<p class="([^"]*)">(เกินงบ.*?)<\/p>/.exec(html);
  assert.ok(line !== null, "the line");
  assert.deepEqual([line[1], plain(line[2] ?? "")], ["text-body text-ink", "เกินงบ 2 เดือน: ธ.ค. 2569 ถึง ม.ค. 2570"]);
  // No icon in it, and a month never splits from its year at a line break.
  assert.ok(!(line[2] ?? "").includes("<svg"));
  assert.deepEqual([...(line[2] ?? "").matchAll(/<span class="whitespace-nowrap">([^<]*)<\/span>/g)].map((m) => m[1]), ["ธ.ค. 2569", "ม.ค. 2570"]);
  assert.ok(!html.includes("เดือนที่เกินงบ"), "the old list of months");
  // Every month in budget: no line at all.
  assert.ok(!bars(same(3, ["3000.00", false, false])).includes("เกินงบ "));
});

function verdictFor(scene: keyof typeof SCENARIOS): { entry: ManualEntryIn; verdict: PreviewOut } {
  const entry: ManualEntryIn = { client_request_id: `r-${scene}`, kind: "purchase", first_due_month: "2026-11", platform_name: null, ...SCENARIOS[scene] };
  const res = handle("POST", "/installments/preview", entry, "demo-mon");
  assert.equal(res.status, 200);
  return { entry, verdict: res.body as PreviewOut };
}

test("UI_41_the_result_says_each_fact_once", () => {
  for (const [scene, line, last] of [
    // The laptop from Nov: Nov and Dec at 6,500.00.
    ["YELLOW", "เกินงบ 2 เดือน: พ.ย. 2569 ถึง ธ.ค. 2569", "ธ.ค. 2569"],
    // The motorbike from Nov: 7,500.00 to Dec, 5,500.00 to Jun.
    ["RED", "เกินงบ 8 เดือน: พ.ย. 2569 ถึง มิ.ย. 2570", "มิ.ย. 2570"],
  ] as const) {
    const { entry, verdict } = verdictFor(scene);
    const html = renderToStaticMarkup(createElement(Result, { entry, verdict, budget: PERSONA_SETTINGS.monthly_installment_budget }));
    // The verdict card is the one warning: the one status, the one box framed in amber or red.
    assert.equal(html.split('role="status"').length - 1, 1, scene);
    assert.ok(!html.includes('role="alert"'), `${scene}: no other warning box`);
    assert.equal(html.match(/\bborder-(warn|risk)-line\b/g)?.length, 1, scene);
    // The months over budget are said once in words (the table is for screen readers only),
    // in the plain line under the bars.
    const seen = plain(html);
    assert.equal(seen.split(line).length - 1, 1, `${scene}: ${line}`);
    assert.equal(seen.split(last).length - 1, 1, `${scene}: ${last} named once`);
  }
});

test("UI_41_keep_months_holds_each_month_to_its_year_and_leaves_other_text_alone", () => {
  const render = (text: string) => renderToStaticMarkup(createElement(KeepMonths, { text }));
  const all = THAI_MONTHS.map((m) => `${m} 2570`).join(" ถึง ");
  const kept = [...render(all).matchAll(/<span class="whitespace-nowrap">([^<]*)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(kept, THAI_MONTHS.map((m) => `${m} 2570`));
  assert.equal(plain(render(all)), all, "the words unchanged");
  // No month in it: the text as it is, no span.
  assert.equal(render("กันชนพอจ่ายส่วนที่เกิน"), "กันชนพอจ่ายส่วนที่เกิน");
  // A month without its year, or a number that is not a year, stays as it is.
  assert.equal(render("ม.ค. ถึง 25 บาท"), "ม.ค. ถึง 25 บาท");
});
