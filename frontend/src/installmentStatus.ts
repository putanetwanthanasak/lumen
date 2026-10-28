/**
 * How Home shows an installment: its status (review F4) and its group by app.
 * The API decides what counts (`owed`, L43); this only picks the words. "Not me"
 * history is kept after a cancel (L59(3)), so a cancelled line with `disputed_at`
 * says so.
 */
import type { InstallmentLine } from "./api-types.ts";
import { HOME } from "./copy.ts";

export type LineStatus = { label: string | null; counted: boolean };

export function lineStatus(line: InstallmentLine): LineStatus {
  const counted = line.owed;
  switch (line.status) {
    case "active":
      return { label: null, counted };
    case "paid_off":
      return { label: HOME.statusPaidOff, counted };
    case "disputed":
      return { label: HOME.statusDisputed, counted };
    case "cancelled":
      return { label: line.disputed_at === null ? HOME.statusCancelled : HOME.statusCancelledAfterReport, counted };
  }
}

export type PlatformGroup = { platform: string | null; label: string; lines: InstallmentLine[] };

/**
 * Home groups installments by the app the user named (UI-19): apps in the order
 * they first appear, the ones without an app last as "ไม่ระบุแอป". Names are the
 * user's own text, compared after trimming, never matched against a platform list.
 */
export function groupByPlatform(lines: readonly InstallmentLine[]): PlatformGroup[] {
  const groups = new Map<string | null, InstallmentLine[]>();
  for (const line of lines) {
    const name = line.platform_name?.trim() || null;
    groups.set(name, [...(groups.get(name) ?? []), line]);
  }
  const named = [...groups].filter(([name]) => name !== null);
  const none = groups.get(null);
  return [
    ...named.map(([platform, list]) => ({ platform, label: platform ?? HOME.noPlatform, lines: list })),
    ...(none === undefined ? [] : [{ platform: null, label: HOME.noPlatform, lines: none }]),
  ];
}
