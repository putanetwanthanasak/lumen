/**
 * UI-72 (Session 25): the เช็กก่อนผ่อน form's two-way price and monthly input.
 * Each of the price and the monthly amount is typed (the user entered it) or
 * calculated:
 * - only the price typed: the monthly amount is the API's 0% suggestion (price /
 *   months rounded UP to the satang, the backend's suggested_monthly, SM-01); the
 *   client never divides money;
 * - only the monthly amount typed: the price is monthly x months, exact in BigInt
 *   satang (money.ts timesMonths), never rounded;
 * - both typed: neither is ever recalculated, the months included, so a plan with the
 *   app's interest (12,000 at 2,100 x 6) is sent as typed (review F1's decision);
 * - clearing a field makes it calculated again, from the other one.
 * Critical (money): the price and monthly amount the form ends with are the ones the
 * saving, the fee and every month total use. The screen's markup is its own, rendered
 * with react-dom/server.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { PreviewOut, RecordedOut, SuggestedMonthlyOut } from "../src/api-types.ts";
import { MONEY_ERRORS, REJECTED, THINK } from "../src/copy.ts";
import { timesMonths, toSatang } from "../src/money.ts";
import { PERSONA_SETTINGS, SCENARIOS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { ThinkFirst } from "../src/screens/ThinkFirst.tsx";
import {
  applySuggestion,
  calculatedNote,
  canPreview,
  changedBy,
  emptyForm,
  exampleForm,
  setDraft,
  shownErrors,
  suggestionRequest,
  toEntry,
  typeLinked,
  withoutRejected,
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

/** The screen's ask key (ThinkFirst.tsx `askKey`): the screen asks the API only when it changes. */
function askKey(form: Form): string | null {
  const ask = suggestionRequest(form);
  return ask === null ? null : `${ask.price}|${ask.months}`;
}

/**
 * Type into the linked fields in this order, as on the screen: the API answers after a
 * step only when the ask key changed (review round 2, F2: a harness that asked after
 * every step hid a monthly amount the screen never asked for again).
 */
function typing(...steps: [LinkedKey, string][]): Form {
  let key: string | null = null;
  return steps.reduce((form, [field, value]) => {
    const next = typeLinked(form, field, value);
    const now = askKey(next);
    const shown = now !== null && now !== key ? answered(next) : next;
    key = now;
    return shown;
  }, emptyForm());
}

/** Which fields the user typed. */
const typedOf = (form: Form) =>
  form.priceTyped && form.monthlyTyped ? "both" : form.priceTyped ? "price" : form.monthlyTyped ? "monthly" : "none";
const linked = (form: Form) => [form.price, form.months, form.monthly, typedOf(form)];

/** The entry the check would send, with a first due month picked. */
function entryOf(form: Form, id = "r") {
  const built = toEntry({ ...form, firstDue: "2026-11" }, id);
  assert.ok(built.ok);
  return built.entry;
}

// ---- one field typed: the other is calculated ---------------------------------------------

test("UI_72_price_12000_over_6_months_fills_the_monthly_amount_2000", () => {
  assert.deepEqual(linked(typing(["price", "12000"], ["months", "6"])), ["12000", "6", "2000.00", "price"]);
  // The months first, or from a chip (the same path on the screen): the same answer.
  assert.deepEqual(linked(typing(["months", "6"], ["price", "12,000"])), ["12,000", "6", "2000.00", "price"]);
});

test("UI_72_only_the_monthly_typed_makes_the_price_monthly_times_months", () => {
  assert.deepEqual(linked(typing(["months", "6"], ["monthly", "2000"])), ["12000.00", "6", "2000", "monthly"]);
  assert.deepEqual(linked(typing(["monthly", "2,000"], ["months", "6"])), ["12000.00", "6", "2,000", "monthly"]);
  // Exact, never rounded: satang and all.
  assert.equal(typing(["months", "12"], ["monthly", "1200.05"]).price, "14400.60");
  // The monthly amount is typed: nothing is asked of the API.
  assert.equal(suggestionRequest(typing(["months", "6"], ["monthly", "2000"])), null);
});

