/**
 * Every Thai string the screens show (DESIGN.md section 8).
 *
 * Rules: friendly helper tone, never scolding; no em dash; no claim we cannot back;
 * the one-third rule is "ธปท. แนะนำ" (guidance), never "ธปท. กำหนด" (L64, L65).
 * Amounts come in already formatted by money.ts; this file never touches money.
 */
import type { PaydayOutcome, Verdict } from "./api-types.ts";

export const APP_NAME = "KidNee";
export const APP_NAME_TH = "คิดหนี้";
export const FOOTER = "Concept prototype สำหรับการแข่งขัน";
export const BOT_GUIDANCE =
  "ธปท. แนะนำว่าค่างวดหนี้ทั้งหมดต่อเดือนไม่ควรเกิน 1 ใน 3 ของรายได้";

export type VerdictIcon = "check" | "alert" | "stop";

export type VerdictCopy = {
  icon: VerdictIcon;
  label: string;
  detail: string;
};

/** The verdict is never colour only: an icon and this text always go with it. */
export const VERDICT: Record<Verdict, VerdictCopy> = {
  GREEN: {
    icon: "check",
    label: "ไหว",
    detail: "ทุกเดือนค่างวดรวมยังอยู่ในงบที่คุณตั้งไว้",
  },
  YELLOW: {
    icon: "alert",
    label: "เสี่ยง: บางเดือนเกินงบ",
    detail: "มีบางเดือนที่ค่างวดรวมเกินงบ ลองดูกราฟด้านล่างว่าเป็นเดือนไหน",
  },
  RED: {
    icon: "stop",
    label: "ไม่ไหว: เกิน 1 ใน 3 ของรายได้",
    detail: "บางเดือนค่างวดรวมสูงกว่าที่ ธปท. แนะนำ คือค่างวดหนี้ทั้งหมดต่อเดือนไม่ควรเกิน 1 ใน 3 ของรายได้",
  },
};

export const ADVISORY_NOTE = "นี่เป็นคำแนะนำเท่านั้น คุณบันทึกรายการได้เสมอ";

export const NAV = {
  home: "หน้าหลัก",
  think: "คิดก่อน",
  buffer: "กันชน",
  alerts: "แจ้งเตือน",
  settings: "ตั้งค่า",
  back: "ย้อนกลับ",
};

export const COMMON = {
  loading: "กำลังโหลด...",
  retry: "ลองอีกครั้ง",
  errorTitle: "โหลดข้อมูลไม่สำเร็จ",
  errorBody: "เชื่อมต่อไม่สำเร็จ ข้อมูลของคุณยังอยู่ครบ ลองอีกครั้งได้เลย",
  baht: "บาท",
  months: "เดือน",
  perMonth: "ต่อเดือน",
  settingsMissingTitle: "ตั้งค่าก่อนเริ่มใช้",
  settingsMissingBody: "บอกรายได้และงบผ่อนต่อเดือนก่อน KidNee ถึงจะช่วยคิดให้ได้",
  settingsMissingAction: "ไปตั้งค่า",
};

export const MONEY_ERRORS = {
  empty: "กรอกจำนวนเงินด้วยนะ",
  format: "กรอกเป็นตัวเลข เช่น 12000 หรือ 12,000.50",
  decimals: "ทศนิยมได้ไม่เกิน 2 ตำแหน่ง",
  zero: "จำนวนเงินต้องมากกว่า 0",
  too_large: "จำนวนเงินมากเกินไป",
} as const;

