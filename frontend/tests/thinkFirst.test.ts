/**
 * The เช็กก่อนผ่อน form and its stages (screen 3): UI-16 (review round 2, F2, F3,
 * F5), UI-18 (first due month, the 0% suggestion), UI-19 (the app), UI-21 (saving),
 * UI-37 (the field order with every field in view, the cash kinds behind a link, the
 * keyboards, the month picks, and the check in the bar above the nav, disabled until
 * the four required fields are valid; critical where it gates money). UI-37's markup is the screen's
 * own, rendered with react-dom/server: no browser, no extra package.
 */
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { InstallmentLine, PreviewOut, RecordedOut, SuggestedMonthlyOut } from "../src/api-types.ts";
import { COMMON, MONEY_ERRORS, THINK } from "../src/copy.ts";
import { ThinkFirst } from "../src/screens/ThinkFirst.tsx";
import { groupByPlatform } from "../src/installmentStatus.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { thaiMonth } from "../src/thaiMonth.ts";
import {
  answerPreview,
  applySuggestion,
  canPreview,
  edit,
  emptyForm,
  entryToRecord,
  firstDueChoices,
  MONTH_CHIPS,
  setDraft,
  shownErrors,
  startPreview,
  suggestionRequest,
  toEntry,
  type Form,
  type Stage,
} from "../src/thinkFirstForm.ts";

const TODAY = new Date(2026, 9, 27);
const FORM: Form = { ...emptyForm(), price: "12000", months: "10", monthly: "1200", firstDue: "2026-11" };
const VERDICT: PreviewOut = {
  verdict: "GREEN",
  months: [],
  over_budget_months: [],
  monthly_total: "3500.00",
  saving_if_recorded: "1200.00",
};

const LINE: InstallmentLine = {
  id: "x",
  vendor: "manual",
  contract_id: "manual-x",
  kind: "purchase",
  item_name: "",
  principal: "100.00",
  monthly_amount: "10.00",
  months: 10,
  paid_amount: "0.00",
  late_fees_accrued: "0.00",
  remaining: "100.00",
  status: "active",
  disputed_at: null,
  owed: true,
  platform_name: null,
};

function built(form: Form, id: string) {
  const result = toEntry(form, id);
  assert.ok(result.ok);
  return result.entry;
}

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

test("UI_16_an_answer_for_a_form_edited_while_checking_is_discarded", () => {
  // F2: the user changes months while the preview is in flight.
  const entry = built(FORM, "req-a");
  const checking = startPreview(entry);
  const edited = edit(checking);
  assert.deepEqual(edited, { name: "form" });
  assert.deepEqual(answerPreview(edited, "req-a", VERDICT), { name: "form" });
});

test("UI_16_an_answer_for_an_older_preview_is_discarded", () => {
  const newer = startPreview(built(FORM, "req-b"));
  assert.equal(answerPreview(newer, "req-a", VERDICT), newer);
  const shown = answerPreview(newer, "req-b", VERDICT);
  assert.equal(shown.name, "verdict");
});

test("UI_16_record_and_its_retry_reuse_the_preview_request_id", () => {
  // F3: a retry after a lost answer must send the same client_request_id.
  const entry = built(FORM, "req-a");
  const shown: Stage = answerPreview(startPreview(entry), "req-a", VERDICT);
  const first = entryToRecord(shown);
  const retry = entryToRecord(shown);
  assert.equal(first?.client_request_id, "req-a");
  assert.deepEqual(retry, first);
  assert.equal(entryToRecord({ name: "form" }), null);
  // And the API records it once.
  const a = handle("POST", "/installments", first, "demo-mint").body as RecordedOut;
  const b = handle("POST", "/installments", retry, "demo-mint").body as RecordedOut;
  assert.equal(b.status, "duplicate");
  assert.equal(b.installment_id, a.installment_id);
});

test("UI_16_kind_is_sent_and_a_cash_loan_saves_nothing", () => {
  // F5, L62: kind is an input; L63: cash never saves.
  assert.equal(built(FORM, "r").kind, "purchase");
  const loan = built({ ...FORM, kind: "cash_loan" }, "r-loan");
  assert.equal(loan.kind, "cash_loan");
  const out = handle("POST", "/installments", loan, "demo-mint").body as RecordedOut;
  assert.equal(out.saved_amount, "0.00");
  assert.equal(built({ ...FORM, kind: "cash_withdrawal" }, "r-w").kind, "cash_withdrawal");
});

// ---- UI-18: first due month and the 0% suggestion -------------------------------

