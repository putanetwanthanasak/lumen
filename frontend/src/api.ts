/**
 * The ONLY place the screens get data from (DESIGN.md section 9).
 *
 * The app calls the FastAPI app at /api (the Vite proxy in dev, the one-server demo
 * in `python -m demo.kidnee serve`, L73), as the persona the Demo panel picked
 * (X-Demo-User, src/personas.ts). Only `npm run dev -- --mode mock` answers from
 * src/mock/server.ts instead, with the same status codes and bodies; the tests call
 * that mock directly. A field an answer lacks is read by src/apiFields.ts, so a
 * screen never crashes on one (UI-39).
 */
import type {
  AssistantPlanOut,
  AssistantSummaryOut,
  BufferOut,
  CodedDetail,
  DebtSummary,
  ManualEntryIn,
  MonthsOut,
  MoveIn,
  MovedOut,
  NotificationsOut,
  PaydayOut,
  PreviewOut,
  RecordedOut,
  SettingsIn,
  SettingsOut,
  ShortfallsOut,
  SuggestedMonthlyOut,
} from "./api-types.ts";
import { readAssistantSummary, readMonths, readPlan, readSummary } from "./apiFields.ts";
import { exampleSummary } from "./assistantText.ts";
import { handle } from "./mock/server.ts";
import type { Money } from "./money.ts";
import { demoUser } from "./personas.ts";

// Set by vite.config.ts: true only with `--mode mock`. Undeclared under node --test.
declare const __KIDNEE_MOCK__: boolean | undefined;
export const USE_MOCK = typeof __KIDNEE_MOCK__ !== "undefined" && __KIDNEE_MOCK__;
const API_PREFIX = "/api";
const MOCK_DELAY_MS = 450; // long enough to show loading states in the demo

let mock = USE_MOCK;

/** For the tests: answer from src/mock/server.ts, as `--mode mock` does. */
export function answerFromMock(on: boolean): void {
  mock = on;
}

/**
 * A non-2xx answer. `code` is set for {"detail": {"code", "message"}} errors;
 * `fields` names the request fields a 422 rejected (the last part of each `loc`).
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly fields: readonly string[];

  constructor(status: number, detail: unknown) {
    const coded = isCoded(detail) ? detail : null;
    super(coded?.message ?? (typeof detail === "string" ? detail : `HTTP ${status}`));
    this.status = status;
    this.code = coded?.code ?? null;
    this.fields = Array.isArray(detail) ? detail.flatMap(fieldOf) : [];
  }
}

function isCoded(detail: unknown): detail is CodedDetail {
  return typeof detail === "object" && detail !== null && "code" in detail && "message" in detail;
}

/** {"loc": ["body", "saving_rule", "percent"], ...} -> ["percent"]; nothing when there is no field name. */
function fieldOf(error: unknown): string[] {
  if (typeof error !== "object" || error === null || !("loc" in error) || !Array.isArray(error.loc)) return [];
  const last: unknown = error.loc.at(-1);
  return typeof last === "string" && last !== "body" ? [last] : [];
}

/** The request fields a 422 rejected, or none for any other error. */
export function rejectedFields(error: unknown): readonly string[] {
  return error instanceof ApiError && error.status === 422 ? error.fields : [];
}

/** True when the answer was 409 SETTINGS_REQUIRED: the screen opens the settings. */
export function needsSettings(error: unknown): boolean {
  return error instanceof ApiError && error.code === "SETTINGS_REQUIRED";
}

type Answer<T> = { status: number; body: T };

