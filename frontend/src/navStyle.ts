/**
 * The bottom nav's look, kept apart from React so it can be tested (UI-25).
 * Selected is the same for every tab: a filled green icon background and a bold
 * label. The centre tab (ตรวจสอบ) is larger and raised, but unselected it is an
 * outline only, never filled, so it never looks selected on another screen.
 * Labels never wrap (`whitespace-nowrap`); copy.ts keeps them short.
 */
import type { Route } from "./router.ts";

const SELECTED_FILL = "bg-leaf-700 text-white";

/**
 * The three tabs (UI-30): feature 1 ภาพรวมหนี้ (Home), the check in the centre,
 * feature 2 กันชน. Nothing else: settings and notifications are in the header.
 */
export const NAV_TABS = [
  { route: "home", primary: false },
  { route: "think", primary: true },
  { route: "buffer", primary: false },
] as const satisfies readonly { route: Route; primary: boolean }[];

export type NavTab = (typeof NAV_TABS)[number]["route"];

/** A tab is selected on its own screen and on the screens it opens. */
export function navActive(tab: NavTab, current: Route): boolean {
  return tab === current || (tab === "think" && current === "result") || (tab === "home" && current === "months");
}

/** How far the centre button rises above the nav (Tailwind's 0.25rem steps: 20px). */
export const NAV_RAISE = "-mt-5";

/**
 * Bottom padding of the scrolling body while the nav shows: the raise plus at
 * least 24px, so the last item is never hidden behind the raised button (UI-27).
 */
export const SCROLL_PAD_WITH_NAV = "pb-14";
export const SCROLL_PAD_WITHOUT_NAV = "pb-6";

export function navIconClass(primary: boolean, active: boolean): string {
  const shape = primary
    ? `${NAV_RAISE} mb-0.5 h-14 w-14 border-2 shadow-card ring-4 ring-card`
    : "h-8 w-14 border-2 border-transparent";
  const look = active
    ? `${SELECTED_FILL} border-leaf-700`
    : primary
      ? "border-leaf-700 bg-card text-leaf-800"
      : "text-ink-muted";
  return `inline-flex items-center justify-center rounded-pill ${shape} ${look}`;
}

export function navLabelClass(active: boolean): string {
  return `whitespace-nowrap ${active ? "font-bold text-leaf-800" : "font-semibold text-ink-muted"}`;
}

export const NAV_SELECTED_FILL = SELECTED_FILL;