test("UI_18_first_due_month_has_no_default_and_blocks_the_preview", () => {
  const empty = emptyForm();
  assert.equal(empty.firstDue, "");
  assert.equal(canPreview(empty), false);
  // Every other field filled: the first due month still blocks it (and UI-37: so does
  // any other required field).
  assert.equal(canPreview({ ...FORM, firstDue: "" }), false);
  assert.equal(canPreview({ ...FORM, firstDue: "2026-10" }), true);
  const result = toEntry({ ...FORM, firstDue: "" }, "r");
  assert.equal(result.ok, false);
  if (!result.ok) assert.ok(result.errors.firstDue !== undefined);
});

test("UI_18_the_two_first_due_choices_are_this_month_and_next_month", () => {
  assert.deepEqual(firstDueChoices(TODAY), { thisMonth: "2026-10", nextMonth: "2026-11" });
  assert.deepEqual(firstDueChoices(new Date(2026, 11, 31)), { thisMonth: "2026-12", nextMonth: "2027-01" });
  // Two equal buttons: the word on one line, the month on a second, smaller line.
  assert.equal(THINK.firstDueThis, "เดือนนี้");
  assert.equal(THINK.firstDueNext, "เดือนหน้า");
  assert.equal(thaiMonth("2026-10"), "ต.ค. 2569");
});

test("UI_18_suggestion_is_asked_only_when_price_and_months_are_ready", () => {
  assert.equal(suggestionRequest(emptyForm()), null);
  assert.equal(suggestionRequest({ ...emptyForm(), price: "12000" }), null);
  assert.deepEqual(suggestionRequest({ ...emptyForm(), price: "1,000", months: "3" }), { price: "1000", months: 3 });
  assert.equal(suggestionRequest({ ...emptyForm(), price: "1000", months: "3", monthlyEdited: true }), null);
});

test("UI_18_a_value_the_user_edited_is_never_overwritten", () => {
  const typed = { ...emptyForm(), price: "1000", months: "3" };
  const asked = { price: "1000", months: 3 };
  assert.equal(applySuggestion(typed, asked, "333.34").monthly, "333.34");
  const edited = { ...typed, monthly: "350", monthlyEdited: true };
  assert.equal(applySuggestion(edited, asked, "333.34").monthly, "350");
  // An answer for inputs that changed since is dropped.
  assert.equal(applySuggestion({ ...typed, months: "4" }, asked, "333.34").monthly, "");
});

test("UI_18_the_api_suggests_price_over_months_rounded_up_to_the_satang", () => {
  const ask = (price: string, months: number) =>
    handle("GET", `/installments/suggested-monthly?item_price=${price}&months=${months}`, undefined, "demo-mint");
  const monthly = (price: string, months: number) => (ask(price, months).body as SuggestedMonthlyOut).monthly_amount;
  assert.equal(monthly("12000", 10), "1200.00");
  assert.equal(monthly("1000", 3), "333.34"); // 333.333... rounded UP, never down
  assert.equal(monthly("1000.01", 1), "1000.01");
  assert.equal(monthly("0.01", 3), "0.01");
  assert.equal(monthly("100", 7), "14.29");
  assert.equal(ask("1000", 0).status, 422);
  assert.equal(ask("1.234", 3).status, 422);
});

// ---- UI-19: the app the user pays through ------------------------------------------

test("UI_19_platform_name_is_optional_trimmed_and_at_most_60_characters", () => {
  assert.equal(built(FORM, "r").platform_name, null);
  assert.equal(built({ ...FORM, platform: "  ShopDemo " }, "r").platform_name, "ShopDemo");
  assert.equal(built({ ...FORM, platform: "ก".repeat(60) }, "r").platform_name, "ก".repeat(60));
  const long = toEntry({ ...FORM, platform: "ก".repeat(61) }, "r");
  assert.equal(long.ok, false);
  if (!long.ok) assert.ok(long.errors.platform !== undefined);
  const res = handle("POST", "/installments/preview", { ...built(FORM, "r"), platform_name: "a\u0007b" }, "demo-mint");
  assert.equal(res.status, 422);
});

test("UI_19_home_groups_by_app_with_no_app_last", () => {
  const line = (id: string, platform_name: string | null) => ({ ...LINE, id, platform_name });
  const groups = groupByPlatform([line("a", null), line("b", "ShopDemo"), line("c", "แอป B"), line("d", " ShopDemo ")]);
  assert.deepEqual(
    groups.map((g) => [g.label, g.lines.map((l) => l.id)]),
    [
      ["ShopDemo", ["b", "d"]],
      ["แอป B", ["c"]],
      ["ไม่ระบุแอป", ["a"]],
    ],
  );
});