async function call<T>(method: "GET" | "POST" | "PUT", path: string, body?: unknown): Promise<Answer<T>> {
  let status: number;
  let data: unknown;
  if (mock) {
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
    // Through JSON, so the mock cannot hand the screens anything the API could not.
    const answer = handle(method, path, body === undefined ? undefined : JSON.parse(JSON.stringify(body)), demoUser());
    if (answer.delayMs !== undefined) await new Promise((resolve) => setTimeout(resolve, answer.delayMs));
    status = answer.status;
    data = JSON.parse(JSON.stringify(answer.body));
  } else {
    const response = await fetch(`${API_PREFIX}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        // L60: no end-user auth before the real login; demo only.
        "X-Demo-User": demoUser(),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    status = response.status;
    data = await response.json().catch(() => null);
  }
  if (status < 200 || status >= 300) {
    const detail = typeof data === "object" && data !== null && "detail" in data ? data.detail : null;
    throw new ApiError(status, detail);
  }
  return { status, body: data as T };
}

// ---- settings (screen 1) ----------------------------------------------------

/** null when the user has none yet (404). */
export async function getSettings(): Promise<SettingsOut | null> {
  try {
    return (await call<SettingsOut>("GET", "/settings")).body;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

/** POST the first time, PUT afterwards. */
export async function saveSettings(data: SettingsIn, exists: boolean): Promise<SettingsOut> {
  if (exists) return (await call<SettingsOut>("PUT", "/settings", data)).body;
  try {
    return (await call<SettingsOut>("POST", "/settings", data)).body;
  } catch (error) {
    // A first save whose answer was lost already exists: save again as an update
    // (review round 2, F6), instead of a 409 on every retry.
    if (error instanceof ApiError && error.status === 409) return (await call<SettingsOut>("PUT", "/settings", data)).body;
    throw error;
  }
}

// ---- home (screen 2) --------------------------------------------------------

export async function getDebtSummary(): Promise<DebtSummary> {
  return readSummary((await call<DebtSummary>("GET", "/debts/summary")).body);
}

/** GET /debts/months: with `count`, that many months from now; without, up to the last month due. */
export async function getMonths(count?: number): Promise<MonthsOut> {
  return readMonths((await call<MonthsOut>("GET", count === undefined ? "/debts/months" : `/debts/months?count=${count}`)).body);
}

export async function getBuffer(): Promise<BufferOut> {
  return (await call<BufferOut>("GET", "/buffer")).body;
}

/** GET /buffer/shortfalls: each month over budget, and whether money was moved for it. */
export async function getShortfalls(): Promise<ShortfallsOut> {
  return (await call<ShortfallsOut>("GET", "/buffer/shortfalls")).body;
}

// ---- เช็กก่อนผ่อน (screen 3) ------------------------------------------------------

/** Writes nothing. 409 SETTINGS_REQUIRED without settings. */
export async function previewInstallment(entry: ManualEntryIn): Promise<PreviewOut> {
  return (await call<PreviewOut>("POST", "/installments/preview", entry)).body;
}

/** The 0% monthly amount to prefill: price / months rounded up to 0.01. Worked out by the API, never by screen code. */
export async function suggestMonthly(itemPrice: Money, months: number): Promise<Money> {
  const query = `item_price=${encodeURIComponent(itemPrice)}&months=${months}`;
  return (await call<SuggestedMonthlyOut>("GET", `/installments/suggested-monthly?${query}`)).body.monthly_amount;
}

/** 201 new or 200 repeat (same client_request_id): the body says which. */
export async function recordInstallment(entry: ManualEntryIn): Promise<RecordedOut> {
  return (await call<RecordedOut>("POST", "/installments", entry)).body;
}

// ---- กันชน (screen 4) --------------------------------------------------------

/** 201 moved or 200 repeat (same client_request_id and fields); 422 AMOUNT_ABOVE_BALANCE. */
export async function moveToMain(request: MoveIn): Promise<MovedOut> {
  return (await call<MovedOut>("POST", "/buffer/move-to-main", request)).body;
}

// ---- แจ้งเตือน (screen 5) ------------------------------------------------------

/** GET /notifications: newest first; no read state. */
export async function getNotifications(): Promise<NotificationsOut> {
  return (await call<NotificationsOut>("GET", "/notifications")).body;
}

// ---- Assistant plan (Home, ภาระผ่อนรายเดือน, the form hint, the buffer) ------------

/** GET /assistant/plan (merged backend): every number of the plan; 409 SETTINGS_REQUIRED. */
export async function getAssistantPlan(): Promise<AssistantPlanOut> {
  return readPlan((await call<AssistantPlanOut>("GET", "/assistant/plan")).body);
}

/**
 * The assistant's bubble on Home. There is no AI endpoint (roadmap only), so it is an
 * example worded from the real plan's numbers, always labelled ตัวอย่าง. The mock
 * still answers POST /assistant/summary, for its slow and failing scenes.
 */
export async function getAssistantSummary(): Promise<AssistantSummaryOut> {
  if (!mock) return { text: exampleSummary(await getAssistantPlan()), is_example: true };
  return readAssistantSummary((await call<AssistantSummaryOut>("POST", "/assistant/summary")).body);
}

// ---- Demo panel -----------------------------------------------------------------

/**
 * Whether the demo endpoints are on (DEMO_ENDPOINTS_ENABLED), without writing: an
 * empty body is refused (422) by a mounted POST /demo/payday, and the path is 404
 * when they are off.
 */
export async function demoEndpointsEnabled(): Promise<boolean> {
  return (await demoEndpointsAnswer()) === true;
}

/**
 * true on, false off (404), null when the API did not answer: a network error, or a
 * 5xx, which is what the Vite proxy sends while the backend is down (review round 2 F3).
 */
async function demoEndpointsAnswer(): Promise<boolean | null> {
  try {
    await call<unknown>("POST", "/demo/payday", {});
    return true;
  } catch (error) {
    if (!(error instanceof ApiError) || error.status >= 500) return null;
    return error.status !== 404;
  }
}

let demoProbe: Promise<boolean | null> | null = null;

/**
 * The Demo panel's probe, asked once per page once the API has answered. No answer
 * tells nothing either way: no panel for now, and the next screen asks again, so
 * starting the frontend before the API still shows the panel later (review F4).
 */
export function demoEndpointsOnce(): Promise<boolean> {
  demoProbe ??= demoEndpointsAnswer().then((answer) => {
    if (answer === null) demoProbe = null;
    return answer;
  });
  return demoProbe.then((answer) => answer === true);
}

/** POST /demo/payday: mounted only with DEMO_ENDPOINTS_ENABLED=true (404 otherwise). */
export async function runPayday(month: string): Promise<{ created: boolean; out: PaydayOut }> {
  const answer = await call<PaydayOut>("POST", "/demo/payday", { month });
  return { created: answer.status === 201, out: answer.body };
}

export type DemoScene =
  | "first_launch"
  | "persona"
  | "over_budget"
  | "over_budget_now"
  | "over_budget_empty_buffer"
  | "ai_slow"
  | "ai_failing";

/** Mock only: there is no backend endpoint for scenes. */
export async function setDemoScene(scene: DemoScene): Promise<void> {
  if (!mock) throw new Error("demo scenes exist only in the mock");
  await call<unknown>("POST", "/demo/scene", { scene });
}
