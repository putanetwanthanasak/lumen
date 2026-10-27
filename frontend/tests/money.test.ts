/**
 * Money on the client is display only (DESIGN.md section 3). Run: npm test.
 * UI-01 to UI-04 are critical (money) and have break tests in the progress log.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { barPermille, formatAmount, formatBaht, largest, MoneyFormatError, parseMoneyInput } from "../src/money.ts";

test("UI_01_format_baht_groups_thousands_by_string_operations", () => {
  assert.equal(formatBaht("1500.00"), "1,500.00 บาท");
  assert.equal(formatBaht("0.50"), "0.50 บาท");
  assert.equal(formatBaht("0.00"), "0.00 บาท");
  assert.equal(formatBaht("999.99"), "999.99 บาท");
  assert.equal(formatBaht("1000.00"), "1,000.00 บาท");
  assert.equal(formatBaht("1234567.89"), "1,234,567.89 บาท");
  // Above 2**53 satang a float would lose the last digits; strings do not.
  assert.equal(formatAmount("9999999999.99"), "9,999,999,999.99");
  assert.equal(formatAmount("90071992547409.93"), "90,071,992,547,409.93");
});

test("UI_01_format_baht_pads_short_decimals_without_rounding", () => {
  assert.equal(formatBaht("1500"), "1,500.00 บาท");
  assert.equal(formatBaht("1500.5"), "1,500.50 บาท");
  assert.equal(formatBaht("0.1"), "0.10 บาท");
});

test("UI_02_format_baht_refuses_anything_that_is_not_an_api_money_string", () => {
  for (const bad of ["", " 1", "1 ", "1e3", "1.234", "-1.00", "+1.00", "01.00", "1,000.00", "NaN", "Infinity", "1.", ".5", "๑๒"]) {
    assert.throws(() => formatBaht(bad), MoneyFormatError, `should refuse ${JSON.stringify(bad)}`);
  }
});

test("UI_03_typed_money_is_kept_as_typed_and_never_rounded", () => {
  assert.deepEqual(parseMoneyInput("12000"), { ok: true, value: "12000" });
  assert.deepEqual(parseMoneyInput("12,000.50"), { ok: true, value: "12000.50" });
  assert.deepEqual(parseMoneyInput("  1200.5 "), { ok: true, value: "1200.5" });
  assert.deepEqual(parseMoneyInput("0.01"), { ok: true, value: "0.01" });
  assert.deepEqual(parseMoneyInput("007"), { ok: true, value: "7" });
  assert.deepEqual(parseMoneyInput("9999999999.99"), { ok: true, value: "9999999999.99" });
});

test("UI_03_typed_money_is_refused_with_a_reason", () => {
  assert.deepEqual(parseMoneyInput(""), { ok: false, reason: "empty" });
  assert.deepEqual(parseMoneyInput("   "), { ok: false, reason: "empty" });
  // L49: more than 2 decimals is refused, never rounded to 1200.56.
  assert.deepEqual(parseMoneyInput("1200.555"), { ok: false, reason: "decimals" });
  assert.deepEqual(parseMoneyInput("0.001"), { ok: false, reason: "decimals" });
  for (const bad of ["1e3", "-5", "abc", "12.", ".5", "1.2.3", "12 000", "๑๒๐๐"]) {
    assert.deepEqual(parseMoneyInput(bad), { ok: false, reason: "format" }, bad);
  }
  assert.deepEqual(parseMoneyInput("0"), { ok: false, reason: "zero" });
  assert.deepEqual(parseMoneyInput("0.00"), { ok: false, reason: "zero" });
  assert.deepEqual(parseMoneyInput("10000000000"), { ok: false, reason: "too_large" });
});

test("UI_04_bar_height_is_exact_per_mille_rounded_down", () => {
  assert.equal(barPermille("4700.00", "5000.00"), 940);
  assert.equal(barPermille("5000.00", "5000.00"), 1000);
  assert.equal(barPermille("0.00", "5000.00"), 0);
  // 1/3 = 333.33... per mille: rounded down, not to nearest.
  assert.equal(barPermille("1.00", "3.00"), 333);
  assert.equal(barPermille("2.00", "3.00"), 666);
  // 0.01 below the scale must not reach 1000 (a float could round it up).
  assert.equal(barPermille("9999999999.98", "9999999999.99"), 999);
});

test("UI_04_bar_height_caps_at_1000_and_a_zero_scale_draws_nothing", () => {
  assert.equal(barPermille("6500.00", "5000.00"), 1000);
  assert.equal(barPermille("100.00", "0.00"), 0);
  assert.throws(() => barPermille("1.5e3", "5000.00"), MoneyFormatError);
});

test("UI_04_largest_compares_exactly", () => {
  assert.equal(largest(["4700.00", "5000.00", "4999.99"]), "5000.00");
  assert.equal(largest(["5000.01", "5000.00"]), "5000.01");
  assert.equal(largest([]), "0.00");
});
