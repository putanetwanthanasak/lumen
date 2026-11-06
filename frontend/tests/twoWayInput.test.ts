/**
 * UI-72 (Session 25): the เช็กก่อนผ่อน form's two-way price and monthly input.
 * Of the price and the monthly amount, the one typed in last is the input, kept as
 * typed; the other is calculated from it and the months:
 * - from the price: the API's 0% suggestion (price / months rounded UP to the
 *   satang, the backend's suggested_monthly, SM-01); the client never divides money;
 * - from the monthly amount: monthly x months, exact in BigInt satang
 *   (money.ts timesMonths), never rounded.
 * Critical (money): the price the form ends with is the one the saving and every
 * month total use. The screen's markup is its own, rendered with react-dom/server.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { PreviewOut, RecordedOut, SuggestedMonthlyOut } from "../src/api-types.ts";
import { MONEY_ERRORS, THINK } from "../src/copy.ts";
import { timesMonths, toSatang } from "../src/money.ts";
import { PERSONA_SETTINGS, SCENARIOS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { ThinkFirst } from "../src/screens/ThinkFirst.tsx";
import {
  applySuggestion,
  calculatedNote,
  canPreview,
  emptyForm,
  setDraft,
  shownErrors,
  suggestionRequest,
  toEntry,
  typeLinked,
  type Form,
  type LinkedKey,
} from "../src/thinkFirstForm.ts";

const TODAY = new Date(2026, 9, 27);

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

/** The API's 0% suggestion, as the screen applies it (the mock answers like the backend). */
function answered(form: Form): Form {
  const ask = suggestionRequest(form);
  if (ask === null) return form;
  const res = handle("GET", `/installments/suggested-monthly?item_price=${ask.price}&months=${ask.months}`, undefined, "demo-mon");
  assert.equal(res.status, 200);
  return applySuggestion(form, ask, (res.body as SuggestedMonthlyOut).monthly_amount);
}

/** Type into the linked fields in this order, the API answering after each step, as on the screen. */
function typing(...steps: [LinkedKey, string][]): Form {
  return steps.reduce((form, [key, value]) => answered(typeLinked(form, key, value)), emptyForm());
}

const linked = (form: Form) => [form.price, form.months, form.monthly, form.source];

test("UI_72_price_12000_over_6_months_fills_the_monthly_amount_2000", () => {
  assert.deepEqual(linked(typing(["price", "12000"], ["months", "6"])), ["12000", "6", "2000.00", "price"]);
  // The months first, or from a chip (the same path on the screen): the same answer.
  assert.deepEqual(linked(typing(["months", "6"], ["price", "12,000"])), ["12,000", "6", "2000.00", "price"]);
});

test("UI_72_monthly_2000_over_6_months_fills_the_price_12000", () => {
  assert.deepEqual(linked(typing(["months", "6"], ["monthly", "2000"])), ["12000.00", "6", "2000", "installment"]);
  assert.deepEqual(linked(typing(["monthly", "2,000"], ["months", "6"])), ["12000.00", "6", "2,000", "installment"]);
  // Exact, never rounded: satang and all.
  assert.equal(typing(["months", "12"], ["monthly", "1200.05"]).price, "14400.60");
  // The monthly amount is the input: nothing is asked of the API.
  assert.equal(suggestionRequest(typing(["months", "6"], ["monthly", "2000"])), null);
});

test("UI_72_an_uneven_split_uses_the_apis_rounding_and_the_way_back_is_exact", () => {
  // 1000 / 3 = 333.333...: the existing rule (the backend's suggested_monthly, SM-01)
  // rounds UP to 333.34. The screen asks the API with the price as typed; it never divides.
  const fromPrice = typing(["price", "1000"], ["months", "3"]);
  assert.deepEqual(suggestionRequest(fromPrice), { price: "1000", months: 3 });
  assert.equal(fromPrice.monthly, "333.34");
  // The other way never rounds: 333.33 x 3 is 999.99, and 333.34 x 3 is 1000.02.
  assert.equal(typeLinked(fromPrice, "monthly", "333.33").price, "999.99");
  assert.equal(typeLinked(fromPrice, "monthly", "333.340").price, "", "three decimals: no price, never rounded");
  assert.equal(typing(["months", "3"], ["monthly", "333.34"]).price, "1000.02");
});

test("UI_72_typing_the_price_then_the_monthly_makes_the_monthly_the_input", () => {
  const fromPrice = typing(["price", "12000"], ["months", "6"]);
  assert.equal(fromPrice.monthly, "2000.00");
  // The user types what their app charges: the price follows it.
  const fromMonthly = answered(typeLinked(fromPrice, "monthly", "2100"));
  assert.deepEqual(linked(fromMonthly), ["12600.00", "6", "2100", "installment"]);
  // And back: typing the price makes it the input again, and the API fills the monthly amount.
  const priceAgain = typeLinked(fromMonthly, "price", "12000");
  assert.deepEqual(linked(priceAgain), ["12000", "6", "", "price"]);
  assert.deepEqual(linked(answered(priceAgain)), ["12000", "6", "2000.00", "price"]);
});