test("UI_72_an_uneven_split_uses_the_apis_rounding_and_the_way_back_is_exact", () => {
  // 1000 / 3 = 333.333...: the existing rule (the backend's suggested_monthly, SM-01)
  // rounds UP to 333.34. The screen asks the API with the price as typed; it never divides.
  const fromPrice = typing(["price", "1000"], ["months", "3"]);
  assert.deepEqual(suggestionRequest(fromPrice), { price: "1000", months: 3 });
  assert.equal(fromPrice.monthly, "333.34");
  // The other way never rounds: 333.33 x 3 is 999.99, and 333.34 x 3 is 1000.02.
  assert.equal(typing(["months", "3"], ["monthly", "333.33"]).price, "999.99");
  assert.equal(typing(["months", "3"], ["monthly", "333.34"]).price, "1000.02");
  assert.equal(typing(["months", "3"], ["monthly", "333.340"]).price, "", "three decimals: no price, never rounded");
});

test("UI_72_changing_the_months_keeps_the_typed_monthly_and_recalculates_the_price", () => {
  const typed = typing(["months", "6"], ["monthly", "2000"]);
  // Typing or a chip: the screen sends both through typeLinked("months").
  assert.deepEqual(linked(typeLinked(typed, "months", "10")), ["20000.00", "10", "2000", "monthly"]);
  assert.deepEqual(linked(typeLinked(typed, "months", "3")), ["6000.00", "3", "2000", "monthly"]);
  // No price while it cannot be calculated; the monthly amount stays as typed.
  for (const months of ["", "0", "601", "1.5"]) {
    assert.deepEqual(linked(typeLinked(typed, "months", months)), ["", months, "2000", "monthly"], months);
  }
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

// ---- both typed: neither is ever recalculated ----------------------------------------------

test("UI_72_price_then_monthly_typed_keeps_both_and_sends_them_as_typed", () => {
  // 12,000 at the app's 2,100 x 6: the monthly amount typed over the suggestion.
  const form = typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]);
  assert.deepEqual(linked(form), ["12000", "6", "2100", "both"]);
  const entry = entryOf(form);
  // Sent as typed (L49); the API reads them as 12,000.00 and 2,100.00.
  assert.deepEqual([entry.item_price, entry.monthly_amount, entry.months], ["12000", "2100", 6]);
  assert.deepEqual([toSatang(entry.item_price), toSatang(entry.monthly_amount)], [1200000n, 210000n]);
  // With the decimals typed, they go exactly so.
  const decimals = entryOf(typing(["price", "12,000.00"], ["months", "6"], ["monthly", "2,100.00"]));
  assert.deepEqual([decimals.item_price, decimals.monthly_amount], ["12000.00", "2100.00"]);
});

test("UI_72_monthly_then_price_typed_keeps_both", () => {
  const form = typing(["months", "6"], ["monthly", "2100"], ["price", "12000"]);
  assert.deepEqual(linked(form), ["12000", "6", "2100", "both"]);
  assert.equal(suggestionRequest(form), null, "nothing to ask: the monthly amount is typed");
  const entry = entryOf(form);
  assert.deepEqual([entry.item_price, entry.monthly_amount], ["12000", "2100"]);
});

test("UI_72_both_typed_months_changed_changes_neither", () => {
  const both = typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]);
  for (const months of ["10", "3", "12", "", "601"]) {
    assert.deepEqual(linked(answered(typeLinked(both, "months", months))), ["12000", months, "2100", "both"], months);
  }
  // Editing one of them keeps the other too.
  assert.deepEqual(linked(typeLinked(both, "price", "13000")), ["13000", "6", "2100", "both"]);
  assert.deepEqual(linked(typeLinked(both, "monthly", "2200")), ["12000", "6", "2200", "both"]);
});

test("UI_72_both_typed_price_cleared_recalculates_it_from_the_monthly", () => {
  const both = typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]);
  assert.deepEqual(linked(typing(["price", "12000"], ["months", "6"], ["monthly", "2100"], ["price", ""])), ["12600.00", "6", "2100", "monthly"]);
  assert.deepEqual(linked(typeLinked(both, "price", "   ")), ["12600.00", "6", "2100", "monthly"], "spaces are empty");
  // And it follows the months from then on.
  assert.equal(typeLinked(typeLinked(both, "price", ""), "months", "10").price, "21000.00");
});

