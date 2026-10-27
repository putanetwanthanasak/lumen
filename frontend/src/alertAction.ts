/**
 * The next step a notification offers (screen 5). A payday shortfall points to the
 * buffer while it holds money, as its text says, else to ภาระผ่อนรายเดือน, which says
 * when the months are back in budget (DESIGN.md section 7.5, review B1 F6). UI-17.
 */
import type { NotificationKind } from "./api-types.ts";
import { ALERTS } from "./copy.ts";
import { toSatang, type Money } from "./money.ts";
import type { Route } from "./router.ts";

export type AlertAction = { label: string; route: Route } | null;

export function alertAction(kind: NotificationKind, bufferBalance: Money): AlertAction {
  switch (kind) {
    case "payday_shortfall":
      return toSatang(bufferBalance) > 0n
        ? { label: ALERTS.openBuffer, route: "buffer" }
        : { label: ALERTS.openMonths, route: "months" };
    case "leftover_saved":
      return { label: ALERTS.openBuffer, route: "buffer" };
    default:
      return null;
  }
}