test("UI_72_changing_the_months_keeps_the_typed_monthly_and_recalculates_the_price", () => {
  const typed = typing(["months", "6"], ["monthly", "2000"]);
  // Typing or a chip: the screen sends both through typeLinked("months").
  assert.deepEqual(linked(typeLinked(typed, "months", "10")), ["20000.00", "10", "2000", "installment"]);
  assert.deepEqual(linked(typeLinked(typed, "months", "3")), ["6000.00", "3", "2000", "installment"]);
  // No price while it cannot be calculated; the monthly amount stays as typed.
  for (const months of ["", "0", "601", "1.5"]) {
    assert.deepEqual(linked(typeLinked(typed, "months", months)), ["", months, "2000", "installment"], months);
  }
  assert.deepEqual(linked(typeLinked(typed, "monthly", "")), ["", "6", "", "installment"]);
});

test("UI_72_changing_the_months_keeps_the_typed_price_and_asks_again_for_the_monthly", () => {
  const typed = typing(["price", "12000"], ["months", "6"]);
  const changed = typeLinked(typed, "months", "10");
  // The old answer never stands for the new months: empty until the API answers.
  assert.deepEqual(linked(changed), ["12000", "10", "", "price"]);
  assert.equal(applySuggestion(changed, { price: "12000", months: 6 }, "2000.00").monthly, "", "a late answer for 6 months");
  assert.deepEqual(linked(answered(changed)), ["12000", "10", "1200.00", "price"]);
  // The same request again (the picked chip tapped, or "12,000" for "12000"): the answer stays.
  assert.equal(typeLinked(typed, "months", "6").monthly, "2000.00");
  assert.equal(typeLinked(typed, "price", "12,000").monthly, "2000.00");
  // A price that is not valid yet: nothing to ask, and no stale answer.
  assert.equal(typeLinked(typed, "price", "12000.").monthly, "");
});

test("UI_72_an_answer_for_the_price_is_dropped_once_the_monthly_is_typed", () => {
  const waiting = typeLinked(typeLinked(emptyForm(), "price", "12000"), "months", "6");
  const ask = suggestionRequest(waiting);
  assert.ok(ask !== null);
  const typed = typeLinked(waiting, "monthly", "2100");
  assert.deepEqual(linked(applySuggestion(typed, ask, "2000.00")), ["12600.00", "6", "2100", "installment"]);
});

test("UI_72_the_saving_and_the_months_use_the_price_the_form_ends_with", () => {
  // ม่อน saves 10% of the price (percent mode, L63). From the monthly amount, the
  // price is monthly x months, and the saving follows it.
  const preview = (form: Form, id: string) => {
    const built = toEntry({ ...form, firstDue: "2026-11" }, id);
    assert.ok(built.ok);
    return { entry: built.entry, out: handle("POST", "/installments/preview", built.entry, "demo-mon").body as PreviewOut };
  };
  const fromMonthly = preview(typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]), "two-way-1");
  assert.deepEqual([fromMonthly.entry.item_price, fromMonthly.entry.monthly_amount, fromMonthly.entry.months], ["12600.00", "2100", 6]);
  assert.equal(fromMonthly.out.saving_if_recorded, "1260.00");
  assert.equal(fromMonthly.out.months.length, 6, "the candidate's six months");
  // From the price: the price as typed, and the API's monthly amount.
  const fromPrice = preview(typing(["months", "6"], ["monthly", "2100"], ["price", "12000"]), "two-way-2");
  assert.deepEqual([fromPrice.entry.item_price, fromPrice.entry.monthly_amount], ["12000", "2000.00"]);
  assert.equal(fromPrice.out.saving_if_recorded, "1200.00");
  // Every month total carries the monthly amount the form ended with: 100.00 apart in each.
  const gaps = fromMonthly.out.months.map((m, i) => toSatang(m.total) - toSatang(fromPrice.out.months[i]?.total ?? "0"));
  assert.deepEqual(gaps, [10000n, 10000n, 10000n, 10000n, 10000n, 10000n]);
  // Recording saves exactly what the preview said (both previews are made first: a
  // recorded entry counts in every later month total).
  const recorded = handle("POST", "/installments", fromMonthly.entry, "demo-mon").body as RecordedOut;
  assert.equal(recorded.saved_amount, "1260.00");
});

test("UI_72_a_calculated_price_too_large_shows_its_error_once_the_monthly_is_left", () => {
  const huge = { ...typing(["months", "600"], ["monthly", "20000000"]), firstDue: "2026-11" };
  assert.equal(huge.price, "12000000000.00"); // 11 digits: more than Numeric(12,2) holds
  assert.equal(canPreview(huge), false);
  assert.deepEqual(shownErrors(huge, new Set()), {}, "not before the user leaves the monthly amount");
  assert.deepEqual(shownErrors(huge, new Set(["monthly"])), { price: MONEY_ERRORS.too_large });
  // A typed price shows its own error only once left, as before.
  assert.deepEqual(shownErrors({ ...huge, source: "price", price: "1,5" }, new Set(["monthly"])), {});
});