test("UI_72_both_typed_monthly_cleared_asks_the_api_again", () => {
  const both = typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]);
  const cleared = typeLinked(both, "monthly", "");
  assert.deepEqual(linked(cleared), ["12000", "6", "", "price"]);
  assert.deepEqual(linked(answered(cleared)), ["12000", "6", "2000.00", "price"]);
});

test("UI_72_a_calculated_monthly_cleared_is_calculated_again_at_once", () => {
  // Review round 2, F2: the price typed, and the API's 2000.00 selected and deleted. The
  // screen asks the API only when the price or the months change, so the form keeps the
  // answer it already has for them: cleared, it is calculated again at once (rule 5).
  assert.deepEqual(linked(typing(["price", "12000"], ["months", "6"], ["monthly", ""])), ["12000", "6", "2000.00", "price"]);
  assert.deepEqual(linked(typing(["price", "12000"], ["months", "6"], ["monthly", "  "])), ["12000", "6", "2000.00", "price"]);
  // Still waiting for the answer: empty, and the answer on its way fills it.
  const waiting = typeLinked(typeLinked(emptyForm(), "price", "12000"), "months", "6");
  const cleared = typeLinked(waiting, "monthly", "");
  assert.equal(cleared.monthly, "");
  assert.equal(applySuggestion(cleared, { price: "12000", months: 6 }, "2000.00").monthly, "2000.00");
});

test("UI_72_clearing_the_only_typed_field_leaves_nothing_to_calculate_from", () => {
  assert.deepEqual(linked(typeLinked(typing(["price", "12000"], ["months", "6"]), "price", "")), ["", "6", "", "none"]);
  assert.deepEqual(linked(typeLinked(typing(["months", "6"], ["monthly", "2000"]), "monthly", "")), ["", "6", "", "none"]);
  // A calculated field cleared is calculated again at once, from the typed one.
  assert.deepEqual(linked(typeLinked(typing(["months", "6"], ["monthly", "2000"]), "price", "")), ["12000.00", "6", "2000", "monthly"]);
});

test("UI_72_an_answer_for_the_price_is_dropped_once_the_monthly_is_typed", () => {
  const waiting = typeLinked(typeLinked(emptyForm(), "price", "12000"), "months", "6");
  const ask = suggestionRequest(waiting);
  assert.ok(ask !== null);
  const typed = typeLinked(waiting, "monthly", "2100");
  assert.deepEqual(linked(applySuggestion(typed, ask, "2000.00")), ["12000", "6", "2100", "both"]);
  // Even an answer for the very price and months on the form.
  const same = typeLinked(typeLinked(typeLinked(emptyForm(), "price", "12000.00"), "months", "6"), "monthly", "2000");
  assert.deepEqual(linked(applySuggestion(same, { price: "12000.00", months: 6 }, "2000.00")), ["12000.00", "6", "2000", "both"]);
});

// ---- what is sent, and what the API does with it -------------------------------------------

test("UI_72_a_keystroke_clears_the_apis_refusal_of_the_field_it_recalculates", () => {
  // Review F3: the API refused the price (422); a keystroke that recalculates the price
  // gives it a new value, so its refusal goes too. A field left as it was keeps its own.
  const fromPrice = typing(["price", "12000"], ["months", "6"]);
  const fromMonthly = typing(["months", "6"], ["monthly", "2000"]);
  const both = typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]);
  assert.deepEqual(changedBy(fromPrice, "months", "10"), ["months", "monthly"]);
  assert.deepEqual(changedBy(fromPrice, "price", "13000"), ["price", "monthly"]);
  assert.deepEqual(changedBy(fromPrice, "monthly", "2100"), ["monthly"], "both typed now: the price stays");
  assert.deepEqual(changedBy(fromMonthly, "months", "10"), ["months", "price"]);
  assert.deepEqual(changedBy(fromMonthly, "monthly", "2100"), ["monthly", "price"]);
  assert.deepEqual(changedBy(both, "months", "10"), ["months"]);
  assert.deepEqual(changedBy(both, "monthly", ""), ["monthly"]);
  const refused = { price: REJECTED, months: REJECTED };
  assert.deepEqual(withoutRejected(refused, changedBy(fromMonthly, "monthly", "2100")), { months: REJECTED });
  assert.deepEqual(withoutRejected(refused, changedBy(fromMonthly, "months", "10")), {});
  assert.deepEqual(withoutRejected(refused, changedBy(both, "monthly", "2200")), refused);
  // Other fields keep theirs; nothing to drop gives the same object back.
  assert.deepEqual(withoutRejected({ name: REJECTED }, ["price", "monthly"]), { name: REJECTED });
  const same = { firstDue: REJECTED };
  assert.equal(withoutRejected(same, ["price"]), same);
});

