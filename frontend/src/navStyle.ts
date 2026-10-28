/**
 * The bottom nav's look, kept apart from React so it can be tested (UI-25).
 * Selected has the same shape for every tab: a filled icon background and a bold
 * label, in the tab's feature colour (green; teal for กันชน, whose icon is teal too).
 * The centre tab (เช็กก่อนผ่อน) is larger and raised, but unselected it is an
 * outline only, never filled, so it never looks selected on another screen.
 * Labels never wrap (`whitespace-nowrap`); copy.ts keeps them short.
 */
import { ACCENT, SOLID } from "./accent.ts";
import type { Route } from "./router.ts";

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

/** The filled look of a selected tab: green, or teal for the buffer (accent.ts). */
export function navFill(tab: NavTab): string {
  return tab === "buffer" ? SOLID.buffer : SOLID.debt;
}

export function navIconClass(tab: NavTab, active: boolean): string {
  const primary = tab === "think";
  const shape = primary
    ? `${NAV_RAISE} mb-0.5 h-14 w-14 border-2 shadow-card ring-4 ring-card`
    : "h-8 w-14 border-2 border-transparent";
  const look = active
    ? navFill(tab)
    : primary
      ? "border-leaf-700 bg-card text-leaf-800"
      : tab === "buffer"
        ? ACCENT.buffer.ink
        : "text-ink-muted group-hover:text-leaf-700";
  return `inline-flex items-center justify-center rounded-pill ${shape} ${look}`;
}

export function navLabelClass(tab: NavTab, active: boolean): string {
  const ink = tab === "buffer" ? ACCENT.buffer.ink : "text-leaf-800";
  return `whitespace-nowrap ${active ? `font-bold ${ink}` : "font-semibold text-ink-muted"}`;
}