// ---- UI-21: the result screen's saving line ------------------------------------------

test("UI_21_preview_says_what_recording_would_save_and_recording_saves_that", () => {
  const entry = built(FORM, "r-save");
  const preview = handle("POST", "/installments/preview", entry, "demo-mint").body as PreviewOut;
  assert.equal(preview.saving_if_recorded, "1200.00");
  const recorded = handle("POST", "/installments", entry, "demo-mint").body as RecordedOut;
  assert.equal(recorded.saved_amount, preview.saving_if_recorded);
  const cash = handle("POST", "/installments/preview", { ...entry, kind: "cash_loan" }, "demo-mint").body as PreviewOut;
  assert.equal(cash.saving_if_recorded, "0.00");
  // The safety net (L63): main 8,300.00 left; 10% of 78,000.00 would leave 500.00
  // (allowed), 10% of 78,000.10 would leave 499.99 (skipped whole). The preview says
  // so, and recording then saves exactly that.
  const near = (price: string, id: string) => ({ ...entry, client_request_id: id, item_price: price, months: 12, monthly_amount: "6500.00" });
  const atNet = handle("POST", "/installments/preview", near("78000.00", "n1"), "demo-mint").body as PreviewOut;
  assert.equal(atNet.saving_if_recorded, "7800.00");
  const belowNet = handle("POST", "/installments/preview", near("78000.10", "n2"), "demo-mint").body as PreviewOut;
  assert.equal(belowNet.saving_if_recorded, "0.00");
  const skipped = handle("POST", "/installments", near("78000.10", "n2"), "demo-mint").body as RecordedOut;
  assert.equal(skipped.saved_amount, belowNet.saving_if_recorded);
});

// ---- UI-37: the form's order, the cash kinds behind a link, and the check in the bar --

/** The screen as it draws a form state (kept as a draft, as after "แก้ไข"). */
function render(form: Form): string {
  setDraft({ form, stage: { name: "form" } });
  try {
    return renderToStaticMarkup(createElement(ThinkFirst, { load: { state: "ready", data: { hint: null } }, reload: () => undefined }));
  } finally {
    setDraft(null);
  }
}

const esc = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The <input> that a field's visible label points to. */
function inputFor(html: string, label: string): string {
  const id = new RegExp(`<label for="([^"]+)"[^>]*>${esc(label)}</label>`).exec(html)?.[1];
  assert.ok(id !== undefined, `no label ${label}`);
  const input = new RegExp(`<input[^>]*\\bid="${esc(id)}"[^>]*>`).exec(html)?.[0];
  assert.ok(input !== undefined, `no input for ${label}`);
  return input;
}

const at = (html: string, text: string) => {
  const i = html.indexOf(text);
  assert.ok(i >= 0, `not drawn: ${text}`);
  return i;
};

test("UI_37_the_check_stays_disabled_until_every_required_field_is_valid", () => {
  assert.equal(canPreview(FORM), true);
  const blocked: [keyof Form, string][] = [
    ["price", ""],
    ["price", "1,5"],
    ["months", ""],
    ["months", "0"],
    ["months", "601"],
    ["monthly", ""],
    ["monthly", "12.345"],
    ["firstDue", ""],
  ];
  for (const [field, value] of blocked) assert.equal(canPreview({ ...FORM, [field]: value }), false, `${field}=${value}`);
  // The optional name and app never block it, and a cash item needs the same four.
  assert.equal(canPreview({ ...FORM, name: "", platform: "" }), true);
  assert.equal(canPreview({ ...FORM, kind: "cash_loan" }), true);
});

test("UI_37_money_fields_take_thousands_separators_only_in_valid_groups", () => {
  const entry = (price: string, monthly: string) => toEntry({ ...FORM, price, monthly }, "r");
  const grouped = entry("12,000", "1,200");
  assert.ok(grouped.ok);
  if (grouped.ok) assert.deepEqual([grouped.entry.item_price, grouped.entry.monthly_amount], ["12000", "1200"]);
  const cents = entry("12,000.50", "1,200.05");
  assert.ok(cents.ok);
  if (cents.ok) assert.deepEqual([cents.entry.item_price, cents.entry.monthly_amount], ["12000.50", "1200.05"]);
  // A comma that is not a thousands separator is refused, never dropped: "1,5" is not 15.
  for (const bad of ["1,5", "12,00", "1,2345", ",100", "1,,000"]) {
    const result = entry(bad, "1200");
    assert.equal(result.ok, false, bad);
    if (!result.ok) assert.equal(result.errors.price, MONEY_ERRORS.format, bad);
    assert.equal(canPreview({ ...FORM, price: bad }), false, bad);
  }
  // The 0% suggestion asks with the separators removed, the digits as typed.
  assert.deepEqual(suggestionRequest({ ...FORM, monthly: "", monthlyEdited: false, price: "12,000" }), { price: "12000", months: 10 });
});

