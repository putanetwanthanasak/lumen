/**
 * Alert text for the mock, copied word for word from
 * backend/app/notifications/copy.py (the user's wording; no em dash).
 * The real backend writes these; the client only shows title and body.
 */
import type { InstallmentKind, NotificationKind } from "../api-types.ts";
import type { Money } from "../money.ts";
import { thaiMonth } from "../thaiMonth.ts";

/** Like copy.format_baht: "20000.00" -> "20,000"; "1234.50" -> "1,234.50". */
export function alertBaht(value: Money): string {
  const [whole = "0", decimals = ""] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const cents = decimals.padEnd(2, "0");
  return cents === "00" ? grouped : `${grouped}.${cents}`;
}

type Alert = { kind: NotificationKind; title: string; body: string };

const MANUAL: Record<InstallmentKind, { kind: NotificationKind; title: string }> = {
  purchase: { kind: "new_debt", title: "บันทึกรายการผ่อนแล้ว" },
  cash_withdrawal: { kind: "cash_withdrawal", title: "บันทึกการเบิกเงินสดแล้ว" },
  cash_loan: { kind: "cash_loan", title: "บันทึกการกู้เงินสดแล้ว" },
};

/** TEMPLATES[kind].kind + MANUAL_TITLES[kind] + MANUAL_BODY (Session 12; L50 strong alert for cash). */
export function manualEntryAlert(
  entryKind: InstallmentKind,
  itemName: string,
  price: Money,
  months: number,
  monthly: Money,
  monthlyTotal: Money,
): Alert {
  const body =
    `ราคา ${alertBaht(price)} บาท ผ่อน ${months} เดือน เดือนละ ${alertBaht(monthly)} บาท ` +
    `ยอดผ่อนรวมต่อเดือนตอนนี้ ${alertBaht(monthlyTotal)} บาท`;
  const { kind, title } = MANUAL[entryKind];
  return { kind, title, body: itemName ? `${itemName} ${body}` : body };
}

/** SHORTFALL_BODY, or SHORTFALL_BODY_NO_BUFFER when the buffer is 0.00. */
export function shortfallAlert(month: string, total: Money, shortfall: Money, buffer: Money, bufferIsEmpty: boolean): Alert {
  const head = `เดือน ${thaiMonth(month)} ค่างวดรวม ${alertBaht(total)} บาท เกินงบ ${alertBaht(shortfall)} บาท`;
  return {
    kind: "payday_shortfall",
    title: "เดือนนี้ค่างวดเกินงบ",
    body: bufferIsEmpty
      ? `${head} ลองเปิดผู้ช่วยปลดหนี้เพื่อดูแผนได้`
      : `${head} คุณมีกันชน ${alertBaht(buffer)} บาท ย้ายมาช่วยจ่ายได้`,
  };
}

/** LEFTOVER_BODY. */
export function leftoverAlert(month: string, total: Money, leftover: Money): Alert {
  return {
    kind: "leftover_saved",
    title: "ออมส่วนที่เหลือจากงบแล้ว",
    body: `เดือน ${thaiMonth(month)} ค่างวดรวม ${alertBaht(total)} บาท ต่ำกว่างบ ${alertBaht(leftover)} บาท ย้ายเข้ากันชนแล้ว`,
  };
}
