/**
 * UI-39: a field the backend does not send yet never crashes a screen (src/apiFields.ts).
 * main's backend leaves out monthly_reduction (the plan's estimate) and platform_name
 * (installment lines); the mock sends them all. An assistant summary without text
 * counts as failed, and the bubble shows the plan's own words (AI-20).
 * Home no longer needs a month row's over_by (UI-42), so the mock no longer sends it. A reader gives null for such a field, with one console warning
 * per answer and field. It never guesses a value and never changes the answer it was
 * given, and Home, drawn from such answers, leaves out only what needs the field.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { beforeEach, test } from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { AssistantPlanOut, AssistantSummaryOut, BufferOut, DebtSummary, MonthsOut, SettingsOut, ShortfallsOut } from "../src/api-types.ts";
import { readAssistantSummary, readMonths, readPlan, readSummary } from "../src/apiFields.ts";
import { ASSIST, HOME } from "../src/copy.ts";
import { PERSONA_SETTINGS } from "../src/mock/persona.ts";
import { handle, resetMock } from "../src/mock/server.ts";
import { HomeBody } from "../src/screens/Home.tsx";

const TODAY = new Date(2026, 9, 27); // Oct 2026
const call = (method: string, path: string, body?: unknown) => handle(method, path, body, "demo-mon");
const scene = (name: string) => assert.equal(call("POST", "/demo/scene", { scene: name }).status, 200);
/** An answer as the screens get it: through JSON, as api.ts does. */
const answer = <T>(path: string): T => JSON.parse(JSON.stringify(call("GET", path).body)) as T;
const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
/** Set a field to anything, or remove it (undefined), as a backend might send it. */
function put(target: object, field: string, value: unknown): void {
  const fields = target as Record<string, unknown>;
  if (value === undefined) delete fields[field];
  else fields[field] = value;
}

/** Runs `fn` with console.warn captured: its result, and every warning in order. */
function withWarnings<T>(fn: () => T): [T, string[]] {
  const seen: string[] = [];
  const original = console.warn;
  console.warn = (...args: unknown[]) => {
    seen.push(args.map(String).join(" "));
  };
  try {
    return [fn(), seen];
  } finally {
    console.warn = original;
  }
}

const SCENES = ["persona", "over_budget", "over_budget_now", "over_budget_empty_buffer"];

beforeEach(() => resetMock(TODAY, PERSONA_SETTINGS));

function offeredPlan(): AssistantPlanOut {
  scene("over_budget_now");
  const plan = answer<AssistantPlanOut>("/assistant/plan");
  assert.ok(plan.consolidation.estimate !== null, "the scene offers consolidation");
  return plan;
}

test("UI_39_complete_answers_pass_unchanged_and_warn_nothing", () => {
  let estimates = 0;
  const [, warned] = withWarnings(() => {
    for (const name of SCENES) {
      scene(name);
      const plan = answer<AssistantPlanOut>("/assistant/plan");
      if (plan.consolidation.estimate !== null) estimates += 1;
      for (const months of [answer<MonthsOut>("/debts/months?count=6"), answer<MonthsOut>("/debts/months")]) {
        assert.deepEqual(readMonths(months), months, name);
      }
      assert.deepEqual(readPlan(plan), plan, name);
      const summary = answer<DebtSummary>("/debts/summary");
      assert.deepEqual(readSummary(summary), summary, name);
    }
    for (const source of ["ai", "fallback"] as const) {
      const summary: AssistantSummaryOut = { text: "บรรทัดแรก\nบรรทัดสอง", source, reason: source === "ai" ? "ok" : "timeout" };
      assert.deepEqual(readAssistantSummary(summary), summary);
    }
  });
  assert.ok(estimates > 0, "the estimate path ran");
  // Since Session 17 the rows carry over_by, as the backend's do, and pass unchanged.
  assert.ok(answer<MonthsOut>("/debts/months").months.every((row) => "over_by" in row));
  assert.deepEqual(warned, [], "the demo's console stays clean");
});

test("UI_39_a_plan_without_monthly_reduction_reads_it_as_null_with_one_warning", () => {
  const plan = offeredPlan();
  const sent = copy(plan);
  put(sent.consolidation.estimate ?? {}, "monthly_reduction", undefined); // as main sends it
  const before = JSON.stringify(sent);
  const [read, warned] = withWarnings(() => readPlan(sent));
  // Only that field changes; the offer keeps every other number as sent.
  assert.ok(plan.consolidation.estimate !== null);
  const expected = { ...plan, consolidation: { ...plan.consolidation, estimate: { ...plan.consolidation.estimate, monthly_reduction: null } } };
  assert.deepEqual(read, expected);
  assert.equal(JSON.stringify(sent), before, "the answer given is not changed");
  assert.equal(warned.length, 1);
  assert.match(warned[0] ?? "", /^GET \/assistant\/plan: no readable consolidation\.estimate\.monthly_reduction, so the offer card shows without its benefit line\./);
});

