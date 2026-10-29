/**
 * The result's month bars (DESIGN.md section 5.4), rendered with react-dom/server:
 * UI-40: bars, labels and the budget line share one grid of equal whole-pixel slots; a
 *   label for every month up to 12, beyond that every k-th from the first, so none
 *   clips or touches the next (Chrome measures both in scripts/month-labels-check.mjs);
 *   solid fills, no hatch and no
 *   hollow part; a ⚠ above every bar over one third of income; the new item's share is
 *   the top of each bar in its month's status colour, everything else one grey below a
 *   2px white gap; the legend shows only what the chart has: the grey, then "ชิ้นใหม่:"
 *   and the statuses its months have, each swatch the colour it names.
 * UI-41 (result): one plain line under the bars says how many months are over budget
 *   and from when to when. The verdict card holds the warning; nothing else repeats it.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { ManualEntryIn, MonthRow, PreviewOut } from "../src/api-types.ts";
import { KeepMonths } from "../src/components/ui.tsx";
import { labelStep, MonthBars, plotColumns } from "../src/components/Verdict.tsx";
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
/** The bars, in order: their class and style, and the parts that paint them (empty divs, top first). */
const barsOf = (inner: string) =>
  [...inner.matchAll(/<div class="relative row-start-1 ([^"]*)" style="([^"]*)">((?:<div [^>]*><\/div>)*)/g)].map((m) => ({
    cls: m[1] ?? "",
    style: m[2] ?? "",
    parts: [...(m[3] ?? "").matchAll(/<div class="([^"]*)"(?: style="([^"]*)")?><\/div>/g)].map((p): [string, string] => [p[1] ?? "", p[2] ?? ""]),
  }));
/** The month labels: their style and text, in order. */
const labelsOf = (inner: string) =>
  [...inner.matchAll(/<span class="row-start-2 ([^"]*)" style="([^"]*)">([^<]*)<\/span>/g)].map((m) => ({ cls: m[1] ?? "", style: m[2] ?? "", text: m[3] ?? "" }));

const ALERT = 'd="M12 3 2 20h20L12 3Zm0 6v5m0 3.5v.5"'; // Icon.tsx "alert"

type Entry = { swatch: string; alert: boolean; text: string };

/**
 * The legend's rows in order, each its label ("" for none) and its entries: an entry's
 * swatch (one empty square, or why not), whether it has the ⚠, and its words.
 */
function legendOf(html: string): { label: string; entries: Entry[] }[] {
  const m = /<div class="flex flex-col gap-1 text-caption text-ink-muted" aria-hidden="true">(.*?)<table class="sr-only">/.exec(html);
  assert.ok(m !== null, "the legend");
  return [...(m[1] ?? "").matchAll(/(?:<span class="[^"]*">([^<]*)<\/span>)?<ul class="flex flex-wrap gap-x-4 gap-y-1">(.*?)<\/ul>/g)].map((row) => ({
    label: row[1] ?? "",
    entries: [...(row[2] ?? "").matchAll(/<li class="flex items-center gap-1\.5">(.*?)<\/li>/g)].map((e) => {
      const inner = e[1] ?? "";
      const swatch = /^<span class="([^"]*)"><\/span>/.exec(inner)?.[1] ?? `not one empty square: ${inner}`;
      return { swatch, alert: inner.includes(ALERT), text: inner.replace(/<[^>]+>/g, "") };
    }),
  }));
}
/** The legend's words, one array per row: its label, then its entries. */
const legendWords = (html: string) => legendOf(html).map((row) => [row.label, ...row.entries.map((e) => e.text)]);

const GREY = "bg-bar-existing";
const GAP = "border-t-2 border-card"; // the grey part's top edge: the 2px white gap
/** Whether a part is hollow or white: no bar colour, a white or clear fill, or any outline but the gap. */
const hollow = (cls: string) => {
  const rest = cls.replace(GAP, "");
  return !/\bbg-bar-/.test(rest) || /\bbg-(card|white|transparent)\b|\bborder\b/.test(rest);
};