export const SETTINGS = {
  title: "เริ่มต้นใช้ KidNee",
  intro: "ตั้งค่าครั้งเดียว KidNee จะช่วยดูว่าผ่อนเพิ่มแล้วยังไหวไหม",
  editTitle: "ตั้งค่า",
  income: "รายได้ต่อเดือน",
  incomeHelp: "รายได้หลังหักภาษีและประกันสังคม",
  payday: "วันเงินเดือนออก",
  paydayHelp: "วันที่ 1 ถึง 31 ของทุกเดือน",
  paydayError: "เลือกวันที่ 1 ถึง 31",
  budget: "งบผ่อนต่อเดือน",
  budgetHelp: "ค่างวดรวมทุกรายการที่คุณสบายใจจ่ายในแต่ละเดือน",
  budgetWarning: `งบนี้เกิน 1 ใน 3 ของรายได้ ${BOT_GUIDANCE} บันทึกไว้แล้ว ปรับได้ทุกเมื่อ`,
  savingTitle: "ออมแบบไหน (เลือกได้แบบเดียว)",
  savingHelp: "กันเงินเข้ากันชนทุกครั้งที่คุณบันทึกรายการผ่อน",
  savingPercent: "% ของราคา",
  savingFixed: "จำนวนเงินคงที่",
  percentLabel: "เปอร์เซ็นต์ของราคาสินค้า",
  percentError: "กรอกจำนวนเต็ม 1 ถึง 100",
  fixedLabel: "จำนวนเงินต่อรายการ",
  autoSave: "เปิดออมอัตโนมัติ",
  safetyNet: "ถ้าเงินในบัญชีหลักจะเหลือน้อยกว่า 500 บาท ระบบจะข้ามการออมครั้งนั้นทั้งก้อน",
  leftover: "วันเงินเดือนออก ออมส่วนที่เหลือจากงบผ่อนเข้ากันชน",
  leftoverHelp: "ใช้ได้เมื่อเปิดออมอัตโนมัติและให้ความยินยอมแล้ว ออมเดือนละไม่เกินหนึ่งครั้ง",
  consent: "ฉันยินยอมให้ KidNee ย้ายเงินจากบัญชีหลักเข้ากันชนตามกติกาด้านบน",
  consentError: "ต้องยินยอมก่อนเปิดออมอัตโนมัติ",
  save: "บันทึกการตั้งค่า",
  saving: "กำลังบันทึก...",
  saved: "บันทึกการตั้งค่าแล้ว",
  failed: "บันทึกไม่สำเร็จ ลองกดบันทึกอีกครั้งได้เลย",
  demoFill: "กรอกข้อมูลตัวอย่างของมิ้นท์",
  next: "ไปหน้าหลัก",
};

export const HOME = {
  greeting: (name: string) => `สวัสดี ${name}`,
  greetingPlain: "สวัสดี",
  thisMonthTitle: (month: string) => `ค่างวดรวมเดือน ${month}`,
  ofBudget: (budget: string) => `จากงบ ${budget}`,
  overBudgetNow: "เดือนนี้ค่างวดรวมเกินงบที่ตั้งไว้",
  withinBudgetNow: "เดือนนี้ยังอยู่ในงบ",
  installments: "รายการผ่อนของคุณ",
  totalPerMonth: (total: string) => `รวม ${total} ต่อเดือน`,
  emptyInstallments: "ยังไม่มีรายการผ่อน ก่อนซื้อชิ้นต่อไป ลองกด คิดก่อน ดูนะ",
  unnamed: "รายการผ่อน",
  perMonth: (amount: string) => `${amount}/เดือน`,
  remaining: (amount: string) => `คงเหลือ ${amount}`,
  monthsLeft: (months: number) => `ผ่อน ${months} เดือน`,
  manual: "บันทึกเอง",
  statusPaidOff: "ผ่อนครบแล้ว",
  statusCancelled: "ยกเลิกแล้ว",
  statusCancelledAfterReport: "ยกเลิกแล้ว หลังจากคุณแจ้งว่าไม่ใช่รายการของคุณ",
  statusDisputed: "คุณแจ้งว่าไม่ใช่รายการของคุณ",
  notCounted: "ไม่นับในยอดต่อเดือน",
  bufferTitle: "กันชนของคุณ",
  bufferCovers: (months: number) => `พอจ่ายค่างวดได้ประมาณ ${months} เดือน`,
  bufferNothingOwed: "ตอนนี้ไม่มีค่างวดที่ต้องจ่าย",
  upcomingTitle: "เดือนข้างหน้าที่ค่างวดรวมเกินงบ",
  upcomingNone: "5 เดือนข้างหน้ายังไม่มีเดือนไหนเกินงบ",
  upcomingRow: (total: string) => `รวม ${total}`,
  thinkCta: "คิดก่อน",
  thinkCtaHelp: "ก่อนกดผ่อนชิ้นต่อไป เช็กก่อนว่ายังไหวไหม",
};