test("UI_72_the_saving_and_the_months_use_the_price_and_monthly_the_form_ends_with", () => {
  // ม่อน saves 10% of the price (percent mode, L63).
  const preview = (form: Form, id: string) => {
    const entry = entryOf(form, id);
    return { entry, out: handle("POST", "/installments/preview", entry, "demo-mon").body as PreviewOut };
  };
  // Both typed: the saving is 10% of the 12,000 typed, not of the 12,600 paid in total.
  const both = preview(typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]), "two-way-1");
  assert.equal(both.out.saving_if_recorded, "1200.00");
  assert.equal(both.out.months.length, 6, "the candidate's six months");
  // Only the monthly typed: the price is 2,100 x 6, and the saving follows it.
  const fromMonthly = preview(typing(["months", "6"], ["monthly", "2100"]), "two-way-2");
  assert.deepEqual([fromMonthly.entry.item_price, fromMonthly.entry.monthly_amount], ["12600.00", "2100"]);
  assert.equal(fromMonthly.out.saving_if_recorded, "1260.00");
  // Only the price typed: the API's monthly amount.
  const fromPrice = preview(typing(["price", "12000"], ["months", "6"]), "two-way-3");
  assert.deepEqual([fromPrice.entry.item_price, fromPrice.entry.monthly_amount], ["12000", "2000.00"]);
  assert.equal(fromPrice.out.saving_if_recorded, "1200.00");
  // Every month total carries the monthly amount the form ended with: 100.00 apart in each.
  const gaps = both.out.months.map((m, i) => toSatang(m.total) - toSatang(fromPrice.out.months[i]?.total ?? "0"));
  assert.deepEqual(gaps, [10000n, 10000n, 10000n, 10000n, 10000n, 10000n]);
  // Recording saves exactly what the preview said (the previews come first: a recorded
  // entry counts in every later month total).
  const recorded = handle("POST", "/installments", both.entry, "demo-mon").body as RecordedOut;
  assert.equal(recorded.saved_amount, "1200.00");
});

test("UI_72_a_calculated_price_too_large_shows_its_error_once_the_monthly_is_left", () => {
  const huge = { ...typing(["months", "600"], ["monthly", "20000000"]), firstDue: "2026-11" };
  assert.equal(huge.price, "12000000000.00"); // 11 digits: more than Numeric(12,2) holds
  assert.equal(canPreview(huge), false);
  assert.deepEqual(shownErrors(huge, new Set()), {}, "not before the user leaves the monthly amount");
  assert.deepEqual(shownErrors(huge, new Set(["monthly"])), { price: MONEY_ERRORS.too_large });
  // A typed price shows its own error only once left, as before.
  assert.deepEqual(shownErrors({ ...huge, priceTyped: true, price: "1,5" }, new Set(["monthly"])), {});
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
  // The demo strip fills the price as typed and the monthly amount as calculated, so its
  // note "คำนวณจากราคา ÷ จำนวนเดือน" must be true: each monthly amount is the API's answer.
  for (const [name, s] of Object.entries(SCENARIOS)) {
    const form = typing(["price", s.item_price], ["months", String(s.months)]);
    assert.equal(form.monthly, s.monthly_amount, name);
  }
});