test("UI_72_times_months_is_exact_in_satang", () => {
  const cases: [string, number, string][] = [
    ["2000", 6, "12000.00"],
    ["2000.00", 6, "12000.00"],
    ["333.34", 3, "1000.02"],
    ["0.01", 600, "6.00"],
    ["1200.5", 12, "14406.00"],
    ["9999999999.99", 1, "9999999999.99"],
    ["9999999999.99", 600, "5999999999994.00"],
  ];
  for (const [monthly, months, price] of cases) assert.equal(timesMonths(monthly, months), price, `${monthly} x ${months}`);
  for (const months of [0, -1, 1.5]) assert.throws(() => timesMonths("2000", months), RangeError);
});

test("UI_72_the_examples_monthly_amounts_are_the_apis_suggestion_for_their_price", () => {
  // The demo strip fills price and monthly with the price as the input, so its note
  // "คำนวณจากราคา ÷ จำนวนเดือน" must be true: each monthly amount is the API's answer.
  for (const [name, s] of Object.entries(SCENARIOS)) {
    const form = typing(["price", s.item_price], ["months", String(s.months)]);
    assert.equal(form.monthly, s.monthly_amount, name);
  }
});

// ---- the screen: one quiet line under the calculated field ------------------------------

function render(form: Form): string {
  setDraft({ form, stage: { name: "form" } });
  try {
    return renderToStaticMarkup(createElement(ThinkFirst, { load: { state: "ready", data: { hint: null } }, reload: () => undefined }));
  } finally {
    setDraft(null);
  }
}

const at = (html: string, text: string) => {
  const i = html.indexOf(text);
  assert.ok(i >= 0, `not drawn: ${text}`);
  return i;
};

/** The quiet help line, as the Field draws it, tied to its input by aria-describedby. */
const line = (text: string) => new RegExp(`<p id="([^"]+-help)" class="text-body text-ink-muted">${text.replace(/[()]/g, "\\$&")}</p>`);

test("UI_72_the_note_sits_under_the_calculated_field_only", () => {
  assert.equal(THINK.fromPrice, "คำนวณจากราคา ÷ จำนวนเดือน (ผ่อน 0%)");
  assert.equal(THINK.fromMonthly, "คำนวณจากค่างวด × จำนวนเดือน");

  // Nothing calculated yet: the monthly amount keeps its usual help, and no note.
  const empty = render(emptyForm());
  assert.ok(empty.includes(THINK.monthlyHelp));
  assert.ok(!empty.includes(THINK.fromPrice) && !empty.includes(THINK.fromMonthly));
  assert.equal(calculatedNote(emptyForm()), null);

  // From the price: the note under ค่างวดต่อเดือน, in place of its usual help.
  const fromPrice = render(typing(["price", "12000"], ["months", "6"]));
  const priceNote = line(THINK.fromPrice).exec(fromPrice);
  assert.ok(priceNote !== null);
  assert.ok(at(fromPrice, `>${THINK.monthly}</label>`) < priceNote.index && priceNote.index < at(fromPrice, `>${THINK.firstDue}</legend>`));
  assert.match(fromPrice, new RegExp(`aria-describedby="${priceNote[1]}"`));
  assert.ok(!fromPrice.includes(THINK.monthlyHelp) && !fromPrice.includes(THINK.fromMonthly));

  // From the monthly amount: the note under ราคาสินค้า, and none under the monthly amount.
  const fromMonthly = render(typing(["months", "6"], ["monthly", "2000"]));
  const monthlyNote = line(THINK.fromMonthly).exec(fromMonthly);
  assert.ok(monthlyNote !== null);
  assert.ok(at(fromMonthly, `>${THINK.price}</label>`) < monthlyNote.index && monthlyNote.index < at(fromMonthly, `>${THINK.months}</label>`));
  assert.ok(!fromMonthly.includes(THINK.monthlyHelp) && !fromMonthly.includes(THINK.fromPrice));
  // The price shows the calculated value.
  assert.match(fromMonthly, /value="12000.00"/);

  // A price that cannot be calculated yet: no note claims it was.
  assert.ok(!render(typing(["monthly", "2000"])).includes(THINK.fromMonthly));
});

test("UI_72_the_screen_sends_the_price_months_chips_and_monthly_through_the_link", () => {
  const src = readFileSync(join("src", "screens", "ThinkFirst.tsx"), "utf8");
  for (const key of ["price", "months", "monthly"]) assert.match(src, new RegExp(`onChange=\\{\\(v\\) => type\\("${key}", v\\)\\}`), key);
  assert.match(src, /onPick=\{\(months\) => type\("months", months\)\}/);
  assert.match(src, /setForm\(\(f\) => typeLinked\(f, key, value\)\)/);
  // No linked field is set around the link.
  assert.doesNotMatch(src, /set\("(price|months|monthly)"/);
});
