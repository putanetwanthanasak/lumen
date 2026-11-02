/**
 * A month's bar shows what the buffer covered (Session 20, DESIGN.md section 7.2b):
 * UI-52 (critical): barSegments draws ok up to the budget, teal for what was moved for
 *   the month (never past the shortfall), and the API's remaining_gap at the end, amber
 *   or red over one third of income. The parts always touch and end at the total.
 * UI-53: Home's bar is this month's own shortfall row, never the first month over budget.
 * UI-54: the months screen's chip and bar for each state; the ธปท. chip and a red ring
 *   stay while a month is over one third of income, even when the buffer covered it.
 * UI-55: the prepared line says the money was moved (ย้าย) and that the user still pays
 *   in the app; never "โอน", never "จ่ายแล้ว", no em dash.
 * UI-56: on the mock, a new installment in a prepared month makes it partly prepared:
 *   the gap is amber again and "ใช้กันชนจ่ายส่วนที่เกิน" comes back.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { BUFFER_BAR, BUFFER_CHIP } from "../src/accent.ts";
import type {
  AssistantPlanOut,
  BufferOut,
  DebtSummary,
  ManualEntryIn,
  MonthDetail,
  MonthsOut,
  PreparedState,
  SettingsOut,
  ShortfallMonth,
  ShortfallsOut,
} from "../src/api-types.ts";
import { barSegments, type Segment } from "../src/barSegments.ts";
import { shortfallsByMonth, shortfallView } from "../src/bufferState.ts";
import { BUFFER_STATE, MONTHS_VIEW } from "../src/copy.ts";
import { heroView } from "../src/homeLayout.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { fromSatang } from "../src/mock/satang.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { barPermille, toSatang, type Money } from "../src/money.ts";
import { HomeBody } from "../src/screens/Home.tsx";
import { MonthList } from "../src/screens/Months.tsx";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
const plain = (html: string) => html.replace(/<[^>]+>/g, "");
const move = (id: string, amount: Money, forMonth: string) =>
  assert.equal(call("POST", "/buffer/move-to-main", { client_request_id: id, amount, for_month: forMonth }).status, 201);

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

const BUDGET = "5000.00";

/** A shortfall row as the API sends it; the derived fields are worked out here, in the test. */
function row(total: Money, prepared: Money, state?: PreparedState, gap?: Money): ShortfallMonth {
  const shortfall = toSatang(total) - toSatang(BUDGET);
  const moved = toSatang(prepared);
  const remaining = shortfall > moved ? shortfall - moved : 0n;
  return {
    month: "2026-11",
    total,
    budget: BUDGET,
    shortfall: fromSatang(shortfall),
    prepared,
    remaining_gap: gap ?? fromSatang(remaining),
    state: state ?? (moved === 0n ? "not_prepared" : remaining === 0n ? "prepared" : "partly_prepared"),
    covered_by_buffer: "0.00",
    still_short: "0.00",
  };
}

/** The API's over_budget flag, as L65 defines it (total above the budget). */
const overOf = (total: Money) => toSatang(total) > toSatang(BUDGET);
const bar = (total: Money, r: ShortfallMonth | null, scale: Money = total, overOneThird = false) =>
  barSegments({ total, budget: BUDGET, scale, row: r, overBudget: overOf(total), overOneThird });

/** [kind, from, to] of each part, for short assertions. */
const shape = (segments: Segment[]) => segments.map((s): [string, number, number] => [s.kind, s.from, s.to]);

/** The parts touch with no gap or overlap, from 0 to the total, and none runs backwards. */
function assertContiguous(segments: Segment[], total: Money, scale: Money): void {
  assert.equal(segments[0]?.from, 0);
  for (const [i, s] of segments.entries()) {
    assert.ok(s.from <= s.to, `${s.kind} runs backwards: ${s.from} > ${s.to}`);
    const next = segments[i + 1];
    if (next !== undefined) assert.equal(s.to, next.from, `${s.kind} -> ${next.kind}`);
  }
  assert.equal(segments.at(-1)?.to, barPermille(total, scale));
}

// ---- UI-52 (critical): barSegments ----------------------------------------------------

