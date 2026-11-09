/**
 * UI-35: every colour pair the accents use is readable (WCAG 2.2), measured from the
 * tokens in src/index.css: text at least 4.5:1, bars, meters and meaningful icons at
 * least 3:1, and the edge of every tinted card at least 3:1 against the page (1.4.11).
 * Colour maths, not money: floating point is fine here.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { EDGE, HOST, SOLID } from "../src/accent.ts";

const TOKENS = new Map(
  [...readFileSync("src/index.css", "utf8").matchAll(/--color-([a-z0-9-]+):\s*(#[0-9a-f]{6});/g)].map((m) => [m[1] ?? "", m[2] ?? ""]),
);
TOKENS.set("white", "#ffffff");

/** `fg` at `alpha` over `bg`, as the browser paints a translucent fill. */
function over(fg: string, alpha: number, bg: string): string {
  const [f, b] = [fg, bg].map((name) => {
    const hex = TOKENS.get(name);
    if (hex === undefined) throw new Error(`no token --color-${name}`);
    return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  });
  return `#${[0, 1, 2].map((i) => Math.round((f?.[i] ?? 0) * alpha + (b?.[i] ?? 0) * (1 - alpha)).toString(16).padStart(2, "0")).join("")}`;
}
// The printed line's band is white at 75% over the paper (HOST.band): over its pattern
// (the darkest point behind the print) and over the bare paper.
TOKENS.set("band-on-pattern", over("white", 0.75, "host-pattern"));
TOKENS.set("band-on-paper", over("white", 0.75, "host-paper"));

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
  // Session 22: the selected tab is host-bar ink on white; the "ใหม่" badge and the note
  // strip are white on host-bar.
  ["host-bar", "card"],
  // Session 23, the passbook page: every text on the paper and on its pattern's darkest
  // point (the title, the number and the balance in ink; the labels, "บาท" and the demo
  // line in ink-muted; the icon and the link in leaf-800), and the print ink on the band
  // over the pattern and over the paper.
  ["ink", "host-paper"],
  ["ink", "host-pattern"],
  ["ink-muted", "host-paper"],
  ["ink-muted", "host-pattern"],
  ["leaf-800", "host-paper"],
  ["leaf-800", "host-pattern"],
  ["host-print", "band-on-pattern"],
  ["host-print", "band-on-paper"],
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
  // Session 22: a shortcut's edge on its hover fill. The tabs', the profile button's and
  // the empty dots' edges against the page are the host-line on host-from and host-to
  // rows above; the selected tab and the filled dot (white) are the card on host-from
  // and host-to rows.
  ["host-line", "host-card"],
  // Session 23: the passbook page's edge against the page, and the ink focus ring on the
  // paper and on its pattern.
  ["host-paper", "host-from"],
  ["host-paper", "host-to"],
  ["ink", "host-paper"],
  ["ink", "host-pattern"],
];

// Decoration, not meaning: the passbook's pattern and the band's rules are meant to be
// faint against the paper (they must never compete with the text), so they stay under
// 1.5:1 (UI-68).
const FAINT: [string, string][] = [
  ["host-pattern", "host-paper"],
  ["host-band-rule", "host-paper"],
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
  // The pattern is the darkest point behind the text, so the pairs above measure the worst case.
  assert.ok(luminance("host-pattern") < luminance("host-paper"));
  // The band measured above is the band the card draws: white at 75%, print ink, and
  // the paper's focus ring is ink.
  for (const cls of ["bg-white/75", "text-host-print"]) assert.ok(HOST.band.split(" ").includes(cls), HOST.band);
  assert.ok(HOST.paperFocus.split(" ").includes("focus-visible:outline-ink"), HOST.paperFocus);
  // Guard the guard: the blend of white over black at 75% is #bfbfbf.
  TOKENS.set("black", "#000000");
  assert.equal(over("white", 0.75, "black"), "#bfbfbf");
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