test("UI_37_a_field_shows_its_error_once_left_with_something_typed", () => {
  const typed: Form = { ...emptyForm(), price: "1,5" };
  assert.deepEqual(shownErrors(typed, new Set()), {}, "nothing before the user leaves a field");
  // Months is empty: not done yet, which the bar's hint says, not an error.
  assert.deepEqual(shownErrors(typed, new Set(["price", "months"])), { price: MONEY_ERRORS.format });
  // A check that could not be sent shows every error.
  assert.deepEqual(Object.keys(shownErrors(typed, "all")).sort(), ["firstDue", "monthly", "months", "price"]);
  assert.deepEqual(shownErrors(FORM, "all"), {});
});

test("UI_37_every_field_is_in_view_name_and_app_first_then_the_four_the_check_needs", () => {
  const html = render(emptyForm());
  // In this order. The cash link sits just above the price, whose label it changes.
  const order = [
    `>${THINK.itemName}</label>`,
    `>${THINK.platform}</label>`,
    `>${THINK.cashLink}</button>`,
    `>${THINK.price}</label>`,
    `>${THINK.months}</label>`,
    `>${THINK.monthly}</label>`,
    `>${THINK.firstDue}</legend>`,
  ];
  const places = order.map((text) => at(html, text));
  assert.deepEqual([...places].sort((a, b) => a - b), places, "in this order");
  // The two optional fields say so in their labels.
  assert.deepEqual([THINK.itemName, THINK.platform], ["ชื่อสินค้า (ไม่บังคับ)", "แอปที่ผ่อน (ไม่บังคับ)"]);
  // Nothing folded: both take typing from the start, and nothing in the form opens or closes.
  inputFor(html, THINK.itemName);
  inputFor(html, THINK.platform);
  assert.ok(!html.slice(at(html, "<form"), at(html, "</form>")).includes("aria-expanded"), "no fold");
  // A cash kind keeps the order: the name and the app, the kinds, then ยอดเงิน.
  const cash = render({ ...FORM, kind: "cash_loan" });
  assert.ok(at(cash, `>${THINK.platform}</label>`) < at(cash, `>${THINK.kindTitle}</legend>`));
  assert.ok(at(cash, `>${THINK.kindTitle}</legend>`) < at(cash, `>${THINK.cashAmount}</label>`));
});

test("UI_37_purchase_is_preselected_and_the_cash_kinds_wait_behind_a_link", () => {
  assert.equal(emptyForm().kind, "purchase");
  const html = render(emptyForm());
  assert.ok(html.includes(`>${THINK.cashLink}</button>`), "the link");
  assert.ok(!html.includes('name="kind"'), "no kinds until the link is used");
  inputFor(html, THINK.price);
  // A cash kind chosen (a draft): all three kinds, that one checked, the amount label
  // ยอดเงิน, the no-saving note, and no link.
  const cash = render({ ...FORM, kind: "cash_loan" });
  // Attribute by attribute, never their order: each radio with the label after it.
  const kinds = [...cash.matchAll(/<input type="radio"([^>]*)\/><span[^>]*>([^<]+)<\/span>/g)].filter((m) => /\bname="kind"/.test(m[1] ?? ""));
  assert.deepEqual(
    kinds.map((m) => m[2]),
    [THINK.kinds.purchase, THINK.kinds.cash_withdrawal, THINK.kinds.cash_loan],
  );
  assert.deepEqual(kinds.filter((m) => /\bchecked=""/.test(m[1] ?? "")).map((m) => m[2]), [THINK.kinds.cash_loan]);
  // Two to a row, ผ่อนสินค้า on its own: no label is squeezed in the 370px desktop frame.
  assert.match(cash, /<div class="grid grid-cols-2 gap-2"><label class="[^"]*\bcol-span-2\b[^"]*"><input type="radio"[^>]*name="kind"/);
  inputFor(cash, THINK.cashAmount);
  assert.equal(THINK.cashAmount, "ยอดเงิน");
  assert.ok(cash.includes(THINK.cashNoSaving) && !cash.includes(THINK.cashLink));
});

