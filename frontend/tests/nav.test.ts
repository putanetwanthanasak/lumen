/**
 * The bottom nav (UI-25): one selected shape for every tab, short one-line labels.
 * UI-27: the raised centre button, never hiding what scrolls and never hidden by it.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { SOLID } from "../src/accent.ts";
import { Screen } from "../src/components/Screen.tsx";
import { NAV, THINK } from "../src/copy.ts";
import {
  ACTIONS_PAD_WITH_NAV,
  ACTIONS_PAD_WITHOUT_NAV,
  bottomPads,
  NAV_RAISE,
  NAV_TABS,
  navFill,
  navIconClass,
  navLabelClass,
  SCROLL_PAD_WITH_NAV,
  SCROLL_PAD_WITHOUT_NAV,
} from "../src/navStyle.ts";

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
  assert.deepEqual(bottomPads(true, false), { main: SCROLL_PAD_WITH_NAV, actions: ACTIONS_PAD_WITH_NAV });
});

test("UI_27_an_action_bar_above_the_nav_clears_the_raised_centre_button", () => {
  // เช็กก่อนผ่อน (UI-37): the check sits in a bar between the body and the nav, so the
  // raised button reaches into the bar, not the body. Its button keeps 12px clear.
  const step = (cls: string, re: RegExp) => Number(re.exec(cls)?.[1] ?? Number.NaN) * 4; // ui-06-allow: layout pixels
  const raise = step(NAV_RAISE, /^-mt-(\d+)$/);
  const withNav = bottomPads(true, true);
  assert.equal(withNav.main, SCROLL_PAD_WITHOUT_NAV);
  assert.equal(withNav.actions, ACTIONS_PAD_WITH_NAV);
  const pad = step(withNav.actions, /^pb-(\d+)$/);
  assert.ok(pad >= raise + 12, `bar padding ${pad}px vs raise ${raise}px`);
  // No nav (the result's บันทึก / ยังไม่ซื้อ): a plain bar.
  assert.deepEqual(bottomPads(false, true), { main: SCROLL_PAD_WITHOUT_NAV, actions: ACTIONS_PAD_WITHOUT_NAV });
  assert.equal(bottomPads(false, false).main, SCROLL_PAD_WITHOUT_NAV);
});

// The raised centre button reaches 16px up into the body (or the form's bar). CSS draws
// a box that is positioned or has its own layer (the assistant's bubble is `relative`
// for its tail, the uncounted rows `opacity-80`) after every plain box, whatever comes
// later in the page, so such a card covered the raised button as it scrolled under it.

/** A screen's shell as drawn, with one line in its body (react-dom/server, no browser). */
function shell(withBar: boolean, showNav = true): string {
  const bar = withBar ? { actions: createElement("button", { type: "button" }, "bar") } : {};
  return renderToStaticMarkup(createElement(Screen, { route: "home", showNav, ...bar, children: createElement("p", null, "body") }));
}

test("UI_27_the_body_the_bar_and_the_nav_are_each_a_layer_drawn_in_that_order", () => {
  // What the screen draws after its body.
  const afterBody = (html: string) => html.slice(html.indexOf("</main>") + "</main>".length);
  // The body is its own layer: nothing inside it is ever drawn over what follows it.
  const home = shell(false);
  assert.match(home, /<main tabindex="0" class="phone-scroll isolate /);
  // The nav follows it, its own layer too, and is the last thing drawn: always on top.
  assert.match(afterBody(home), /^<nav [^>]*class="isolate /);
  assert.ok(home.endsWith("</nav></div>"), "the nav is drawn last");
  // With the check's bar (the form): the body, the bar, then the nav, each a layer.
  const form = shell(true);
  assert.match(afterBody(form), /^<div class="isolate [^"]*"><button type="button">bar<\/button><\/div><nav [^>]*class="isolate /);
  assert.ok(form.endsWith("</nav></div>"), "the nav is drawn last");
  // No nav (the result's บันทึก / ยังไม่ซื้อ): the bar, a layer, is drawn last.
  assert.match(afterBody(shell(true, false)), /^<div class="isolate [^"]*"><button type="button">bar<\/button><\/div><\/div>$/);
});