export const THINK = {
  title: "คิดก่อนผ่อน",
  intro: "กรอกราคาและแผนผ่อน KidNee จะดูให้ว่าทุกเดือนยังไหวไหม",
  kindTitle: "ประเภทรายการ",
  kinds: { purchase: "ผ่อนสินค้า", cash_withdrawal: "กดเงินสด", cash_loan: "สินเชื่อเงินสด" },
  cashNoSaving: "รายการเงินสดจะไม่กันเงินเข้ากันชน",
  cashAmount: "ยอดเงินที่ได้รับ",
  itemName: "ชื่อสินค้า (ไม่บังคับ)",
  itemNamePlaceholder: "เช่น โทรศัพท์",
  price: "ราคาสินค้า",
  months: "จำนวนเดือนที่ผ่อน",
  monthsError: "กรอกจำนวนเต็ม 1 ถึง 600",
  monthly: "ค่างวดต่อเดือน",
  firstDue: "เริ่มจ่ายงวดแรก",
  check: "ดูว่าไหวไหม",
  checking: "กำลังคิด...",
  monthsTitle: "ค่างวดรวมแต่ละเดือน ถ้าผ่อนชิ้นนี้",
  budgetLine: (budget: string) => `เส้นประ คืองบ ${budget}`,
  overMonths: (months: string) => `เดือนที่เกินงบ: ${months}`,
  legendOk: "อยู่ในงบ",
  legendOver: "เกินงบ",
  legendRisk: "เกิน 1 ใน 3 ของรายได้",
  nowTotal: (total: string) => `ตอนนี้ค่างวดรวมเดือนละ ${total}`,
  record: "บันทึก",
  recording: "กำลังบันทึก...",
  notBuying: "ยังไม่ซื้อ",
  notBuyingDone: "โอเค ยังไม่ซื้อ ไว้ค่อยคิดใหม่ได้เสมอ",
  savedTitle: "บันทึกรายการผ่อนแล้ว",
  savedLabel: "กันเงินเข้ากันชนให้แล้ว",
  savedNothing: "ครั้งนี้ไม่ได้กันเงินเข้ากันชน",
  newTotalLabel: "ค่างวดรวมต่อเดือนตอนนี้",
  failed: "ติดต่อระบบไม่สำเร็จ ลองกดอีกครั้งได้เลย",
  demoTitle: "Demo: ลองตัวอย่างของมิ้นท์",
  demoScenario: { GREEN: "ไหว", YELLOW: "เสี่ยง", RED: "ไม่ไหว" },
  backHome: "กลับหน้าหลัก",
  another: "คิดอีกรายการ",
};

export const BUFFER = {
  title: "กันชน",
  balance: "ยอดในกันชน",
  moveTitle: "ย้ายกลับบัญชีหลัก",
  moveHelp: "เงินในกันชนเป็นของคุณ ย้ายกลับได้ทุกเมื่อ",
  amount: "จำนวนเงินที่จะย้าย",
  move: "ย้ายกลับบัญชีหลัก",
  moving: "กำลังย้าย...",
  moved: (amount: string) => `ย้าย ${amount} กลับบัญชีหลักแล้ว`,
  aboveBalance: "ยอดในกันชนไม่พอสำหรับจำนวนนี้",
};

export const PAYDAY_OUTCOME: Record<PaydayOutcome, string> = {
  over_budget: "เดือนนี้ค่างวดเกินงบ",
  leftover_saved: "ออมส่วนที่เหลือจากงบแล้ว",
  no_leftover: "ค่างวดพอดีงบ ไม่มีส่วนเหลือให้ออม",
  leftover_off: "ไม่ได้เปิดการออมส่วนที่เหลือ",
  safety_net: "ข้ามการออมเพราะเงินในบัญชีหลักจะเหลือน้อยกว่า 500 บาท",
};