test("UI_40_bars_labels_and_the_budget_line_share_one_grid_of_equal_columns", () => {
  const plot = plotOf(bars(same(10, ["3000.00", false, false])));
  // A slot per month, in whole pixels: Chrome draws a bar's edges on whole pixels, so
  // with 318 / 12 = 26.5px slots alternate bars rounded 1px apart. No wider than leaves
  // 12px from each end bar's centre to the plot's edge, for its label. The spare pixels
  // go to a side column at each end.
  assert.equal(
    plot.style,
    "grid-template-columns:minmax(0, 1fr) repeat(10, round(down, min(100% / 10, (100% - 24px) / 9) + 0.25px / 10, 1px)) minmax(0, 1fr)",
  );
  assert.equal(plotColumns(1), "minmax(0, 1fr) repeat(1, round(down, 100% + 0.25px / 1, 1px)) minmax(0, 1fr)");
  assert.ok(plotColumns(36).includes("repeat(36, round(down, "), plotColumns(36));
  // Beyond 36 months a slot is under 10px: the exact share, so the spare is not a tenth of the plot.
  assert.equal(plotColumns(37), "minmax(0, 1fr) repeat(37, min(100% / 37, (100% - 24px) / 36)) minmax(0, 1fr)");
  // The budget line spans every column, the side ones too, drawn first, behind the bars: at the top when
  // the budget is the largest value (the scale), lower when a month is above it.
  const line = '<div class="col-span-full row-start-1 self-end border-t-2 border-dashed border-ink-muted" style="height:';
  assert.ok(plot.inner.startsWith(`${line}100%">`), plot.inner.slice(0, 160));
  assert.ok(plotOf(bars(rows([["7500.00", true, true]]))).inner.startsWith(`${line}66.6%">`));
  // Month i in column i + 2, after the side column; each label in its own bar's column,
  // centred, on one line, at 11px.
  assert.deepEqual(
    barsOf(plot.inner).map((b) => /grid-column:(\d+)/.exec(b.style)?.[1]),
    ["2", "3", "4", "5", "6", "7", "8", "9", "10", "11"],
  );
  const labels = labelsOf(plot.inner);
  assert.deepEqual(
    labels.map((l) => [/grid-column:(\d+)/.exec(l.style)?.[1], l.text]),
    [["2", "พ.ย."], ["3", "ธ.ค."], ["4", "ม.ค."], ["5", "ก.พ."], ["6", "มี.ค."], ["7", "เม.ย."], ["8", "พ.ค."], ["9", "มิ.ย."], ["10", "ก.ค."], ["11", "ส.ค."]],
  );
  for (const l of labels) {
    assert.ok(["justify-self-center", "whitespace-nowrap", "text-axis"].every((c) => l.cls.split(" ").includes(c)), l.cls);
    // Plain: no bold or amber label for a month over budget (the bar's colour says it).
    assert.ok(!/font-bold|warn/.test(l.cls), l.cls);
  }
});

