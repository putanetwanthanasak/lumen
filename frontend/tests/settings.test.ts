/** The settings form (screen 1): UI-11. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { EMPTY, toRequest, type Form } from "../src/settingsForm.ts";

const FILLED: Form = { ...EMPTY, income: "20000", payday: "25", budget: "5000", consent: true };

test("UI_11_auto_save_off_saves_even_when_the_hidden_rule_field_is_empty", () => {
  // Review F3: with auto-save off the rule fields are hidden, so an error on them
  // could never be seen and the form could never be saved.
  for (const hidden of [
    { mode: "fixed" as const, fixed: "" },
    { mode: "percent" as const, percent: "" },
    { mode: "percent" as const, percent: "500" },
  ]) {
    const result = toRequest({ ...FILLED, ...hidden, autoSave: false, consent: false });
    assert.equal(result.ok, true, JSON.stringify(hidden));
    if (result.ok) {
      assert.equal(result.body.auto_save_enabled, false);
      assert.equal(result.body.auto_save_consent, false);
    }
  }
});

test("UI_11_auto_save_on_still_checks_the_rule_and_the_consent", () => {
  const empty = toRequest({ ...FILLED, mode: "fixed", fixed: "" });
  assert.equal(empty.ok, false);
  if (!empty.ok) assert.ok(empty.errors.fixed !== undefined);
  const noConsent = toRequest({ ...FILLED, consent: false });
  assert.equal(noConsent.ok, false);
  if (!noConsent.ok) assert.ok(noConsent.errors.consent !== undefined);
});

test("UI_11_exactly_one_saving_mode_is_sent", () => {
  const fixed = toRequest({ ...FILLED, mode: "fixed", fixed: "200", percent: "10" });
  assert.deepEqual(fixed.ok && fixed.body.saving_rule, { mode: "fixed", amount: "200" });
  const percent = toRequest({ ...FILLED, mode: "percent", percent: "10", fixed: "200" });
  assert.deepEqual(percent.ok && percent.body.saving_rule, { mode: "percent", percent: 10 });
});

test("UI_11_first_save_retried_after_a_lost_answer_still_saves", async () => {
  // Review round 2, F6: the first POST was saved but its answer was lost, so the
  // screen still thinks nothing exists. The retry must not fail with 409 forever.
  const { resetMock, handle } = await import("../src/mock/server.ts");
  const { saveSettings } = await import("../src/api.ts");
  resetMock(new Date(2026, 9, 27));
  const result = toRequest(FILLED);
  assert.ok(result.ok);
  assert.equal(handle("POST", "/settings", result.body, "demo-mon").status, 201); // answer "lost"
  const saved = await saveSettings({ ...result.body, payday: 1 }, false);
  assert.equal(saved.payday, 1);
});
