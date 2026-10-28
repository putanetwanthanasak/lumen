/**
 * Screen 7: how to get a payoff amount, per app the user named (UI-23). Apps come
 * from groupByPlatform (first appearance order, "ไม่ระบุแอป" last); the steps name
 * the app and its items. The names are the user's own text, never a platform list.
 */
import type { InstallmentLine } from "./api-types.ts";
import { CONSOLIDATE, HOME } from "./copy.ts";
import { groupByPlatform } from "./installmentStatus.ts";

export type AppSteps = { label: string; steps: string[] };

export function payoffSteps(lines: readonly InstallmentLine[]): AppSteps[] {
  return groupByPlatform(lines).map((group) => {
    const items = group.lines.map((l) => l.item_name || HOME.unnamed).join(", ");
    return { label: group.label, steps: CONSOLIDATE.stepsFor(group.platform, items) };
  });
}
