/**
 * The ONLY place the screens get data from (DESIGN.md section 9).
 *
 * USE_MOCK = true answers from src/mock/server.ts with the same status codes and
 * bodies as the backend. Set it to false to call the FastAPI app through the Vite
 * proxy (/api is stripped; to be confirmed when wiring).
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
  SuggestedMonthlyOut,
} from "./api-types.ts";
import { handle } from "./mock/server.ts";
import { DEMO_USER } from "./mock/persona.ts";
import type { Money } from "./money.ts";

export const USE_MOCK = true;
const API_PREFIX = "/api";
const MOCK_DELAY_MS = 450; // long enough to show loading states in the demo

/** A non-2xx answer. `code` is set for {"detail": {"code", "message"}} errors. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, detail: unknown) {
    const coded = isCoded(detail) ? detail : null;
    super(coded?.message ?? (typeof detail === "string" ? detail : `HTTP ${status}`));
    this.status = status;
    this.code = coded?.code ?? null;
  }
}

function isCoded(detail: unknown): detail is CodedDetail {
  return typeof detail === "object" && detail !== null && "code" in detail && "message" in detail;
}

type Answer<T> = { status: number; body: T };

async function call<T>(method: "GET" | "POST" | "PUT", path: string, body?: unknown): Promise<Answer<T>> {
  let status: number;
  let data: unknown;
  if (USE_MOCK) {
    await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
    // Through JSON, so the mock cannot hand the screens anything the API could not.
    const answer = handle(method, path, body === undefined ? undefined : JSON.parse(JSON.stringify(body)), DEMO_USER);
    status = answer.status;
    data = JSON.parse(JSON.stringify(answer.body));
  } else {
    const response = await fetch(`${API_PREFIX}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        // L60: no end-user auth before the real login; demo only.
        "X-Demo-User": DEMO_USER,
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
  return (await call<DebtSummary>("GET", "/debts/summary")).body;
}

/**
 * TODO(backend): GET /debts/months is not built yet; answered by the mock only.
 * With `count`, that many months from now; without, up to the last month due.
 */
export async function getMonths(count?: number): Promise<MonthsOut> {
  return (await call<MonthsOut>("GET", count === undefined ? "/debts/months" : `/debts/months?count=${count}`)).body;
}

export async function getBuffer(): Promise<BufferOut> {
  return (await call<BufferOut>("GET", "/buffer")).body;
}

// ---- ตรวจสอบก่อนผ่อน (screen 3) ------------------------------------------------------

/** Writes nothing. 409 SETTINGS_REQUIRED without settings. */
export async function previewInstallment(entry: ManualEntryIn): Promise<PreviewOut> {
  return (await call<PreviewOut>("POST", "/installments/preview", entry)).body;
}

/**
 * The 0% monthly amount to prefill: price / months rounded up to 0.01. Worked out
 * by the API, never by screen code. TODO(backend): mock only for now.
 */
export async function suggestMonthly(itemPrice: Money, months: number): Promise<Money> {
  const query = `item_price=${encodeURIComponent(itemPrice)}&months=${months}`;
  return (await call<SuggestedMonthlyOut>("GET", `/installments/suggested-monthly?${query}`)).body.monthly_amount;
}

/** 201 new or 200 repeat (same client_request_id): the body says which. */
export async function recordInstallment(entry: ManualEntryIn): Promise<RecordedOut> {
  return (await call<RecordedOut>("POST", "/installments", entry)).body;
}

// ---- กันชน (screen 4) --------------------------------------------------------

/** 201 moved or 200 repeat (same client_request_id); 422 AMOUNT_ABOVE_BALANCE. */
export async function moveToMain(request: MoveIn): Promise<MovedOut> {
  return (await call<MovedOut>("POST", "/buffer/move-to-main", request)).body;
}

// ---- แจ้งเตือน (screen 5) ------------------------------------------------------

/** TODO(backend): GET /notifications is not built yet; answered by the mock only. */
export async function getNotifications(): Promise<NotificationsOut> {
  return (await call<NotificationsOut>("GET", "/notifications")).body;
}

/** TODO(backend): POST /notifications/read marks every notification read (opening the list). */
export async function markNotificationsRead(): Promise<NotificationsOut> {
  return (await call<NotificationsOut>("POST", "/notifications/read")).body;
}

// ---- Assistant plan (Home, ภาระผ่อนรายเดือน, the form hint, the buffer) ------------

/** GET /assistant/plan (merged backend): every number of the plan; 409 SETTINGS_REQUIRED. */
export async function getAssistantPlan(): Promise<AssistantPlanOut> {
  return (await call<AssistantPlanOut>("GET", "/assistant/plan")).body;
}

/** TODO(backend, tomorrow): POST /assistant/summary, the AI summary. The mock returns an example. */
export async function getAssistantSummary(): Promise<AssistantSummaryOut> {
  return (await call<AssistantSummaryOut>("POST", "/assistant/summary")).body;
}

// ---- Demo panel -----------------------------------------------------------------

/** POST /demo/payday: mounted only with DEMO_ENDPOINTS_ENABLED=true (404 otherwise). */
export async function runPayday(month: string): Promise<{ created: boolean; out: PaydayOut }> {
  const answer = await call<PaydayOut>("POST", "/demo/payday", { month });
  return { created: answer.status === 201, out: answer.body };
}

export type DemoScene = "first_launch" | "persona" | "over_budget" | "over_budget_now";

/** Mock only: there is no backend endpoint for scenes. */
export async function setDemoScene(scene: DemoScene): Promise<void> {
  if (!USE_MOCK) throw new Error("demo scenes exist only in the mock");
  await call<unknown>("POST", "/demo/scene", { scene });
}
