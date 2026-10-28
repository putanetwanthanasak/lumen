/** The bottom nav (UI-25): one selected shape for every tab, short one-line labels. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { SOLID } from "../src/accent.ts";
import { NAV, THINK } from "../src/copy.ts";
import { NAV_RAISE, NAV_TABS, navFill, navIconClass, navLabelClass, SCROLL_PAD_WITH_NAV } from "../src/navStyle.ts";

// Class by class, never a substring of a whole look (round 1 review F6): the bg- of
// each filled look in accent.ts.
const classes = (cls: string) => cls.split(/\s+/);
const FILLS = [SOLID.debt, SOLID.buffer].flatMap((look) => classes(look).filter((c) => c.startsWith("bg-")));

test("UI_25_every_tab_looks_selected_only_when_it_is_selected", () => {
  assert.deepEqual(FILLS, ["bg-leaf-700", "bg-teal-700"]);
  for (const { route } of NAV_TABS) {
    // Selected: the filled icon background and a bold label, the same shape on every tab.
    assert.ok(navIconClass(route, true).includes(navFill(route)), `${route} selected`);
    assert.ok(classes(navLabelClass(route, true)).includes("font-bold"), `${route} label selected`);
    // Not selected: no fill of either colour, no white icon, never bold.
    const off = classes(navIconClass(route, false));
    for (const cls of [...FILLS, "text-white"]) assert.ok(!off.includes(cls), `${route} not selected has ${cls}`);
    assert.ok(!classes(navLabelClass(route, false)).includes("font-bold"), `${route} label not selected`);
  }
  // The centre tab, not selected, is an outline on white.
  assert.ok(classes(navIconClass("think", false)).includes("bg-card"));
});

test("UI_25_the_buffer_tab_is_teal_and_the_others_green", () => {
  // A colour always means the same feature (DESIGN.md section 4): teal is the buffer.
  assert.equal(navFill("buffer"), SOLID.buffer);
  assert.equal(navFill("home"), SOLID.debt);
  assert.equal(navFill("think"), SOLID.debt);
  assert.ok(navLabelClass("buffer", true).includes("text-teal-800"));
  assert.ok(navLabelClass("home", true).includes("text-leaf-800"));
});

test("UI_25_nav_labels_are_short_and_never_wrap", () => {
  const labels = [NAV.home, NAV.think, NAV.buffer];
  assert.deepEqual(labels, ["หน้าหลัก", "เช็กก่อนผ่อน", "กันชน"]);
  // Count the characters that take space: Thai vowel and tone marks above or below
  // a letter take none. Measured in Chrome at 14px: "เช็กก่อนผ่อน" (9) is 74px, one
  // line in a 130px tab at 390px (120px at 360px). 10 keeps that margin.
  const wide = (label: string) => [...label].filter((c) => !/[ัิ-ฺ็-๎]/.test(c)).length;
  assert.equal(wide("เช็กก่อนผ่อน"), 9);
  for (const label of labels) assert.ok(wide(label) <= 10, label);
  for (const { route } of NAV_TABS) {
    for (const active of [true, false]) assert.ok(navLabelClass(route, active).includes("whitespace-nowrap"));
  }
  // The tab and the screen use the same name.
  assert.equal(THINK.title, "เช็กก่อนผ่อน");
});

test("UI_27_the_scroll_area_clears_the_raised_centre_button", () => {
  // Tailwind spacing steps are 4px. The padding must cover the raise plus 24px.
  const step = (cls: string, re: RegExp) => Number(re.exec(cls)?.[1] ?? Number.NaN) * 4; // ui-06-allow: layout pixels
  const raise = step(NAV_RAISE, /^-mt-(\d+)$/);
  const pad = step(SCROLL_PAD_WITH_NAV, /^pb-(\d+)$/);
  assert.ok(navIconClass("think", false).includes(NAV_RAISE));
  assert.ok(pad >= raise + 24, `padding ${pad}px vs raise ${raise}px`);
});
