/**
 * The seeded demo personas (backend/demo/kidnee.py, docs/api/kidnee-endpoints.md), and
 * which one the app calls the API as (X-Demo-User, L60: demo-only identification, not
 * auth). The Demo panel switches between them; the choice is kept per browser, and a
 * stored id that is not a persona falls back to ม่อน. Names are fictional (rule 5).
 */
import { DEMO_USER } from "./mock/persona.ts";

export type Persona = { id: string; name: string | null; story: string };

export const PERSONAS: readonly Persona[] = [
  { id: DEMO_USER, name: "ม่อน", story: "ค่างวดอยู่ในงบทุกเดือน" },
  { id: "demo-over", name: null, story: "เกินงบเดือนนี้และเดือนหน้า กันชนพอจ่ายส่วนที่เกิน" },
  { id: "demo-consolidate", name: null, story: "เกินงบหลายเดือน กันชนไม่พอ ควรดูเรื่องรวมหนี้" },
];

const KEY = "kidnee-demo-user";

declare const __KIDNEE_MOCK__: boolean | undefined; // vite.config.ts: true only with --mode mock
const MOCK_BUILD = typeof __KIDNEE_MOCK__ !== "undefined" && __KIDNEE_MOCK__;

function stored(): string | null {
  try {
    return globalThis.localStorage?.getItem(KEY) ?? null;
  } catch {
    return null; // private window or blocked storage: the default persona
  }
}

/**
 * The persona a page starts as. The mock knows only ม่อน, so `--mode mock` ignores a
 * choice kept from the real API on the same origin (review F3); so does an unknown id.
 */
export function startingUser(mockBuild: boolean, saved: string | null): string {
  if (mockBuild) return DEMO_USER;
  return PERSONAS.find((p) => p.id === saved)?.id ?? DEMO_USER;
}

let current = startingUser(MOCK_BUILD, stored());

export function demoUser(): string {
  return current;
}

/** The persona on show, for Home's greeting. */
export function currentPersona(): Persona {
  return PERSONAS.find((p) => p.id === current) ?? { id: current, name: null, story: "" };
}

export function setDemoUser(id: string): void {
  if (!PERSONAS.some((p) => p.id === id)) return;
  current = id;
  try {
    globalThis.localStorage?.setItem(KEY, id);
  } catch {
    // Not kept across reloads; the switch still holds for this page.
  }
}
