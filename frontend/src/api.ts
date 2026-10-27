/**
 * The ONLY place the screens get data from (DESIGN.md section 9).
 *
 * USE_MOCK = true answers from src/mock/server.ts with the same status codes and
 * bodies as the backend. Set it to false to call the FastAPI app through the Vite
 * proxy (/api is stripped; to be confirmed when wiring).
 */
import type {
  BufferOut,
  CodedDetail,
  DebtSummary,
  ManualEntryIn,
  RecordedOut,
  SettingsIn,
  SettingsOut,
  UpcomingMonthsOut,
  VerdictOut,
} from "./api-types.ts";
import { handle } from "./mock/server.ts";
import { DEMO_USER } from "./mock/persona.ts";

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

/** TODO(backend): GET /debts/months is not built yet; answered by the mock only. */
export async function getUpcomingMonths(): Promise<UpcomingMonthsOut> {
  return (await call<UpcomingMonthsOut>("GET", "/debts/months?count=6")).body;
}

export async function getBuffer(): Promise<BufferOut> {
  return (await call<BufferOut>("GET", "/buffer")).body;
}

// ---- คิดก่อน (screen 3) ------------------------------------------------------

/** Writes nothing. 409 SETTINGS_REQUIRED without settings. */
export async function previewInstallment(entry: ManualEntryIn): Promise<VerdictOut> {
  return (await call<VerdictOut>("POST", "/installments/preview", entry)).body;
}

/** 201 new or 200 repeat (same client_request_id): the body says which. */
export async function recordInstallment(entry: ManualEntryIn): Promise<RecordedOut> {
  return (await call<RecordedOut>("POST", "/installments", entry)).body;
}