test("UI_52_within_budget_is_one_green_part_as_long_as_the_total", () => {
  const parts = bar("3500.00", null, BUDGET);
  assert.deepEqual(shape(parts), [["ok", 0, 700]]);
  assert.equal(parts[0]?.className, "bg-bar-ok");
  // Exactly the budget is within it (L65): still all green, to the end.
  assert.deepEqual(shape(bar(BUDGET, null)), [["ok", 0, 1000]]);
});

test("UI_52_over_budget_and_nothing_moved_is_green_to_the_budget_then_the_gap", () => {
  // 5,000 / 6,500 is 769 per mille, rounded down.
  const parts = bar("6500.00", row("6500.00", "0.00"));
  assert.deepEqual(shape(parts), [
    ["ok", 0, 769],
    ["gap", 769, 1000],
  ]);
  assert.equal(parts[1]?.className, "bg-bar-over");
  // Without the shortfalls answer, the same: never a teal part it cannot show.
  assert.deepEqual(shape(bar("6500.00", null)), shape(parts));
});

test("UI_52_partly_prepared_is_green_then_teal_then_the_apis_gap_at_the_end", () => {
  // 600 moved of 1,500: the gap is 900, 138 per mille of 6,500, at the end of the bar.
  const parts = bar("6500.00", row("6500.00", "600.00"));
  assert.deepEqual(shape(parts), [
    ["ok", 0, 769],
    ["buffer", 769, 862],
    ["gap", 862, 1000],
  ]);
  assert.deepEqual(
    parts.map((s) => s.className),
    ["bg-bar-ok", BUFFER_BAR, "bg-bar-over"],
  );
});

test("UI_52_prepared_is_green_then_teal_to_the_end", () => {
  const parts = bar("6500.00", row("6500.00", "1500.00"));
  assert.deepEqual(shape(parts), [
    ["ok", 0, 769],
    ["buffer", 769, 1000],
  ]);
  assert.equal(parts[1]?.className, BUFFER_BAR);
  // Moved more than the shortfall: the teal is capped at the shortfall, the bar at the total.
  assert.deepEqual(shape(bar("6500.00", row("6500.00", "2000.00"))), shape(parts));
});

test("UI_52_over_one_third_the_gap_is_red_and_prepared_draws_the_same_parts", () => {
  // 7,500 is over 20,000 / 3. The gap left is red; a prepared month has no gap to colour.
  const partly = bar("7500.00", row("7500.00", "1000.00"), "7500.00", true);
  assert.deepEqual(
    partly.map((s) => [s.kind, s.className]),
    [
      ["ok", "bg-bar-ok"],
      ["buffer", BUFFER_BAR],
      ["gap", "bg-bar-risk"],
    ],
  );
  const prepared = bar("7500.00", row("7500.00", "2500.00"), "7500.00", true);
  assert.deepEqual(shape(prepared), shape(bar("7500.00", row("7500.00", "2500.00"))));
  assert.ok(prepared.every((s) => s.className !== "bg-bar-risk"));
  // Nothing moved: the whole part over the budget is red.
  assert.equal(bar("7500.00", row("7500.00", "0.00"), "7500.00", true)[1]?.className, "bg-bar-risk");
});

test("UI_52_a_tiny_move_never_starts_the_teal_after_it_ends", () => {
  // 0.01 of a 1,500.00 shortfall on a shared scale of 7,000: the gap's 214 per mille takes
  // the bar back to the budget mark exactly, so the teal is zero wide, never negative.
  const parts = bar("6500.00", row("6500.00", "0.01"), "7000.00");
  assert.deepEqual(shape(parts), [
    ["ok", 0, 714],
    ["buffer", 714, 714],
    ["gap", 714, 928],
  ]);
  assertContiguous(parts, "6500.00", "7000.00");
  // A gap the API should never send (more than the shortfall) is held at the budget mark.
  const held = bar("6500.00", row("6500.00", "0.01", "partly_prepared", "2000.00"));
  assert.deepEqual(shape(held), [
    ["ok", 0, 769],
    ["buffer", 769, 769],
    ["gap", 769, 1000],
  ]);
});

test("UI_52_partly_prepared_with_no_gap_left_is_drawn_as_prepared", () => {
  // The API never sends this; drawn as prepared, and no crash.
  const odd = bar("6500.00", row("6500.00", "1500.00", "partly_prepared", "0.00"));
  assert.deepEqual(shape(odd), shape(bar("6500.00", row("6500.00", "1500.00"))));
});

