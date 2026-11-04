/**
 * One accent colour per feature (DESIGN.md section 4), never colour only: each
 * accent comes with its icon and its text, and the screens take the classes from
 * here only (UI-34 scans for teal-, bank-, ai-, quiet- and host- classes anywhere else).
 * Contrast of every pair is checked against index.css by UI-35.
 */
import type { IconName } from "./components/Icon.tsx";
import { ACCENT_LABEL } from "./copy.ts";

export type Accent = "debt" | "buffer" | "warn" | "bank" | "ai" | "quiet";

export type AccentLook = {
  icon: IconName;
  label: string; // what the colour means, in Thai
  ink: string; // text and icons, on white or on the tint
  tint: string; // background
  line: string; // border on the tint
};

/** A coloured line or chip: never colour only, so always an icon and text (UI-34). */
export type Marked = { accent: Accent; icon: IconName; text: string };

export const ACCENT: Record<Accent, AccentLook> = {
  // Feature 1, ภาพรวมหนี้, the main actions, and "in budget".
  debt: { icon: "home", label: ACCENT_LABEL.debt, ink: "text-leaf-800", tint: "bg-leaf-50", line: "border-leaf-200" },
  // Feature 2, กันชน.
  buffer: { icon: "shield", label: ACCENT_LABEL.buffer, ink: "text-teal-800", tint: "bg-teal-50", line: "border-teal-100" },
  // A month over budget: the warn-* family, as on the verdict and the month bars.
  warn: { icon: "alert", label: ACCENT_LABEL.warn, ink: "text-warn-ink", tint: "bg-warn-bg", line: "border-warn-line" },
  // The bank's consolidation offer, an example only (L71: the bank decides).
  bank: { icon: "bank", label: ACCENT_LABEL.bank, ink: "text-bank-800", tint: "bg-bank-50", line: "border-bank-200" },
  // The assistant only: a soft tint, never a solid colour.
  ai: { icon: "chat", label: ACCENT_LABEL.ai, ink: "text-ai-ink", tint: "bg-linear-to-br from-ai-from to-ai-to", line: "border-ai-line" },
  // A note with nothing to act on: low emphasis.
  quiet: { icon: "info", label: ACCENT_LABEL.quiet, ink: "text-quiet-ink", tint: "bg-quiet-bg", line: "border-quiet-line" },
};

/** Filled: a selected nav tab, the wallet's icon, the bank offer's header band. White text on it. */
export const SOLID = {
  debt: "border-leaf-700 bg-leaf-700 text-white",
  buffer: "border-teal-700 bg-teal-700 text-white",
  bank: "border-bank-700 bg-bank-700 text-white",
} as const satisfies Partial<Record<Accent, string>>;

/**
 * The edge of a tinted card where it meets the page, at least 3:1 against the page
 * (WCAG 1.4.11; UI-35 measures each): without it the light tints blend into the
 * page. The bank's offer is a white card framed in its own blue; the buffer's wallet
 * (Home and the buffer screen) in a mid teal.
 */
export const EDGE = {
  buffer: "border-2 border-teal-edge",
  bank: "border-2 border-bank-700",
  ai: "border border-ai-edge",
  quiet: "border border-quiet-edge",
} as const satisfies Partial<Record<Accent, string>>;

/** A feature's own button, drawn as an outline (green uses Button's secondary). */
export const OUTLINE = {
  bank: "border-2 border-bank-700 bg-card text-bank-800 hover:bg-bank-50",
  buffer: "border-2 border-teal-700 bg-card text-teal-800 hover:bg-teal-50",
} as const satisfies Partial<Record<Accent, string>>;

/** A feature's own main button, filled (green uses Button's primary): the buffer's move. */
export const FILL = {
  buffer: "bg-teal-700 text-white hover:bg-teal-800 disabled:bg-teal-200",
} as const satisfies Partial<Record<Accent, string>>;

/** The wallet's month segments: filled and empty. */
export const BUFFER_METER = { on: "bg-teal-700", off: "bg-teal-200" } as const;

/**
 * A month bar's buffer part: what was moved from the buffer for that month (barSegments,
 * UI-52), the wallet's filled teal, at least 3:1 against the white card (UI-35).
 */
export const BUFFER_BAR = "bg-teal-700";

/** The months screen's chip for a month the buffer covered: its own tint, ink and shield. */
export const BUFFER_CHIP = `${ACCENT.buffer.tint} ${ACCENT.buffer.ink}`;

/**
 * The host shell of #/account (Session 21): a generic bank app's home around KidNee.
 * Flat colours only, no artwork. White text on every host colour (UI-35).
 */
export const HOST = {
  page: "bg-linear-to-b from-host-from to-host-to text-white",
  card: "border border-host-line bg-host-card text-white",
  muted: "text-host-muted",
  shortcut: "border-2 border-host-line text-white group-hover:bg-host-card",
  bar: "border-t border-host-line bg-host-bar",
  navOn: "border-b-2 border-white font-bold text-white",
  navOff: "border-b-2 border-transparent font-semibold text-host-muted",
  focus: "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white",
} as const;
