/**
 * Home's "ผู้ช่วย KidNee สรุปให้ฟัง" card on GET /assistant/summary (Session 18):
 * AI-18: the text shows the same way whether the model or the app worded it, with no
 *   "ตัวอย่าง" tag, and nothing on screen reads `source` or `reason`.
 * AI-19: a loading state while the answer is on its way.
 * AI-20: a failed request (network, 5xx, or an answer without text) shows the plan's
 *   own words: never an error, a retry or an empty card. The mock answers the GET as
 *   the backend does without a key.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { afterEach, beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { getAssistantSummary } from "../src/api.ts";
import type { AssistantPlanOut, AssistantSummaryOut } from "../src/api-types.ts";
import { planSummary } from "../src/assistantText.ts";
import { AiBubbleCard } from "../src/components/AssistantCards.tsx";
import { ASSIST } from "../src/copy.ts";
import { aiBubble } from "../src/homeLayout.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
const plan = () => call("GET", "/assistant/plan").body as AssistantPlanOut;
const SCENES = ["persona", "over_budget", "over_budget_now", "over_budget_empty_buffer"];
const realFetch = globalThis.fetch;
const card = () => {
  const src = readFileSync("src/components/AssistantCards.tsx", "utf8");
  return src.slice(src.indexOf("export function AiBubbleCard"));
};

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));
afterEach(() => {
  globalThis.fetch = realFetch;
});

// ---- AI-18: one look for the model's words and the app's own ----------------------------

test("AI_18_the_models_words_and_the_apps_own_show_the_same_way", () => {
  const p = plan();
  const text = "เดือน ต.ค. 2569 ค่างวดรวม 3,500.00 บาท\nทุกเดือนอยู่ในงบ";
  const answers: AssistantSummaryOut[] = [
    { text, source: "ai", reason: "ok" },
    { text, source: "fallback", reason: "no_key" },
    { text, source: "fallback", reason: "grounding_failed" },
  ];
  const bubbles = answers.map((data) => aiBubble({ state: "ready", data }, p));
  for (const bubble of bubbles) assert.deepEqual(bubble, bubbles[0]);
  assert.deepEqual(bubbles[0], { state: "done", first: "เดือน ต.ค. 2569 ค่างวดรวม 3,500.00 บาท", rest: ["ทุกเดือนอยู่ในงบ"] });
});

test("AI_18_no_example_tag_and_nothing_reads_source_or_reason", () => {
  const src = card();
  for (const banned of ["ExampleTag", "ตัวอย่าง", "source", "reason", "is_example"]) {
    assert.ok(!src.includes(banned), `the AI card must not use ${banned}`);
  }
  assert.ok(!("aiExample" in ASSIST), "the ตัวอย่าง tag's copy is gone");
  const html = renderToStaticMarkup(createElement(AiBubbleCard, { plan: plan() }));
  assert.ok(html.includes(ASSIST.aiTitle));
  assert.equal(ASSIST.aiTitle, "ผู้ช่วย KidNee สรุปให้ฟัง");
  assert.ok(!html.includes("ตัวอย่าง"));
});

// ---- AI-19: loading ---------------------------------------------------------------------

test("AI_19_a_loading_state_while_waiting", () => {
  assert.deepEqual(aiBubble({ state: "loading" }, plan()), { state: "loading" });
  // The first render, before the answer: a busy status line under the title.
  const html = renderToStaticMarkup(createElement(AiBubbleCard, { plan: plan() }));
  assert.match(html, /<p role="status" aria-busy="true"[^>]*>กำลังสรุป\.\.\.<\/p>/);
  assert.equal(ASSIST.aiLoading, "กำลังสรุป...");
});

// ---- AI-20: a failed request shows the plan's own words ----------------------------------

test("AI_20_a_failed_request_shows_the_plans_own_words_in_every_scene", () => {
  for (const name of SCENES) {
    scene(name);
    const p = plan();
    const [first, ...rest] = planSummary(p).split("\n");
    const failed = aiBubble({ state: "error", error: new Error("503") }, p);
    assert.deepEqual(failed, { state: "done", first, rest }, name);
    assert.ok((first ?? "").trim().length > 0, `${name}: never an empty bubble`);
    // A ready answer with nothing to say is treated the same way.
    const blank = aiBubble({ state: "ready", data: { text: " \n ", source: "ai", reason: "ok" } }, p);
    assert.deepEqual(blank, failed, name);
  }
});

test("AI_20_the_card_has_no_error_state_and_no_retry", () => {
  const src = card();
  for (const banned of ["failed", "retry", "reload", "ไม่สำเร็จ"]) {
    assert.ok(!src.includes(banned), `the AI card must not show ${banned}`);
  }
  assert.ok(!("aiFailed" in ASSIST), "the error copy is gone");
});

test("AI_20_the_getter_rejects_on_a_network_error_a_5xx_or_no_text", async () => {
  const answers: (() => Response)[] = [
    () => {
      throw new TypeError("Failed to fetch");
    },
    () => ({ status: 503, json: async () => ({ detail: "summary unavailable" }) }) as Response,
    () => ({ status: 200, json: async () => ({ text: "", source: "ai", reason: "ok" }) }) as Response,
  ];
  for (const answer of answers) {
    globalThis.fetch = (async () => answer()) as typeof fetch;
    // useLoad turns the rejection into its error state: the bubble's plan words above.
    await assert.rejects(getAssistantSummary(), (e: unknown) => e instanceof Error);
  }
});

test("AI_20_the_mock_answers_the_get_as_the_backend_does_without_a_key", () => {
  scene("over_budget_now");
  const answer = call("GET", "/assistant/summary");
  assert.equal(answer.status, 200);
  assert.deepEqual(answer.body, { text: planSummary(plan()), source: "fallback", reason: "no_key" });
  assert.equal(call("POST", "/assistant/summary").status, 404, "the old POST is gone");
  resetMock(TODAY);
  assert.equal(call("GET", "/assistant/summary").status, 409, "no settings: SETTINGS_REQUIRED");
});