test("UI_52_every_state_on_every_scale_touches_and_ends_at_the_total", () => {
  // A sweep (no generator package): totals over and under the budget, moves from a satang
  // to past the shortfall, the bar's own scale and a shared larger one.
  const totals = ["4999.99", "5000.00", "5000.01", "5333.33", "6500.00", "7777.77", "12345.67"];
  const moves = ["0.00", "0.01", "0.99", "1.00", "333.33", "600.00", "1499.99", "1500.00", "7345.66", "7345.67", "9000.00"];
  let checked = 0;
  for (const total of totals) {
    const over = toSatang(total) > toSatang(BUDGET);
    for (const prepared of moves) {
      for (const scale of [total, "13000.00", "99999.99"]) {
        for (const overOneThird of [false, true]) {
          const parts = bar(total, over ? row(total, prepared) : null, scale, overOneThird);
          assertContiguous(parts, total, scale);
          if (!over) {
            assert.deepEqual(parts.map((s) => s.kind), ["ok"]);
            assert.equal(parts[0]?.className, overOneThird ? "bg-bar-risk" : "bg-bar-ok");
            continue;
          }
          assert.equal(parts[0]?.to, barPermille(BUDGET, scale), "green ends at the budget");
          const state = row(total, prepared).state;
          const kinds = { not_prepared: ["ok", "gap"], partly_prepared: ["ok", "buffer", "gap"], prepared: ["ok", "buffer"] }[state];
          assert.deepEqual(parts.map((s) => s.kind), kinds, `${total} ${prepared} ${state}`);
          checked += 1;
        }
      }
    }
  }
  assert.ok(checked > 200, `${checked} cases`);
});

// ---- UI-53: Home's bar is this month's -----------------------------------------------

/** Home's bar: its parts' classes, in order. */
function homeBar(): string[] {
  const html = renderToStaticMarkup(
    createElement(HomeBody, {
      settings: call("GET", "/settings").body as SettingsOut,
      summary: call("GET", "/debts/summary").body as DebtSummary,
      buffer: call("GET", "/buffer").body as BufferOut,
      months: call("GET", "/debts/months").body as MonthsOut,
      plan: call("GET", "/assistant/plan").body as AssistantPlanOut,
      shortfalls: call("GET", "/buffer/shortfalls").body as ShortfallsOut,
    }),
  );
  const track = /<span class="relative my-1 block h-3 [^"]*" role="presentation">(.*?)<\/span><\/span>/.exec(html)?.[1] ?? "";
  return [...track.matchAll(/<span class="absolute inset-y-0 (bg-[a-z0-9-]+)/g)].map((m) => m[1] ?? "");
}

const hero = () => heroView((call("GET", "/debts/months").body as MonthsOut).months, call("GET", "/buffer/shortfalls").body as ShortfallsOut);

test("UI_53_home_uses_this_months_row_not_the_first_month_over_budget", () => {
  // Oct to Jun over budget (Oct 7,500.00, over one third). Prepare a later month, Nov.
  scene("over_budget_now");
  move("nov", "2500.00", "2026-11");
  const later = hero();
  assert.equal(later?.month, "2026-10");
  assert.deepEqual([later?.barRow?.month, later?.barRow?.state], ["2026-10", "not_prepared"]);
  assert.deepEqual(homeBar(), ["bg-bar-ok", "bg-bar-risk"]);
  // Now this month: its bar turns teal, while Nov's state is unchanged.
  move("oct", "2500.00", "2026-10");
  assert.equal(hero()?.barRow?.state, "prepared");
  assert.deepEqual(homeBar(), ["bg-bar-ok", BUFFER_BAR]);
});

test("UI_53_this_month_in_budget_has_no_row_even_when_a_later_month_is_prepared", () => {
  // Oct in budget, Nov and Dec over. Nov prepared: the line names Nov, the bar is Oct's, all green.
  scene("over_budget");
  move("nov", "1500.00", "2026-11");
  const view = hero();
  assert.equal(view?.barRow, null);
  assert.equal(view?.buffer?.state, "prepared"); // the line, unchanged: its own month
  assert.deepEqual(homeBar(), ["bg-bar-ok"]);
});

// ---- UI-54: the months screen's chip and bar ------------------------------------------

function month(m: string, total: Money, overOneThird = false): MonthDetail {
  const over = toSatang(total) > toSatang(BUDGET);
  return {
    month: m,
    total,
    over_budget: over,
    over_one_third: overOneThird,
    budget: BUDGET,
    over_by: over ? fromSatang(toSatang(total) - toSatang(BUDGET)) : "0.00",
    installments: [],
  };
}

type Card = { chip: string; chipClass: string; ring: boolean; parts: string[]; text: string };

/** Each month's card: its chip's words and class, whether the bar has the red ring, its parts. */
function cards(months: MonthDetail[], rows: ShortfallMonth[], balance: Money = "9000.00"): Card[] {
  const out: ShortfallsOut = {
    balance,
    shortfall: "0.00",
    remaining_gap: "0.00",
    covered: true,
    still_short: "0.00",
    months: rows,
    months_truncated: false,
  };
  const html = renderToStaticMarkup(createElement(MonthList, { months, budget: BUDGET, buffer: shortfallsByMonth(out) }));
  return [...html.matchAll(/<li class="overflow-hidden[^"]*">(.*?)<\/li>(?=<li class="overflow-hidden|<\/ul>$)/g)].map((m) => {
    const card = m[1] ?? "";
    const chip = /<span class="inline-flex items-center gap-1 rounded-pill px-2\.5 py-0\.5 text-caption font-semibold ([^"]*)">(.*?)<\/span>/.exec(card);
    const track = /<span class="relative block h-3 rounded-pill bg-leaf-50([^"]*)" role="presentation">(.*?)<\/span><\/span>/.exec(card);
    return {
      chip: plain(chip?.[2] ?? ""),
      chipClass: chip?.[1] ?? "",
      ring: (track?.[1] ?? "").includes("ring-bar-risk"),
      parts: [...(track?.[2] ?? "").matchAll(/<span class="absolute inset-y-0 (bg-[a-z0-9-]+)/g)].map((p) => p[1] ?? ""),
      text: plain(card),
    };
  });
}