test("UI_40_every_month_has_a_label_up_to_12_months_and_every_kth_from_the_first_beyond", () => {
  // At 11px the widest label is 22.7px and a slot is 24px at 360px, so 12 fit; beyond 12
  // months, every k-th month, k = ceil(months / 12), starting with the first.
  const cases: [number, number][] = [[1, 1], [6, 1], [10, 1], [12, 1], [13, 2], [24, 2], [36, 3], [600, 50]];
  for (const [n, k] of cases) {
    assert.equal(labelStep(n), k, `${n} months`);
    const labels = labelsOf(plotOf(bars(same(n, ["3000.00", false, false]))).inner);
    // The month each label is under (its column, less the side column and 1).
    const under = labels.map((l) => Number(/grid-column:(\d+)/.exec(l.style)?.[1]) - 2);
    const every = Array.from({ length: n }, (_, i) => i).filter((i) => i % k === 0);
    assert.deepEqual(under, every, `${n} months, every ${k}`);
    assert.equal(under[0], 0, `${n} months: the first month is labelled`);
    assert.equal(labels[0]?.text, "พ.ย.", `${n} months`);
  }
  // Every term the API allows (1 to 600): at most 12 labels, with the smallest step that
  // keeps it so, and every month labelled up to 12.
  for (let n = 1; n <= 600; n += 1) {
    const k = labelStep(n);
    const shown = Array.from({ length: n }, (_, i) => i).filter((i) => i % k === 0).length;
    assert.ok(shown <= 12, `${n} months, every ${k}: ${shown} labels`);
    if (n <= 12) assert.equal(shown, n, `${n} months`);
    else assert.ok(Array.from({ length: n }, (_, i) => i).filter((i) => i % (k - 1) === 0).length > 12, `${n} months: every ${k - 1} would do`);
  }
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
  // With no item, each bar is one part, wholly its month's status colour (no grey: the colour is all there is to say).
  assert.deepEqual(
    drawn.map((b) => b.parts),
    ["bg-bar-ok", "bg-bar-over", "bg-bar-risk", "bg-bar-risk", "bg-bar-ok"].map((bg) => [[`rounded-t-md ${bg}`, "height:100%"]]),
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

test("UI_40_the_new_items_share_takes_its_months_status_colour_above_one_grey_and_a_white_gap", () => {
  const months = rows([
    ["6500.00", true, false],
    ["4500.00", false, false],
    ["7500.00", true, true],
    ["4500.00", false, true], // over a third while in budget (a budget above a third of income): red wins
    ["3000.00", false, false], // nothing else due that month: the share is the whole bar
    ["3000.01", false, false], // one satang else: a grey sliver, still under its gap
  ]);
  const html = bars(months, "3000.00");
  const drawn = barsOf(plotOf(html).inner);
  // The share's colour is its month's status, from the API's flags; everything else is the
  // same grey on every bar, whatever the status, its top edge the 2px white gap. Each share's
  // height is its part of that month's bar: 3,000 of 6,500, of 4,500, ... (per mille, rounded down).
  assert.deepEqual(
    drawn.map((b) => b.parts),
    [
      [["rounded-t-md bg-bar-over", "height:46.1%"], [`flex-1 ${GAP} ${GREY}`, ""]],
      [["rounded-t-md bg-bar-ok", "height:66.6%"], [`flex-1 ${GAP} ${GREY}`, ""]],
      [["rounded-t-md bg-bar-risk", "height:40%"], [`flex-1 ${GAP} ${GREY}`, ""]],
      [["rounded-t-md bg-bar-risk", "height:66.6%"], [`flex-1 ${GAP} ${GREY}`, ""]],
      [["rounded-t-md bg-bar-ok", "height:100%"]],
      [["rounded-t-md bg-bar-ok", "height:99.9%"], [`flex-1 ${GAP} ${GREY}`, ""]],
    ],
  );
  // Nothing hollow or white: every part is a solid bar colour, and the gap is the only edge.
  assert.deepEqual(drawn.flatMap((b) => b.parts.filter(([cls]) => hollow(cls))), []);
  assert.ok(!/\bbg-(card|white)\b|\bborder-2\b|border-bar-/.test(plotOf(html).inner), "no white fill and no outline in the plot");
  // The bar itself paints nothing: its parts do, so no other colour shows at their edges.
  assert.ok(drawn.every((b) => !/\bbg-/.test(b.cls)), drawn.map((b) => b.cls).join(" | "));
  // Without an item (no candidate): no grey part and no part entries.
  const none = bars(months);
  assert.ok(!none.includes(GREY) && !none.includes("ชิ้นใหม่") && !none.includes("ค่างวดที่มีอยู่"));
});

test("UI_40_the_legend_shows_only_the_statuses_and_the_parts_this_chart_has", () => {
  const ok: [string, boolean, boolean] = ["4500.00", false, false];
  const over: [string, boolean, boolean] = ["6500.00", true, false];
  const red: [string, boolean, boolean] = ["7500.00", true, true];
  const words = (months: MonthRow[], candidate: string | null) => legendWords(bars(months, candidate));
  // In budget only: the grey, then "ชิ้นใหม่:" with the green entry alone, and no ⚠ anywhere.
  const green = bars(rows([ok, ok]), "3000.00");
  assert.deepEqual(legendWords(green), [["", "ค่างวดที่มีอยู่"], ["ชิ้นใหม่:", "อยู่ในงบ"]]);
  assert.ok(!green.includes(ALERT));
  // Over budget, none over a third: no red entry.
  assert.deepEqual(words(rows([over, ok]), "3000.00"), [["", "ค่างวดที่มีอยู่"], ["ชิ้นใหม่:", "อยู่ในงบ", "เกินงบ"]]);
  // Every month over budget: no green entry.
  assert.deepEqual(words(rows([over, over]), "3000.00"), [["", "ค่างวดที่มีอยู่"], ["ชิ้นใหม่:", "เกินงบ"]]);
  // A month over a third: its entry carries the ⚠, in the same order as ever, whatever the months' order.
  assert.deepEqual(
    legendOf(bars(rows([red, over, ok]), "3000.00")).map((row) => [row.label, ...row.entries.map((e) => [e.text, e.alert])]),
    [
      ["", ["ค่างวดที่มีอยู่", false]],
      ["ชิ้นใหม่:", ["อยู่ในงบ", false], ["เกินงบ", false], ["เกินเกณฑ์ที่ ธปท. แนะนำ", true]],
    ],
  );
  // Nothing else due in the term (each total is the item alone): no grey part, so no "ค่างวดที่มีอยู่".
  const alone: [string, boolean, boolean] = ["3000.00", false, false];
  assert.deepEqual(words(rows([alone, alone]), "3000.00"), [["ชิ้นใหม่:", "อยู่ในงบ"]]);
  // One satang of something else in one month is enough.
  assert.deepEqual(words(rows([alone, ["3000.01", false, false]]), "3000.00"), [["", "ค่างวดที่มีอยู่"], ["ชิ้นใหม่:", "อยู่ในงบ"]]);
  // No item: the statuses only, the colours of whole bars, with no "ชิ้นใหม่:".
  assert.deepEqual(words(rows([ok, over]), null), [["", "อยู่ในงบ", "เกินงบ"]]);
});

test("UI_40_each_legend_swatch_is_one_solid_square_in_the_colour_it_names_on_the_bars", () => {
  const months = rows([["4500.00", false, false], ["6500.00", true, false], ["7500.00", true, true]]);
  const html = bars(months, "3000.00");
  // One empty square each, never a two-colour mini bar, never hollow: the grey of the
  // existing part, then the status colours of the new item's share.
  assert.deepEqual(
    legendOf(html).map((row) => [row.label, ...row.entries.map((e) => [e.text, e.swatch])]),
    [
      ["", ["ค่างวดที่มีอยู่", `inline-block h-3 w-3 rounded-sm ${GREY}`]],
      [
        "ชิ้นใหม่:",
        ["อยู่ในงบ", "inline-block h-3 w-3 rounded-sm bg-bar-ok"],
        ["เกินงบ", "inline-block h-3 w-3 rounded-sm bg-bar-over"],
        ["เกินเกณฑ์ที่ ธปท. แนะนำ", "inline-block h-3 w-3 rounded-sm bg-bar-risk"],
      ],
    ],
  );
  // Each swatch is the very colour it names on the bars: the grey is each bar's lower
  // part, and the statuses, in month order here, are the shares' colours.
  const fill = (cls: string) => cls.split(" ").find((c) => c.startsWith("bg-"));
  const [existing, statuses] = legendOf(html);
  const drawn = barsOf(plotOf(html).inner);
  const grey = fill(existing?.entries[0]?.swatch ?? "");
  assert.deepEqual(drawn.map((b) => fill(b.parts[1]?.[0] ?? "")), [grey, grey, grey]);
  assert.deepEqual(drawn.map((b) => fill(b.parts[0]?.[0] ?? "")), statuses?.entries.map((e) => fill(e.swatch)));
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
