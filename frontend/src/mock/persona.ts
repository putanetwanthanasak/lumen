/**
 * Demo persona ม่อน (DESIGN.md section 10). Months are relative to the month the
 * demo runs in, so the story reads the same on any date:
 * - an installment of 2,000.00 that ends soon (its last month is next-next month),
 * - one of 1,500.00 that runs most of next year.
 * Now: 3,500.00 a month against a budget of 5,000.00 and an income of 20,000.00.
 */
import type { InstallmentKind, SettingsIn } from "../api-types.ts";
import type { Money } from "../money.ts";
import { addMonths, monthOf } from "../thaiMonth.ts";

export const PERSONA_NAME = "ม่อน";
export const DEMO_USER = "demo-mon";

export const PERSONA_SETTINGS: SettingsIn = {
  income: "20000.00",
  payday: 25,
  monthly_installment_budget: "5000.00",
  saving_rule: { mode: "percent", percent: 10 },
  auto_save_enabled: true,
  auto_save_consent: true,
  leftover_saving_enabled: true,
};

/** The mock's view of an installment: the summary line plus its schedule. */
export type MockInstallment = {
  id: string;
  vendor: string;
  contract_id: string;
  kind: InstallmentKind;
  item_name: string;
  principal: Money;
  monthly_amount: Money;
  months: number;
  paid_amount: Money;
  remaining: Money;
  first_due_month: string; // "YYYY-MM"
  platform_name: string | null; // the user's own text, never a list of real platforms
};

export function personaInstallments(today: Date): MockInstallment[] {
  const now = monthOf(today);
  return [
    {
      id: "8f0c2a4e-1b7d-4c55-9a7e-2f1d3c4b5a61",
      vendor: "manual",
      contract_id: "manual-8f0c2a4e",
      kind: "purchase",
      item_name: "หูฟังไร้สาย",
      principal: "12000.00",
      monthly_amount: "2000.00",
      months: 6,
      paid_amount: "8000.00",
      remaining: "4000.00",
      first_due_month: addMonths(now, -3), // last due: now + 2
      platform_name: "ShopDemo",
    },
    {
      id: "3b9e7d10-6a2f-4e8c-b1d4-7c0a5e9f2b38",
      vendor: "manual",
      contract_id: "manual-3b9e7d10",
      kind: "purchase",
      item_name: "ตู้เย็น",
      principal: "15000.00",
      monthly_amount: "1500.00",
      months: 10,
      paid_amount: "3000.00",
      remaining: "12000.00",
      first_due_month: addMonths(now, -1), // last due: now + 8
      platform_name: null,
    },
    {
      // Paid off: listed on Home but not counted (owed is false).
      id: "c41f8e22-9d3a-4b7e-8f61-0a2b3c4d5e6f",
      vendor: "manual",
      contract_id: "manual-c41f8e22",
      kind: "purchase",
      item_name: "กระเป๋าเป้",
      principal: "2400.00",
      monthly_amount: "800.00",
      months: 3,
      paid_amount: "2400.00",
      remaining: "0.00",
      first_due_month: addMonths(now, -5), // last due: now - 3
      platform_name: "ShopDemo",
    },
  ];
}

/** Bank-side balances for the mock (L63 safety net, L66 buffer). */
export const PERSONA_MAIN_BALANCE: Money = "9500.00";
export const PERSONA_BUFFER_BALANCE: Money = "4800.00";

export type Scenario = "GREEN" | "YELLOW" | "RED";

export type ScenarioEntry = {
  item_name: string;
  item_price: Money;
  months: number;
  monthly_amount: Money;
};

/** The three เช็กก่อนผ่อน examples the demo switches between. */
export const SCENARIOS: Record<Scenario, ScenarioEntry> = {
  // Next month: 2,000 + 1,500 + 1,200 = 4,700 <= 5,000 budget. Every month fits.
  GREEN: { item_name: "โทรศัพท์", item_price: "12000.00", months: 10, monthly_amount: "1200.00" },
  // Next two months: 6,500 > 5,000 budget, but 6,500 x 3 = 19,500 <= 20,000 income.
  YELLOW: { item_name: "โน้ตบุ๊ก", item_price: "30000.00", months: 10, monthly_amount: "3000.00" },
  // Next month: 7,500 x 3 = 22,500 > 20,000 income: above one third.
  RED: { item_name: "มอเตอร์ไซค์", item_price: "48000.00", months: 12, monthly_amount: "4000.00" },
};