const at = (m: string, r: ShortfallMonth): ShortfallMonth => ({ ...r, month: m });

test("UI_54_each_state_has_its_chip_and_its_bar_colours", () => {
  const got = cards(
    [month("2026-10", "3500.00"), month("2026-11", "6500.00"), month("2026-12", "6500.00"), month("2027-01", "6500.00")],
    [at("2026-11", row("6500.00", "0.00")), at("2026-12", row("6500.00", "600.00")), at("2027-01", row("6500.00", "1500.00"))],
  );
  assert.deepEqual(
    got.map((c) => [c.chip, c.chipClass, c.ring, c.parts]),
    [
      [MONTHS_VIEW.ok, "bg-ok-bg text-ok-ink", false, ["bg-bar-ok"]],
      [MONTHS_VIEW.over, "bg-warn-bg text-warn-ink", false, ["bg-bar-ok", "bg-bar-over"]],
      // Partly prepared is still over budget: the amber chip, and the gap left in amber.
      [MONTHS_VIEW.over, "bg-warn-bg text-warn-ink", false, ["bg-bar-ok", BUFFER_BAR, "bg-bar-over"]],
      // Prepared: the buffer's own chip, with its shield, and no amber at all.
      [MONTHS_VIEW.bufferReady, BUFFER_CHIP, false, ["bg-bar-ok", BUFFER_BAR]],
    ],
  );
  assert.equal(MONTHS_VIEW.bufferReady, "กันชนเตรียมเงินแล้ว");
  assert.ok(got[1]?.text.includes(BUFFER_STATE.use) && got[2]?.text.includes(BUFFER_STATE.use));
  assert.ok(!got[3]?.text.includes(BUFFER_STATE.use), "no button once prepared");
});

test("UI_54_over_one_third_keeps_its_chip_and_a_red_ring_even_when_prepared", () => {
  const got = cards(
    [month("2026-11", "7500.00", true), month("2026-12", "7500.00", true), month("2027-01", "7500.00", true)],
    [at("2026-11", row("7500.00", "0.00")), at("2026-12", row("7500.00", "1000.00")), at("2027-01", row("7500.00", "2500.00"))],
  );
  assert.deepEqual(
    got.map((c) => [c.chip, c.chipClass, c.ring, c.parts]),
    [
      [MONTHS_VIEW.risk, "bg-risk-bg text-risk-ink", true, ["bg-bar-ok", "bg-bar-risk"]],
      [MONTHS_VIEW.risk, "bg-risk-bg text-risk-ink", true, ["bg-bar-ok", BUFFER_BAR, "bg-bar-risk"]],
      // The buffer covers the payment, not the burden on income: the month never looks safe.
      [MONTHS_VIEW.risk, "bg-risk-bg text-risk-ink", true, ["bg-bar-ok", BUFFER_BAR]],
    ],
  );
  // The line under it still says the buffer prepared it.
  assert.ok(got[2]?.text.includes("ย้ายจากกันชนเข้าบัญชีหลักแล้ว"));
});

