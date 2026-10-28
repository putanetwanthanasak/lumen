/**
 * Mock answers for screens 6 and 7, which have no backend yet (TODO shapes in
 * api-types.ts). Exact BigInt satang, like the rest of the mock. The explanation and
 * the answers are canned examples, not generated text.
 */
import type { ConsolidationOut, MonthRow, PayoffPlanOut } from "../api-types.ts";
import { formatBaht, type Money } from "../money.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { fromSatang, toSatang } from "./satang.ts";

/** Screen 6 from the months ahead (this month first, no candidate). */
export function payoffPlan(
  rows: readonly MonthRow[],
  budget: Money,
  buffer: Money,
  owedCount: number,
): PayoffPlanOut {
  const cap = toSatang(budget);
  const lastOver = rows.findLastIndex((r) => r.over_budget);
  const back = lastOver === -1 ? (rows[0]?.month ?? null) : (rows[lastOver + 1]?.month ?? null);
  const shortfalls = rows
    .filter((r) => r.over_budget)
    .map((r) => ({ month: r.month, amount: fromSatang(toSatang(r.total) - cap) }));
  const total = shortfalls.reduce((acc, s) => acc + toSatang(s.amount), 0n);

  let headroom: PayoffPlanOut["headroom"] = null;
  if (back !== null) {
    const from = rows.findIndex((r) => r.month === back);
    const least = rows.slice(from).reduce((min, r) => {
      const room = cap - toSatang(r.total);
      return room < min ? room : min;
    }, cap);
    if (least > 0n) headroom = { amount: fromSatang(least), from_month: back };
  }

  const plan: PayoffPlanOut = {
    over_budget_now: rows[0]?.over_budget ?? false,
    back_in_budget_month: back,
    pause_until: lastOver === -1 ? null : back,
    pause_beyond_horizon: lastOver !== -1 && back === null,
    headroom,
    buffer_plan: {
      buffer_balance: buffer,
      shortfalls,
      total_shortfall: fromSatang(total),
      covered: toSatang(buffer) >= total,
    },
    explanation: "",
    consolidation_eligible: owedCount >= 2 && lastOver !== -1,
  };
  plan.explanation = explain(plan);
  return plan;
}

function explain(p: PayoffPlanOut): string {
  if (p.buffer_plan.shortfalls.length === 0) {
    return "ตอนนี้ทุกเดือนอยู่ในงบ ถ้าจะผ่อนเพิ่ม ลองกด คิดก่อน ทุกครั้ง จะได้เห็นว่าเดือนไหนแน่นที่สุด";
  }
  // The tightest month is the one over by the most (review B2 F5).
  const first = p.buffer_plan.shortfalls.reduce<(typeof p.buffer_plan.shortfalls)[number] | undefined>(
    (max, s) => (max === undefined || toSatang(s.amount) > toSatang(max.amount) ? s : max),
    undefined,
  );
  const months = p.buffer_plan.shortfalls.map((s) => thaiMonth(s.month)).join(", ");
  const parts = [
    `ช่วง ${months} ค่างวดรวมสูงกว่างบ เพราะมีหลายรายการซ้อนกันอยู่`,
    first === undefined ? "" : `เดือนที่แน่นที่สุดเกินงบ ${formatBaht(first.amount)}`,
    p.buffer_plan.covered
      ? `กันชนที่มีอยู่ ${formatBaht(p.buffer_plan.buffer_balance)} พอช่วยจ่ายส่วนที่เกินได้`
      : "กันชนยังไม่พอสำหรับทุกเดือนที่เกิน ลองชะลอการผ่อนใหม่ไว้ก่อน",
    p.back_in_budget_month === null ? "" : `ตั้งแต่ ${thaiMonth(p.back_in_budget_month)} จะกลับมาอยู่ในงบ`,
  ];
  return parts.filter((s) => s !== "").join(" ");
}

/** Canned example answers for the question box, chosen by keyword. */
export function exampleAnswer(question: string): string {
  if (/กันชน|ย้าย/.test(question)) {
    return "เงินในกันชนเป็นของคุณ ย้ายกลับบัญชีหลักได้ทุกเมื่อ ถ้าเดือนไหนค่างวดเกินงบ ย้ายมาช่วยจ่ายเฉพาะส่วนที่เกินก็พอ";
  }
  if (/รวมหนี้|ปิด/.test(question)) {
    return "การรวมหนี้อาจทำให้ค่างวดต่อเดือนลดลง แต่ต้นทุนรวมอาจสูงขึ้น ดูทั้งสองตัวเลขก่อนตัดสินใจนะ";
  }
  return "ลองเริ่มจากเดือนที่ค่างวดรวมเกินงบก่อน ชะลอการผ่อนใหม่จนถึงเดือนที่กลับมาอยู่ในงบ แล้วใช้กันชนช่วยเฉพาะส่วนที่เกิน";
}

export const EXAMPLE_ANNUAL_RATE = "12.00";
const RATE_BASIS_POINTS = 1200n; // 12.00% a year, an assumed example

/**
 * Screen 7: a flat-rate example. Interest = principal x 12% x months / 12,
 * rounded down to the satang; the monthly payment is rounded up, and the total is
 * what all payments add up to, so the two numbers always agree.
 */
export function consolidationEstimate(
  principal: Money,
  months: number,
  monthlyNow: Money,
  remainingNow: Money,
): ConsolidationOut {
  const p = toSatang(principal);
  const n = BigInt(months);
  const interest = (p * RATE_BASIS_POINTS * n) / (10000n * 12n);
  const owed = p + interest;
  const monthly = (owed + n - 1n) / n;
  const total = monthly * n;
  return {
    is_example: true,
    principal,
    months,
    annual_rate_example: EXAMPLE_ANNUAL_RATE,
    new_monthly_payment: fromSatang(monthly),
    total_cost: fromSatang(total),
    total_interest: fromSatang(total - p),
    monthly_now: monthlyNow,
    remaining_now: remainingNow,
  };
}