test("UI_37_money_fields_open_the_decimal_keyboard_and_months_the_numeric_one", () => {
  const html = render(emptyForm());
  assert.match(inputFor(html, THINK.price), /inputmode="decimal"/i);
  assert.match(inputFor(html, THINK.monthly), /inputmode="decimal"/i);
  assert.match(inputFor(html, THINK.months), /inputmode="numeric"/i);
  // Text inputs, never a number input: the browser cannot turn money into a float.
  for (const label of [THINK.price, THINK.monthly, THINK.months]) assert.match(inputFor(html, label), /type="text"/);
  // The placeholder shows a form the field takes ("12,000" above).
  assert.match(inputFor(html, THINK.price), /placeholder="เช่น 12,000"/);
});

test("UI_37_month_chips_are_3_6_10_12_and_fill_the_field", () => {
  assert.deepEqual([...MONTH_CHIPS], [3, 6, 10, 12]);
  const html = render({ ...FORM, months: "10" });
  const chips = [...html.matchAll(/<button type="button" aria-pressed="(true|false)"[^>]*>([0-9]+) เดือน<\/button>/g)].map((m) => [m[2], m[1]]);
  assert.deepEqual(chips, [["3", "false"], ["6", "false"], ["10", "true"], ["12", "false"]]);
  // Under the months field, which still takes typing (no readonly): 24 is no chip.
  assert.ok(at(html, ">จำนวนเดือนที่ผ่อน</label>") < at(html, ">3 เดือน</button>"));
  assert.ok(at(html, ">12 เดือน</button>") < at(html, ">ค่างวดต่อเดือน</label>"));
  assert.doesNotMatch(inputFor(html, THINK.months), /readonly/i);
  assert.ok(!render({ ...FORM, months: "24" }).includes('aria-pressed="true"'));
  // A tap puts the chip's number in the field, so the 0% suggestion asks for it.
  assert.equal(suggestionRequest({ ...FORM, months: String(MONTH_CHIPS[1]), monthly: "", monthlyEdited: false })?.months, 6);
});

test("UI_37_the_check_sits_in_the_bar_above_the_nav_and_waits_for_the_four_fields", () => {
  const empty = render(emptyForm());
  const formId = /<form id="([^"]+)"/.exec(empty)?.[1];
  const button = /<button type="submit" form="([^"]+)"([^>]*)>/.exec(empty);
  assert.ok(formId !== undefined && button !== null);
  assert.equal(button[1], formId, "the bar's button submits the form");
  // Outside the scrolling body, before the nav: always in view.
  assert.ok(at(empty, "</main>") < button.index && button.index < at(empty, "<nav"));
  // Disabled, and it says why. The attribute, not the class's "disabled:" variant.
  assert.match(button[2] ?? "", /\sdisabled=""/);
  const why = /aria-describedby="([^"]+)"/.exec(button[2] ?? "")?.[1];
  assert.ok(why !== undefined);
  assert.ok(empty.includes(`<p id="${why}" class="text-center text-body text-ink-muted">${THINK.checkNeeds}</p>`));
  // The four valid: enabled, and the hint is gone.
  const ready = /<button type="submit" form="[^"]+"([^>]*)>/.exec(render(FORM))?.[1] ?? "";
  assert.doesNotMatch(ready, /\sdisabled=""|\saria-describedby=/);
  assert.ok(!render(FORM).includes(THINK.checkNeeds));
});

test("UI_37_before_the_form_is_ready_the_same_screen_shows_no_check_bar", () => {
  // ThinkFirst draws the screen in every state, so it stays one screen (one header,
  // one bell) from loading to the form; the bar joins only with the form.
  // A kept draft gives the form its first state (no deep link to read from the URL).
  const draw = (load: Parameters<typeof ThinkFirst>[0]["load"]) => {
    setDraft({ form: emptyForm(), stage: { name: "form" } });
    try {
      return renderToStaticMarkup(createElement(ThinkFirst, { load, reload: () => undefined }));
    } finally {
      setDraft(null);
    }
  };
  for (const [name, html] of [
    ["loading", draw({ state: "loading" })],
    ["error", draw({ state: "error", error: new Error("x") })],
    ["no settings", draw({ state: "ready", data: null })],
  ] as const) {
    assert.ok(html.includes(`>${THINK.title}</h1>`) && html.includes("<nav"), `${name}: the screen`);
    assert.ok(!html.includes("<form") && !html.includes('type="submit"'), `${name}: no form, no bar`);
  }
  assert.ok(draw({ state: "error", error: new Error("x") }).includes(`>${COMMON.retry}</button>`));
  assert.ok(draw({ state: "ready", data: null }).includes(COMMON.settingsMissingTitle));
});
