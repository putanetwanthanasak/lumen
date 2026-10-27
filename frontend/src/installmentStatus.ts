/**
 * How Home shows an installment's status (review F4). The API decides what counts
 * (`owed`, L43); this only picks the words. "Not me" history is kept after a cancel
 * (L59(3)), so a cancelled line with `disputed_at` says so.
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