test("UI_39_null_or_unreadable_money_reads_as_missing_never_as_a_guess", () => {
  const plan = offeredPlan();
  // A JSON number, a sign, a comma, nothing, three decimals, a space: never read as money (L49).
  const unreadable: unknown[] = [null, 4130, "-5.00", "4,130.12", "", "4130.123", " 4130.12"];
  const [, warned] = withWarnings(() => {
    for (const value of unreadable) {
      const sent = copy(plan);
      put(sent.consolidation.estimate ?? {}, "monthly_reduction", value);
      assert.equal(readPlan(sent).consolidation.estimate?.monthly_reduction, null, JSON.stringify(value));
    }
    // A readable one is kept as sent, "0.00" too: the card leaves that line out itself (UI-38).
    for (const value of ["0.00", "0.01", "4130.12", "4130.5"]) {
      const sent = copy(plan);
      put(sent.consolidation.estimate ?? {}, "monthly_reduction", value);
      assert.equal(readPlan(sent).consolidation.estimate?.monthly_reduction, value);
    }
  });
  assert.equal(warned.length, unreadable.length);
});

test("UI_39_platform_name_absent_reads_as_null_and_text_or_null_is_kept", () => {
  scene("persona");
  const summary = answer<DebtSummary>("/debts/summary");
  // The persona names its app on some lines and not on others ("ShopDemo", null).
  assert.deepEqual([...new Set(summary.installments.map((line) => line.platform_name))].sort(), ["ShopDemo", null].sort());
  const [kept, quiet] = withWarnings(() => readSummary(copy(summary)));
  assert.deepEqual(kept, summary);
  assert.deepEqual(quiet, [], "null is a sent value: no app named");
  const sent = copy(summary);
  for (const line of sent.installments) put(line, "platform_name", undefined);
  put(sent.installments[0] ?? {}, "platform_name", 7); // not text: no app name either
  const [read, warned] = withWarnings(() => readSummary(sent));
  assert.deepEqual(
    read.installments.map((line) => line.platform_name),
    summary.installments.map(() => null),
  );
  assert.equal(warned.length, 1);
  assert.match(warned[0] ?? "", /^GET \/debts\/summary: no readable installments\[\]\.platform_name \(\d+ times\)/);
  // The month rows' installments too.
  const months = answer<MonthsOut>("/debts/months?count=6");
  const rows = copy(months);
  for (const row of rows.months) for (const item of row.installments) put(item, "platform_name", undefined);
  const [readRows, rowWarnings] = withWarnings(() => readMonths(rows));
  assert.ok(readRows.months.every((row) => row.installments.every((item) => item.platform_name === null)));
  assert.equal(rowWarnings.length, 1);
});

test("UI_39_an_assistant_summary_without_text_counts_as_failed", () => {
  const [, warned] = withWarnings(() => {
    // No text, or only spaces: a failed request (useLoad turns the throw into it), so
    // the bubble shows the plan's own words (AI-20), never an empty bubble.
    for (const text of [undefined, null, 42, "", "  \n "]) {
      assert.throws(() => readAssistantSummary({ text, source: "ai", reason: "ok" } as unknown as AssistantSummaryOut), /no text/);
    }
    // No source or reason: nothing on screen needs them, so the answer passes as it is.
    const read = readAssistantSummary({ text: "สรุป" } as unknown as AssistantSummaryOut);
    assert.deepEqual(read, { text: "สรุป" });
  });
  assert.equal(warned.length, 5);
  assert.match(warned[0] ?? "", /^GET \/assistant\/summary: no readable text, so the assistant's bubble shows the plan's own words\./);
});

test("UI_39_api_ts_reads_every_such_answer_through_its_reader", () => {
  // The getters the screens call apply the readers; the screens never see a raw answer.
  const api = readFileSync("src/api.ts", "utf8");
  const getters: [string, string][] = [
    ["getDebtSummary", "readSummary"],
    ["getMonths", "readMonths"],
    ["getAssistantPlan", "readPlan"],
    ["getAssistantSummary", "readAssistantSummary"], // in both modes since Session 18
  ];
  for (const [getter, reader] of getters) {
    const body = new RegExp(`export async function ${getter}\\([^)]*\\)[^{]*\\{\\s*return ${reader}\\(\\(await call<`).test(api);
    assert.ok(body, `${getter} returns ${reader}(...)`);
  }
});

// ---- Home, drawn from the answers as main's backend gives them today -------------

/** Remove a field wherever it is in an answer, as a backend that does not send it yet. */
function drop(value: unknown, field: string): void {
  if (Array.isArray(value)) {
    for (const item of value) drop(item, field);
  } else if (typeof value === "object" && value !== null) {
    delete (value as Record<string, unknown>)[field];
    for (const item of Object.values(value)) drop(item, field);
  }
}

const MAIN_LACKS = ["monthly_reduction", "platform_name"];

/**
 * Home in a scene, from its answers without `fields`, each read as api.ts reads it
 * (`change` edits the summary as sent): the markup, and the warnings while reading and drawing.
 */