test("UI_72_an_example_counts_its_price_as_typed_and_its_monthly_as_calculated", () => {
  // Review round 2, F4: the strip's examples and the deep link fill through exampleForm.
  // The 6-month chip (none of the examples is 6 months): the API answers 12,000 -> 2,000.00,
  // 30,000 -> 5,000.00, 48,000 -> 8,000.00.
  const sixth: Record<string, string> = { GREEN: "2000.00", YELLOW: "5000.00", RED: "8000.00" };
  for (const [name, s] of Object.entries(SCENARIOS)) {
    const example = exampleForm(emptyForm(), s, "2026-11");
    assert.deepEqual(linked(example), [s.item_price, String(s.months), s.monthly_amount, "price"], name);
    assert.equal(calculatedNote(example)?.field, "monthly", name);
    // A month chip after the example: the price stays, and the monthly amount waits for the API.
    const chip = typeLinked(example, "months", "6");
    assert.deepEqual(linked(chip), [s.item_price, "6", "", "price"], name);
    assert.equal(answered(chip).monthly, sixth[name], name);
    // Its own months again (the picked chip tapped): the example's amount stays.
    assert.equal(typeLinked(example, "months", String(s.months)).monthly, s.monthly_amount, name);
  }
  // The screen fills its examples this way.
  const src = readFileSync(join("src", "screens", "ThinkFirst.tsx"), "utf8");
  assert.match(src, /return exampleForm\(base, SCENARIOS\[scenario\], firstDueChoices\(new Date\(\)\)\.nextMonth\);/);
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
  assert.equal(THINK.fromPrice, "คำนวณจากราคา ÷ จำนวนเดือน (ผ่อน 0%) ถ้าแอปผ่อนแจ้งยอดต่างจากนี้ แก้ให้ตรงกับแอปได้");
  assert.equal(THINK.fromMonthly, "คำนวณจากค่างวด × จำนวนเดือน");
  const notes = [THINK.fromPrice, THINK.fromMonthly, THINK.monthlyHelp];
  const drawn = (html: string) => notes.filter((text) => html.includes(text));

  // Nothing calculated yet: the monthly amount keeps its usual help, and no note.
  assert.deepEqual(drawn(render(emptyForm())), [THINK.monthlyHelp]);
  assert.equal(calculatedNote(emptyForm()), null);

  // Only the price typed: the note under ค่างวดต่อเดือน, in place of its usual help.
  const fromPrice = render(typing(["price", "12000"], ["months", "6"]));
  assert.deepEqual(drawn(fromPrice), [THINK.fromPrice]);
  const priceNote = line(THINK.fromPrice).exec(fromPrice);
  assert.ok(priceNote !== null);
  assert.ok(at(fromPrice, `>${THINK.monthly}</label>`) < priceNote.index && priceNote.index < at(fromPrice, `>${THINK.firstDue}</legend>`));
  assert.match(fromPrice, new RegExp(`aria-describedby="${priceNote[1]}"`));

  // Only the monthly amount typed: the note under ราคาสินค้า, and none under the monthly amount.
  const fromMonthly = render(typing(["months", "6"], ["monthly", "2000"]));
  assert.deepEqual(drawn(fromMonthly), [THINK.fromMonthly]);
  const monthlyNote = line(THINK.fromMonthly).exec(fromMonthly);
  assert.ok(monthlyNote !== null);
  assert.ok(at(fromMonthly, `>${THINK.price}</label>`) < monthlyNote.index && monthlyNote.index < at(fromMonthly, `>${THINK.months}</label>`));
  assert.match(fromMonthly, /value="12000.00"/);

  // Both typed: no note and no help under either field.
  assert.deepEqual(drawn(render(typing(["price", "12000"], ["months", "6"], ["monthly", "2100"]))), []);
  assert.equal(calculatedNote(typing(["price", "12000"], ["months", "6"], ["monthly", "2100"])), null);

  // A price that cannot be calculated yet: no note claims it was.
  assert.deepEqual(drawn(render(typing(["monthly", "2000"]))), []);
});

test("UI_72_the_screen_sends_the_price_months_chips_and_monthly_through_the_link", () => {
  const src = readFileSync(join("src", "screens", "ThinkFirst.tsx"), "utf8");
  for (const key of ["price", "months", "monthly"]) assert.match(src, new RegExp(`onChange=\\{\\(v\\) => type\\("${key}", v\\)\\}`), key);
  assert.match(src, /onPick=\{\(months\) => type\("months", months\)\}/);
  assert.match(src, /setForm\(\(f\) => typeLinked\(f, key, value\)\)/);
  // The refusals of the typed field and the recalculated one go (review F3).
  assert.match(src, /changed\(changedBy\(form, key, value\)\)/);
  assert.match(src, /setRejected\(\(r\) => withoutRejected\(r, keys\)\)/);
  // No linked field is set around the link.
  assert.doesNotMatch(src, /set\("(price|months|monthly)"/);
});
