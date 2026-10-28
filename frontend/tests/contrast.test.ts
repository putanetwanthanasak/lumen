/**
 * UI-35: every colour pair the accents use is readable (WCAG 2.2), measured from the
 * tokens in src/index.css: text at least 4.5:1, bars, meters and meaningful icons at
 * least 3:1 (1.4.11). Colour maths, not money: floating point is fine here.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const TOKENS = new Map(
  [...readFileSync("src/index.css", "utf8").matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-f]{6});/g)].map((m) => [m[1] ?? "", m[2] ?? ""]),
);
TOKENS.set("white", "#ffffff");

function luminance(name: string): number {
  const hex = TOKENS.get(name);
  if (hex === undefined) throw new Error(`no token --color-${name}`);
  const [r = 0, g = 0, b = 0] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

// [foreground, background], as the screens draw them.
const TEXT: [string, string][] = [
  ["ink", "card"],
  ["ink-muted", "card"],
  ["ink-muted", "surface"],
  ["white", "leaf-700"],
  ["leaf-800", "card"],
  ["ok-ink", "card"],
  ["warn-ink", "warn-bg"],
  ["warn-ink", "card"], // the month chips
  ["ink", "warn-bg"],
  ["teal-800", "teal-50"],
  ["teal-800", "card"],
  ["teal-800", "warn-bg"], // the strip's buffer line
  ["white", "teal-700"],
  ["ink", "teal-50"],
  ["ink-muted", "teal-50"],
  ["leaf-800", "teal-50"], // header icons on the buffer screen's tinted header
  ["bank-800", "bank-50"],
  ["bank-800", "card"],
  ["ink", "bank-50"],
  ["ink-muted", "bank-50"],
  ["ai-ink", "ai-from"],
  ["ai-ink", "ai-to"],
  ["ai-ink", "card"],
  ["ink", "ai-from"],
  ["ink", "ai-to"],
  ["quiet-ink", "quiet-bg"],
  ["ink", "quiet-bg"],
];

const GRAPHICS: [string, string][] = [
  ["bar-ok", "leaf-50"], // the hero's bar on its track
  ["bar-over", "leaf-50"],
  ["teal-700", "teal-50"], // the wallet's filled segment and icon
  ["teal-700", "teal-200"], // filled against empty segments
  ["teal-700", "warn-bg"], // the shield on the amber strip
  ["bank-700", "bank-50"], // the offer's button border
  ["ai-ink", "ai-from"],
];

test("UI_35_every_accent_text_pair_is_at_least_4_5_to_1", () => {
  const low = TEXT.filter(([fg, bg]) => ratio(fg, bg) < 4.5).map(([fg, bg]) => `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`);
  assert.deepEqual(low, []);
});

test("UI_35_bars_meters_and_icons_are_at_least_3_to_1", () => {
  const low = GRAPHICS.filter(([fg, bg]) => ratio(fg, bg) < 3).map(([fg, bg]) => `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`);
  assert.deepEqual(low, []);
});

test("UI_35_the_measure_matches_known_values", () => {
  // Guard the guard: black on white is 21:1, a colour on itself 1:1.
  TOKENS.set("black", "#000000");
  assert.equal(ratio("black", "white").toFixed(2), "21.00");
  assert.equal(ratio("teal-700", "teal-700").toFixed(2), "1.00");
});
