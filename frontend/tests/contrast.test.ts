/**
 * UI-35: every colour pair the accents use is readable (WCAG 2.2), measured from the
 * tokens in src/index.css: text at least 4.5:1, bars, meters and meaningful icons at
 * least 3:1, and the edge of every tinted card at least 3:1 against the page (1.4.11).
 * Colour maths, not money: floating point is fine here.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { EDGE, SOLID } from "../src/accent.ts";

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
  ["warn-ink", "card"], // the hero's warning line
  ["ink", "warn-bg"],
  ["teal-800", "teal-50"],
  ["teal-800", "card"], // the hero's buffer line and its link
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
  ["white", "bank-700"], // the offer's title on its solid header band
  // The hero while hovered (leaf-50): every text and icon in it.
  ["ink", "leaf-50"],
  ["ink-muted", "leaf-50"],
  ["leaf-800", "leaf-50"],
  ["warn-ink", "leaf-50"],
  ["teal-800", "leaf-50"],
  // The host shell (#/account, Session 21): white and muted text on every host colour,
  // the gradient's two ends included (the text can sit anywhere on it).
  ["white", "host-from"],
  ["white", "host-to"],
  ["white", "host-card"],
  ["white", "host-bar"],
  ["host-muted", "host-from"],
  ["host-muted", "host-to"],
  ["host-muted", "host-card"],
  ["host-muted", "host-bar"],
  // Session 22: the passbook card's text sits on the card and on its ruled lines (the
  // spine carries no text, but is measured too); the selected tab is host-bar ink on
  // white; the "ใหม่" badge and the note strip are white on host-bar.
  ["white", "host-rule"],
  ["white", "host-spine"],
  ["host-muted", "host-rule"],
  ["host-muted", "host-spine"],
  ["host-bar", "card"],
];

const GRAPHICS: [string, string][] = [
  ["bar-ok", "leaf-50"], // the hero's bar on its track; bar-ok, bar-over and bar-risk on card also cover the white gap between a month bar's parts
  ["bar-over", "leaf-50"],
  ["bar-risk", "leaf-50"], // the hero's gap over one third of income (UI-52)
  ["ink", "leaf-50"], // the hero's budget mark, on the track and on either colour
  ["ink", "bar-ok"],
  ["ink", "bar-over"],
  ["bar-ok", "card"], // the result's new item's share, on the card and against the white gap (UI-40)
  ["bar-over", "card"],
  ["bar-risk", "card"],
  ["bar-existing", "card"], // the grey of every other installment, on the card and against the white gap
  ["risk-ink", "card"], // the ⚠ above a bar over one third of income
  ["ink-muted", "card"], // the dashed budget line
  ["teal-700", "teal-50"], // the wallet's filled segment and icon
  ["teal-700", "teal-200"], // filled against empty segments
  ["teal-700", "card"], // a month bar's buffer part (BUFFER_BAR, UI-52), on the months' card and against the 2px white gap between parts (UI-54)
  ["teal-700", "leaf-50"], // and on the hero's track
  ["white", "teal-700"], // the hero's budget mark has a white halo against the buffer part (ink on teal-700 is 2.6:1)
  ["bank-700", "bank-50"], // the offer's button border
  ["ai-ink", "ai-from"],
  // The host shell: the account card's and the shortcuts' edges, and the bar's top
  // line, against the gradient; the white cards against it; the selected underline.
  ["host-line", "host-from"],
  ["host-line", "host-to"],
  ["host-line", "host-bar"],
  ["card", "host-from"],
  ["card", "host-to"],
  ["white", "host-bar"],
  // Session 22: the tabs' and the round profile button's edges, and the empty page
  // dots, against the page; the filled dot and the selected tab (white) against it.
  ["host-line", "host-card"],
  ["host-line", "host-spine"],
  ["host-line", "host-rule"],
];

// Decoration, not meaning: the passbook's rules and spine are meant to be faint against
// the card (they must never compete with the text), so they stay under 1.5:1 (UI-68).
const FAINT: [string, string][] = [
  ["host-rule", "host-card"],
  ["host-spine", "host-card"],
];

test("UI_35_every_accent_text_pair_is_at_least_4_5_to_1", () => {
  const low = TEXT.filter(([fg, bg]) => ratio(fg, bg) < 4.5).map(([fg, bg]) => `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`);
  assert.deepEqual(low, []);
});

test("UI_35_bars_meters_and_icons_are_at_least_3_to_1", () => {
  const low = GRAPHICS.filter(([fg, bg]) => ratio(fg, bg) < 3).map(([fg, bg]) => `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`);
  assert.deepEqual(low, []);
});

test("UI_35_the_passbook_decoration_stays_faint_behind_the_text", () => {
  const loud = FAINT.filter(([fg, bg]) => ratio(fg, bg) >= 1.5).map(([fg, bg]) => `${fg} on ${bg}: ${ratio(fg, bg).toFixed(2)}`);
  assert.deepEqual(loud, []);
});

// The colour token of a border class list: "border-2 border-bank-700" -> "bank-700".
const borderToken = (cls: string) => cls.split(/\s+/).flatMap((c) => /^border-(?!\d)([a-z0-9-]+)$/.exec(c)?.slice(1) ?? []);

test("UI_35_every_tinted_card_edge_stands_out_from_the_page_at_least_3_to_1", () => {
  // The offer card, the assistant's panel, the consolidation banner and the buffer's
  // wallet meet the page (surface) at their edge; the light tints alone blend into it.
  assert.deepEqual(Object.keys(EDGE).sort(), ["ai", "bank", "buffer", "quiet"]);
  const low = Object.entries(EDGE).flatMap(([accent, cls]) => {
    const [token] = borderToken(cls);
    if (token === undefined) return [`${accent}: no border colour in "${cls}"`];
    return ["surface", "card"].filter((bg) => ratio(token, bg) < 3).map((bg) => `${accent} ${token} on ${bg}: ${ratio(token, bg).toFixed(2)}`);
  });
  assert.deepEqual(low, []);
  // The band under the offer's title is solid bank-700 with white text (4.5:1 above).
  assert.ok(SOLID.bank.split(" ").includes("bg-bank-700") && SOLID.bank.split(" ").includes("text-white"), SOLID.bank);
});

test("UI_35_the_edge_check_catches_the_light_lines_it_replaced", () => {
  // Guard the guard: the borders these cards had before blend into the page.
  for (const old of ["bank-200", "ai-line", "quiet-line", "warn-line", "teal-100"]) {
    assert.ok(ratio(old, "surface") < 3, `${old}: ${ratio(old, "surface").toFixed(2)}`);
  }
  assert.deepEqual(borderToken("border-2 border-bank-700"), ["bank-700"]);
  assert.deepEqual(borderToken("border border-ai-edge"), ["ai-edge"]);
  assert.deepEqual(borderToken(EDGE.buffer), ["teal-edge"]);
});

test("UI_35_the_measure_matches_known_values", () => {
  // Guard the guard: black on white is 21:1, a colour on itself 1:1.
  TOKENS.set("black", "#000000");
  assert.equal(ratio("black", "white").toFixed(2), "21.00");
  assert.equal(ratio("teal-700", "teal-700").toFixed(2), "1.00");
});
