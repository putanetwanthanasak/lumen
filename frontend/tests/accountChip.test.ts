/**
 * UI-69 (Session 23): the KidNee card on บัญชีหลัก shows the months screen's chip. This
 * month's row in GET /buffer/shortfalls decides it (the API, as in #47 and UI-54):
 * - prepared: "กันชนเตรียมเงินแล้ว" in the buffer's chip;
 * - partly prepared, not prepared, or no row: "เกินงบ";
 * - over one third of income: the red chip, even when prepared;
 * - in budget: unchanged.
 * Only this month's row counts, and without the buffer states the chip is the month's
 * status, as on ภาระผ่อนรายเดือน.
 */
import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { answerFromMock } from "../src/api.ts";
import type { BufferOut, MonthRow, PreparedState, ShortfallMonth, ShortfallsOut } from "../src/api-types.ts";
import { ACCENT, BUFFER_CHIP } from "../src/accent.ts";
import { MONTHS_VIEW } from "../src/copy.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { monthChip, STATUS_CHIP } from "../src/monthStatus.ts";
import { KidNeeCard, loadAccount } from "../src/screens/Account.tsx";

const plain = (html: string) => html.replace(/<[^>]+>/g, "");
const BUFFER_OUT: BufferOut = { balance: "4200.00", monthly_total: "5000.00", months_covered: 1 };
const THIS_MONTH = "2026-11";
const OVER: Pick<MonthRow, "over_budget" | "over_one_third"> = { over_budget: true, over_one_third: false };

function shortfallRow(month: string, state: PreparedState): ShortfallMonth {
  return {
    month,
    total: "5800.00",
    budget: "4300.00",
    shortfall: "1500.00",
    prepared: state === "prepared" ? "1500.00" : state === "partly_prepared" ? "500.00" : "0.00",
    remaining_gap: state === "prepared" ? "0.00" : state === "partly_prepared" ? "1000.00" : "1500.00",
    state,
    covered_by_buffer: "0.00",
    still_short: "0.00",
  };
}

function shortfalls(...rows: ShortfallMonth[]): ShortfallsOut {
  return { balance: "4200.00", shortfall: "1500.00", remaining_gap: "0.00", covered: true, still_short: "0.00", months: rows, months_truncated: false };
}

/** The card's chip: its class list, its icon path and its words. */
function chipOf(flags: Pick<MonthRow, "over_budget" | "over_one_third">, out: ShortfallsOut | null): { html: string; text: string } {
  const month: MonthRow = { month: THIS_MONTH, total: "5800.00", ...flags };
  const html = renderToStaticMarkup(createElement(KidNeeCard, { buffer: BUFFER_OUT, month, shortfalls: out }));
  const chip = /<span class="inline-flex items-center gap-1 rounded-pill[^"]*">.*?<\/span>/.exec(html)?.[0] ?? "";
  return { html: chip, text: plain(chip) };
}

beforeEach(() => resetMock(new Date(2026, 9, 27), PERSONA_SETTINGS));
afterEach(() => answerFromMock(false));

test("UI_69_prepared_this_month_shows_the_buffers_chip", () => {
  const { html, text } = chipOf(OVER, shortfalls(shortfallRow(THIS_MONTH, "prepared")));
  assert.equal(text, MONTHS_VIEW.bufferReady);
  assert.equal(text, "กันชนเตรียมเงินแล้ว");
  assert.ok(html.includes(BUFFER_CHIP), html);
  assert.deepEqual(monthChip(OVER, "prepared"), { icon: ACCENT.buffer.icon, label: MONTHS_VIEW.bufferReady, className: BUFFER_CHIP });
});

test("UI_69_partly_or_not_prepared_still_says_over_budget", () => {
  for (const state of ["partly_prepared", "not_prepared"] as const) {
    const { html, text } = chipOf(OVER, shortfalls(shortfallRow(THIS_MONTH, state)));
    assert.equal(text, MONTHS_VIEW.over, state);
    assert.ok(html.includes(STATUS_CHIP.over), state);
  }
  // No row for this month in the answer: the month's status.
  assert.equal(chipOf(OVER, shortfalls()).text, MONTHS_VIEW.over);
});

test("UI_69_over_one_third_of_income_stays_red_even_when_prepared", () => {
  const { html, text } = chipOf({ over_budget: true, over_one_third: true }, shortfalls(shortfallRow(THIS_MONTH, "prepared")));
  assert.equal(text, MONTHS_VIEW.risk);
  assert.ok(html.includes(STATUS_CHIP.risk), html);
  assert.ok(!html.includes(BUFFER_CHIP));
});

test("UI_69_in_budget_is_unchanged", () => {
  const inBudget = { over_budget: false, over_one_third: false };
  assert.equal(chipOf(inBudget, null).text, MONTHS_VIEW.ok);
  assert.equal(chipOf(inBudget, shortfalls()).text, MONTHS_VIEW.ok);
  // A prepared row never turns a month in budget into the buffer's chip.
  assert.equal(chipOf(inBudget, shortfalls(shortfallRow(THIS_MONTH, "prepared"))).text, MONTHS_VIEW.ok);
});

test("UI_69_only_this_months_row_counts", () => {
  // Next month prepared and listed first, this month not: this month is still over budget.
  const out = shortfalls(shortfallRow("2026-12", "prepared"), shortfallRow(THIS_MONTH, "not_prepared"));
  assert.equal(chipOf(OVER, out).text, MONTHS_VIEW.over);
  assert.equal(chipOf(OVER, shortfalls(shortfallRow("2026-12", "prepared"))).text, MONTHS_VIEW.over);
  // And the other way round: this month prepared, listed after another month.
  const later = shortfalls(shortfallRow("2026-10", "not_prepared"), shortfallRow(THIS_MONTH, "prepared"));
  assert.equal(chipOf(OVER, later).text, MONTHS_VIEW.bufferReady);
});

test("UI_69_without_the_buffer_states_the_chip_is_the_months_status", () => {
  assert.equal(chipOf(OVER, null).text, MONTHS_VIEW.over);
  assert.equal(chipOf({ over_budget: true, over_one_third: true }, null).text, MONTHS_VIEW.risk);
});

test("UI_69_load_account_asks_for_the_buffer_states_and_survives_their_failure", async () => {
  answerFromMock(true);
  const loaded = await loadAccount();
  const expected = handle("GET", "/buffer/shortfalls", undefined, "demo-mon").body as ShortfallsOut;
  assert.deepEqual(loaded.shortfalls, expected);
  // The buffer states fail on their own: the screen still loads, with no states.
  answerFromMock(false);
  const realFetch = globalThis.fetch;
  globalThis.fetch = (async (url: string) => {
    const path = url.replace(/^\/api/, "");
    if (path === "/buffer/shortfalls") throw new TypeError("Failed to fetch");
    const answer = handle("GET", path, undefined, "demo-mon");
    return { status: answer.status, json: async () => answer.body } as Response;
  }) as typeof fetch;
  try {
    const partial = await loadAccount();
    assert.equal(partial.shortfalls, null);
    assert.ok(partial.month !== null);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("UI_69_before_setup_there_is_no_call_for_the_buffer_states", async () => {
  resetMock(new Date(2026, 9, 27)); // first launch: no settings
  answerFromMock(true);
  const loaded = await loadAccount();
  assert.equal(loaded.month, null);
  assert.equal(loaded.shortfalls, null);
});