function home(name: string, fields: readonly string[], change?: (summary: DebtSummary) => void): [string, string[]] {
  scene(name);
  const sent = <T>(path: string): T => {
    const body = answer<T>(path);
    for (const field of fields) drop(body, field);
    return body;
  };
  const summary = sent<DebtSummary>("/debts/summary");
  change?.(summary);
  const settings = sent<SettingsOut>("/settings");
  const buffer = sent<BufferOut>("/buffer");
  const months = sent<MonthsOut>("/debts/months");
  const plan = sent<AssistantPlanOut>("/assistant/plan");
  const shortfalls = sent<ShortfallsOut>("/buffer/shortfalls");
  return withWarnings(() =>
    renderToStaticMarkup(
      createElement(HomeBody, { settings, buffer, summary: readSummary(summary), months: readMonths(months), plan: readPlan(plan), shortfalls }),
    ),
  );
}

const textOf = (html: string) => html.replace(/<[^>]+>/g, " ");
/** The offer card's own markup: the section on the bank's solid blue. */
const offerCard = (html: string) => /<section class="[^"]*\bbg-bank-700\b[^"]*">[\s\S]*?<\/section>/.exec(html)?.[0] ?? "";

test("UI_39_without_monthly_reduction_home_shows_the_offer_without_its_benefit_line_and_warns", () => {
  const [html, warned] = home("over_budget_now", ["monthly_reduction"]);
  const card = offerCard(html);
  // The card, whole: its title, both plans' monthly and total amounts, the tag, the note, the button.
  const parts = ["ทางเลือกจากธนาคาร", ASSIST.exampleTag, "7,500.00 บาท", "67,500.00 บาท", "3,369.88 บาท", "80,877.12 บาท", "ผ่อน 24 เดือน ดอกเบี้ยสมมติ 18% ต่อปี", ASSIST.interested];
  for (const part of parts) assert.ok(card.includes(part), part);
  assert.ok(!html.includes("ค่างวดลดลง"), "no benefit line");
  assert.deepEqual(warned, [
    "GET /assistant/plan: no readable consolidation.estimate.monthly_reduction, so the offer card shows without its benefit line.",
  ]);
  // The control: with the field sent, the same card has the line, and nothing is warned.
  const [full, quiet] = home("over_budget_now", []);
  assert.ok(offerCard(full).includes("ค่างวดลดลงเดือนละ 4,130.12 บาท"));
  assert.deepEqual(quiet, []);
});

test("UI_39_home_never_crashes_on_the_fields_main_does_not_send_in_any_scene", () => {
  const scenes = ["persona", "over_budget", "over_budget_now", "over_budget_empty_buffer", "ai_slow", "ai_failing"];
  for (const name of scenes) {
    const [html, warned] = home(name, MAIN_LACKS); // throws if any part of Home cannot be drawn
    assert.doesNotMatch(textOf(html), /undefined|NaN|null/, name);
    // The hero's warning needs only the rows' flags, which main sends: still there.
    const over = answer<MonthsOut>("/debts/months").months.filter((m) => m.over_budget).length;
    assert.equal(textOf(html).includes(`เกินงบ ${over} เดือน (`), over > 0, name);
    // One warning per answer and field, each naming what Home leaves out.
    const offered = answer<AssistantPlanOut>("/assistant/plan").consolidation.estimate !== null;
    const heads = warned.map((w) => w.split(",")[0]?.replace(/ \(\d+ times\)$/, ""));
    assert.deepEqual(
      heads.sort(),
      [
        "GET /debts/months: no readable installments[].platform_name",
        "GET /debts/summary: no readable installments[].platform_name",
        ...(offered ? ["GET /assistant/plan: no readable consolidation.estimate.monthly_reduction"] : []),
      ].sort(),
      name,
    );
  }
});

test("UI_39_an_installment_without_platform_name_never_shows_undefined_on_home", () => {
  scene("persona");
  const first = answer<DebtSummary>("/debts/summary").installments[0];
  assert.equal(first?.platform_name, "ShopDemo");
  // Cancelled, so it shows under "ไม่นับในยอดต่อเดือน", where a row names its app.
  const cancelled = (summary: DebtSummary) => {
    const line = summary.installments[0];
    assert.ok(line !== undefined);
    Object.assign(line, { status: "cancelled", owed: false });
  };
  const [html] = home("persona", ["platform_name"], cancelled);
  assert.ok(html.includes(HOME.notCounted));
  assert.ok(!textOf(html).includes("undefined"), "no app name, never \"undefined\"");
  const left = `<span class="whitespace-nowrap">${HOME.monthsLeft(first?.months ?? 0)}</span>`;
  assert.ok(html.includes(`<span class="text-caption text-ink-muted">${left}</span>`), "the row without its app");
  const [named] = home("persona", [], cancelled);
  assert.ok(named.includes(`<span class="text-caption text-ink-muted">ShopDemo · ${left}</span>`), "with the name sent, the row says which app");
});
