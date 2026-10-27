/** The bottom nav (UI-25): one selected look for every tab, short one-line labels. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { NAV, PAYOFF, THINK } from "../src/copy.ts";
import { NAV_SELECTED_FILL, navIconClass, navLabelClass } from "../src/navStyle.ts";

test("UI_25_the_centre_tab_looks_selected_only_when_it_is_selected", () => {
  for (const primary of [true, false]) {
    assert.ok(navIconClass(primary, true).includes(NAV_SELECTED_FILL), `primary=${primary} selected`);
    assert.ok(!navIconClass(primary, false).includes("bg-leaf-700"), `primary=${primary} not selected`);
  }
  assert.ok(navLabelClass(true).includes("font-bold"));
  assert.ok(!navLabelClass(false).includes("font-bold"));
});

test("UI_25_nav_labels_are_short_and_never_wrap", () => {
  const labels = [NAV.home, NAV.think, NAV.buffer, NAV.payoff];
  assert.deepEqual(labels, ["หน้าหลัก", "ตรวจสอบ", "กันชน", "ปลดหนี้"]);
  // A quarter of 390px holds about 8 Thai characters at 14px; checked in the browser too.
  for (const label of labels) assert.ok([...label].length <= 8, label);
  for (const active of [true, false]) assert.ok(navLabelClass(active).includes("whitespace-nowrap"));
  // The full names stay on the screens themselves.
  assert.equal(THINK.title, "ตรวจสอบก่อนผ่อน");
  assert.equal(PAYOFF.title, "ผู้ช่วยปลดหนี้");
});