test("UI_54_within_budget_but_over_one_third_is_red_with_its_chip_and_ring", () => {
  // A budget above a third of income is allowed (L64): 4,500.00 is within 5,000.00 yet over
  // a third of 12,000.00. Nothing is over budget, so the whole bar is the red level, as before.
  const got = cards([month("2026-11", "4500.00", true)], []);
  assert.deepEqual(
    got.map((c) => [c.chip, c.chipClass, c.ring, c.parts]),
    [[MONTHS_VIEW.risk, "bg-risk-bg text-risk-ink", true, ["bg-bar-risk"]]],
  );
});

// ---- UI-55: the prepared line ---------------------------------------------------------

test("UI_55_the_prepared_line_says_moved_and_to_pay_in_the_app_and_never_paid", () => {
  const line = BUFFER_STATE.prepared("พ.ย. 2569", "1,500.00 บาท");
  assert.equal(line, "พ.ย. 2569 เกินงบ 1,500.00 บาท ย้ายจากกันชนเข้าบัญชีหลักแล้ว อย่าลืมจ่ายค่างวดในแอปผ่อน");
  // As the screens show it, from an API row.
  const shown = shortfallView(row("6500.00", "1500.00"), "0.00").line;
  assert.deepEqual([shown.accent, shown.icon, shown.text], ["buffer", "check", line]);
  for (const text of [line, MONTHS_VIEW.bufferReady]) {
    assert.doesNotMatch(text, /โอน/, text);
    assert.doesNotMatch(text, /จ่ายแล้ว/, text);
    assert.doesNotMatch(text, /—/, text);
  }
  assert.match(line, /ย้าย/);
  assert.match(line, /อย่าลืมจ่ายค่างวดในแอปผ่อน/);
});

// ---- UI-56: a new installment in a prepared month --------------------------------------

test("UI_56_a_new_installment_after_full_preparation_reopens_the_gap_in_amber", () => {
  scene("over_budget"); // Nov and Dec 6,500.00, 1,500.00 over each
  move("nov", "1500.00", "2026-11");
  const novRow = () => (call("GET", "/buffer/shortfalls").body as ShortfallsOut).months.find((m) => m.month === "2026-11");
  assert.equal(novRow()?.state, "prepared");
  const novCard = () => {
    const months = (call("GET", "/debts/months").body as MonthsOut).months;
    const out = call("GET", "/buffer/shortfalls").body as ShortfallsOut;
    return cards(months, out.months, out.balance)[months.findIndex((m) => m.month === "2026-11")];
  };
  assert.deepEqual([novCard()?.chip, novCard()?.parts], [MONTHS_VIEW.bufferReady, ["bg-bar-ok", BUFFER_BAR]]);

  // 100.00 more in Nov: 6,600.00 is still under a third of 20,000.00, so the gap is amber.
  const entry: ManualEntryIn = {
    client_request_id: "after-prep",
    kind: "purchase",
    item_price: "100.00",
    months: 1,
    monthly_amount: "100.00",
    first_due_month: "2026-11",
    item_name: "สายชาร์จ",
    platform_name: null,
  };
  assert.equal(call("POST", "/installments", entry).status, 201);

  const after = novRow();
  assert.deepEqual(
    [after?.total, after?.shortfall, after?.prepared, after?.remaining_gap, after?.state],
    ["6600.00", "1600.00", "1500.00", "100.00", "partly_prepared"], // the gap: 1,600.00 - 1,500.00
  );
  const card = novCard();
  assert.deepEqual([card?.chip, card?.ring, card?.parts], [MONTHS_VIEW.over, false, ["bg-bar-ok", BUFFER_BAR, "bg-bar-over"]]);
  assert.ok(card?.text.includes(BUFFER_STATE.use), "the button is back");
  assert.ok(card?.text.includes("เตรียมจากกันชนแล้ว 1,500.00 บาท ยังขาด 100.00 บาท"));
});
