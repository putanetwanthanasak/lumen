/**
 * Every Thai string the screens show (DESIGN.md section 8).
 *
 * Rules: friendly helper tone, never scolding; no em dash; no claim we cannot back;
 * the one-third rule is "ธปท. แนะนำ" (guidance), never "ธปท. กำหนด" (L64, L65).
 * Amounts come in already formatted by money.ts; this file never touches money.
 */
import type { ConsolidationReason, MovementKind, PaydayOutcome, Verdict } from "./api-types.ts";

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
    label: "อยู่ในงบ",
    detail: "ค่างวดรวมทุกเดือนตลอดแผนผ่อนนี้ไม่เกินงบที่คุณตั้งไว้",
  },
  YELLOW: {
    icon: "alert",
    label: "บางเดือนเกินงบ",
    detail: "มีบางเดือนที่ค่างวดรวมเกินงบที่คุณตั้งไว้ ดูได้จากกราฟด้านล่าง",
  },
  RED: {
    icon: "stop",
    label: "เกินเกณฑ์ที่ ธปท. แนะนำ (1 ใน 3 ของรายได้)",
    detail: "บางเดือนค่างวดรวมสูงกว่าเกณฑ์ที่ ธปท. แนะนำ คือค่างวดหนี้ทั้งหมดต่อเดือนไม่ควรเกิน 1 ใน 3 ของรายได้",
  },
};

export const ADVISORY_NOTE = "นี่เป็นคำแนะนำเท่านั้น คุณบันทึกรายการได้เสมอ";

/** What each accent colour means (accent.ts); always shown with its icon. */
export const ACCENT_LABEL = {
  debt: "ภาพรวมหนี้",
  buffer: "กันชน",
  warn: "เกินงบ",
  bank: "ทางเลือกจากธนาคาร",
  ai: "ผู้ช่วย KidNee",
  quiet: "ข้อมูลเพิ่มเติม",
};

export const NAV = {
  home: "หน้าหลัก",
  // Short labels: a quarter of 390px, one line each. Full names stay on titles and buttons.
  think: "เช็กก่อนผ่อน",
  buffer: "กันชน",
  alerts: "แจ้งเตือน",
  settings: "ตั้งค่า",
  back: "ย้อนกลับ",
  menu: "เมนูหลัก",
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

/** A field the API refused with 422 (item 7): said next to that field, never the raw error. */
export const REJECTED = "ระบบไม่รับค่านี้ ลองแก้แล้วกดอีกครั้ง";

export const MONEY_ERRORS = {
  empty: "กรอกจำนวนเงินด้วยนะ",
  format: "กรอกเป็นตัวเลข เช่น 12000 หรือ 12,000.50",
  decimals: "ทศนิยมได้ไม่เกิน 2 ตำแหน่ง",
  zero: "จำนวนเงินต้องมากกว่า 0",
  too_large: "จำนวนเงินมากเกินไป",
} as const;

export const SETTINGS = {
  title: "เริ่มต้นใช้ KidNee",
  intro: "ตั้งค่าครั้งเดียว KidNee จะช่วยประเมินว่าผ่อนเพิ่มแล้วค่างวดรวมยังอยู่ในงบหรือไม่",
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
  demoFill: "กรอกข้อมูลตัวอย่างของม่อน",
  next: "ไปหน้าหลัก",
};

export const HOME = {
  toAccount: "บัญชีหลัก", // the way back to the host app's home (#/account)
  greeting: (name: string) => `สวัสดี ${name}`,
  greetingPlain: "สวัสดี",
  thisMonthTitle: (month: string) => `ค่างวดรวมเดือน ${month}`,
  seeAllMonths: "ดูทุกเดือน", // read aloud with the hero's chevron
  ofBudget: (budget: string) => `จากงบ ${budget}`,
  withinBudgetNow: "เดือนนี้ยังอยู่ในงบ",
  installments: "รายการผ่อนของคุณ",
  totalPerMonth: (total: string) => `รวม ${total} ต่อเดือน`,
  emptyInstallments: "ยังไม่มีรายการผ่อน ก่อนผ่อนชิ้นต่อไป กด เช็กก่อนผ่อน ได้เลย",
  noPlatform: "ไม่ระบุแอป",
  unnamed: "รายการผ่อน",
  perMonth: (amount: string) => `${amount}/เดือน`,
  remaining: (amount: string) => `คงเหลือ ${amount}`,
  monthsLeft: (months: number) => `ผ่อน ${months} เดือน`,
  // From GET /debts/months (UI-43): where an installment is in its plan.
  schedule: (no: number, total: number, last: string | null) =>
    last === null ? `งวดที่ ${no} จาก ${total}` : `งวดที่ ${no} จาก ${total} · หมด ${last}`,
  scheduleLater: (first: string, last: string | null) => (last === null ? `เริ่ม ${first}` : `เริ่ม ${first} · หมด ${last}`),
  manual: "บันทึกเอง",
  statusPaidOff: "ผ่อนครบแล้ว",
  statusCancelled: "ยกเลิกแล้ว",
  statusCancelledAfterReport: "ยกเลิกแล้ว หลังจากคุณแจ้งว่าไม่ใช่รายการของคุณ",
  statusDisputed: "คุณแจ้งว่าไม่ใช่รายการของคุณ",
  statusConsolidated: "ปิดด้วยสินเชื่อรวมหนี้แล้ว",
  notCounted: "ไม่นับในยอดต่อเดือน", // cancelled, or reported "not me": never under "ผ่อนครบแล้ว"
  finished: (count: number) => `ผ่อนครบแล้ว ${count} รายการ`,
  allInBudget: (later: number) => `เดือนนี้และอีก ${later} เดือนอยู่ในงบ`,
  // The hero's one warning line (UI-41, UI-42), months already in Thai.
  overWarning: (count: number, first: string, last: string, together: boolean) =>
    count === 1
      ? `เกินงบ 1 เดือน (${first})`
      : together
        ? `เกินงบ ${count} เดือน (${first} ถึง ${last})`
        : `เกินงบ ${count} เดือน (ในช่วง ${first} ถึง ${last})`,
  bufferTitle: "กันชนของคุณ ›",
  walletCovers: (months: number) => `พอ ${months} เดือน`,
  walletCoversNone: "ยังไม่พอ 1 เดือน",
  walletNothingOwed: "ไม่มีค่างวด",
  thinkCta: "เช็กก่อนผ่อน",
  thinkCtaHelp: "ก่อนกดผ่อนชิ้นต่อไป ประเมินภาระผ่อนรายเดือนได้ที่นี่",
};

export const THINK = {
  title: "เช็กก่อนผ่อน",
  intro: "กรอกราคาและแผนผ่อน KidNee จะประเมินค่างวดรวมของทุกเดือนตลอดแผนผ่อนนี้",
  kindTitle: "ประเภทรายการ",
  kinds: { purchase: "ผ่อนสินค้า", cash_withdrawal: "กดเงินสด", cash_loan: "สินเชื่อเงินสด" },
  cashNoSaving: "รายการเงินสดจะไม่กันเงินเข้ากันชน",
  cashAmount: "ยอดเงิน",
  cashLink: "เป็นรายการเงินสด?",
  itemName: "ชื่อสินค้า (ไม่บังคับ)",
  itemNamePlaceholder: "เช่น โทรศัพท์",
  price: "ราคาสินค้า",
  months: "จำนวนเดือนที่ผ่อน",
  monthChip: (months: number) => `${months} เดือน`,
  monthsError: "กรอกจำนวนเต็ม 1 ถึง 600",
  monthly: "ค่างวดต่อเดือน",
  monthlyHelp: "คิดแบบผ่อน 0% ถ้าแอปแจ้งยอดต่อเดือนไม่ตรงนี้ แก้ให้ตรงกับแอปได้",
  platform: "แอปที่ผ่อน (ไม่บังคับ)",
  platformPlaceholder: "เช่น ShopDemo",
  platformTooLong: "ชื่อแอปยาวได้ไม่เกิน 60 ตัวอักษร",
  firstDue: "เริ่มจ่ายงวดแรก",
  firstDueHelp: "ดูได้ในหน้าสรุปก่อนกดผ่อนของแอปผ่อน",
  firstDueThis: "เดือนนี้",
  firstDueNext: "เดือนหน้า",
  firstDueError: "เลือกเดือนที่เริ่มจ่ายงวดแรก",
  check: "ประเมินภาระผ่อน",
  checkNeeds: "กรอกราคา จำนวนเดือน ค่างวด และเดือนเริ่มจ่ายให้ครบก่อน",
  checking: "กำลังประเมิน...",
  monthsTitle: "ค่างวดรวมแต่ละเดือน ถ้าผ่อนชิ้นนี้",
  budgetLine: (budget: string) => `เส้นประ คืองบ ${budget}`,
  // The plain line under the chart (UI-41), months already in Thai.
  overSummary: (count: number, first: string, last: string, together: boolean) =>
    count === 1
      ? `เกินงบ 1 เดือน: ${first}`
      : together
        ? `เกินงบ ${count} เดือน: ${first} ถึง ${last}`
        : `เกินงบ ${count} เดือน ในช่วง ${first} ถึง ${last}`,
  legendOk: "อยู่ในงบ",
  legendOver: "เกินงบ",
  legendRisk: "เกินเกณฑ์ที่ ธปท. แนะนำ",
  legendExisting: "ค่างวดที่มีอยู่", // the grey lower part of a bar
  legendCandidate: "ชิ้นใหม่:", // before the statuses: the coloured top is the item being checked
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
  demoTitle: "Demo: ลองตัวอย่างของม่อน",
  demoScenario: { GREEN: "อยู่ในงบ", YELLOW: "เกินงบ", RED: "เกินเกณฑ์" },
  backHome: "กลับหน้าหลัก",
  another: "เช็กรายการอื่น",
  resultTitle: "ผลการประเมิน",
  edit: "แก้ไข",
  summary: (what: string, price: string, months: number, monthly: string, start: string) =>
    `${what} ${price} · ${months} เดือน · เดือนละ ${monthly} · เริ่ม ${start}`,
  summaryCash: "เงินสด",
  summaryItem: "สินค้า",
  savingTitle: "ถ้าบันทึก จะกันเงินเข้ากันชน",
  savingNone: "ถ้าบันทึก ครั้งนี้จะไม่ได้กันเงินเข้ากันชน",
  savingNoneHelp: "เช่น รายการเงินสด ปิดการออมอัตโนมัติ หรือเงินในบัญชีหลักจะเหลือน้อยกว่า 500 บาท",
  seeMonths: "ดูภาระผ่อนรายเดือน",
  noDraft: "ยังไม่มีรายการที่ประเมิน กรอกข้อมูลก่อนนะ",
  toForm: "ไปกรอกข้อมูล",
};

// A month over budget and the buffer (UI-46), on Home, the buffer screen and the months.
export const BUFFER_STATE = {
  over: (month: string, shortfall: string) => `${month} เกินงบ ${shortfall}`,
  partly: (month: string, shortfall: string, prepared: string, gap: string) =>
    `${month} เกินงบ ${shortfall} เตรียมจากกันชนแล้ว ${prepared} ยังขาด ${gap}`,
  // The money is in the main account; the user still pays in the app (never "จ่ายแล้ว", UI-55).
  prepared: (month: string, shortfall: string) =>
    `${month} เกินงบ ${shortfall} ย้ายจากกันชนเข้าบัญชีหลักแล้ว อย่าลืมจ่ายค่างวดในแอปผ่อน`,
  use: "ใช้กันชนจ่ายส่วนที่เกิน",
  // The buffer screen's move for a month, as three steps (UI-47). "ย้าย" between the
  // user's own accounts, never "โอน".
  sectionTitle: "เดือนที่ค่างวดเกินงบ",
  step1: (amount: string) => `ใช้กันชน ${amount}`,
  step1Done: (amount: string, before: string, after: string) => `ใช้กันชน ${amount} (กันชน ${before} → ${after})`,
  step2: (amount: string) => `ย้ายเข้าบัญชีหลัก +${amount}`,
  step3: (month: string, total: string) => `จ่ายค่างวดในแอปผ่อน (ผู้ใช้ทำเอง) ค่างวด ${month} ${total}`,
  stepsLabel: "ขั้นตอน",
  helper: "ย้ายก่อนวันที่แอปผ่อนตัดเงิน แนะนำทำในวันเงินเดือนเข้า",
  moving: "กำลังย้าย...",
  success: (amount: string, balance: string) =>
    `ย้าย ${amount}เข้าบัญชีหลักแล้ว กันชนเหลือ ${balance} จ่ายค่างวดในแอปผ่อนได้เลย`,
  empty: "กันชนว่าง ยังไม่มีเงินให้ย้าย",
};

export const MONTHS_VIEW = {
  title: "ภาระผ่อนรายเดือน",
  intro: "ค่างวดรวมของทุกเดือน ตั้งแต่เดือนนี้ถึงเดือนสุดท้ายที่มีงวดผ่อน แตะเดือนเพื่อดูรายการ",
  ofBudget: (total: string, budget: string) => `${total} จากงบ ${budget}`,
  ok: "อยู่ในงบ",
  over: "เกินงบ",
  risk: "เกินเกณฑ์ที่ ธปท. แนะนำ",
  bufferReady: "กันชนเตรียมเงินแล้ว", // a month over budget the buffer covered (UI-54)
  showItems: "ดูรายการ",
  hideItems: "ซ่อนรายการ",
  instalmentOf: (n: number, total: number) => `งวดที่ ${n} จาก ${total}`,
  lastInstalment: "งวดสุดท้าย",
  empty: "ไม่มีงวดผ่อนที่ต้องจ่ายตั้งแต่เดือนนี้",
  // One quiet line at the bottom (Session 17): the user's own check against the app.
  scamCheck:
    "ยอดในแอปผ่อนไม่ตรงกับที่นี่? อาจมีรายการที่คุณไม่ได้ทำ ติดต่อแอปผ่อนโดยตรงจากช่องทางในแอป อย่าโอนเงินให้ใครที่โทรมาทวง",
};

export const BUFFER = {
  title: "กันชน",
  intro: "เงินที่กันไว้ทุกครั้งที่ผ่อน ไว้ช่วยในเดือนที่ค่างวดแน่น",
  balance: "ยอดในกันชน",
  covers: (months: number) => `พอจ่ายค่างวดได้ประมาณ ${months} เดือน`,
  coversNone: "ยังไม่พอจ่ายค่างวดครบหนึ่งเดือน",
  nothingOwed: "ตอนนี้ไม่มีค่างวดที่ต้องจ่าย",
  monthlyTotal: (total: string) => `ค่างวดรวมต่อเดือนตอนนี้ ${total}`,
  moveTitle: "ย้ายกลับบัญชีหลัก",
  moveHelp: "เงินในกันชนเป็นของคุณ ย้ายกลับได้ทุกเมื่อ ไม่มีเงื่อนไข",
  amount: "จำนวนเงินที่จะย้าย",
  move: "ย้ายกลับบัญชีหลัก",
  moving: "กำลังย้าย...",
  moved: (amount: string) => `ย้าย ${amount} กลับบัญชีหลักแล้ว`,
  balanceAfter: (amount: string) => `เหลือในกันชน ${amount}`,
  aboveBalance: "ยอดในกันชนไม่พอสำหรับจำนวนนี้ ลองใส่จำนวนที่น้อยลง",
  failed: "ยังไม่แน่ใจว่าย้ายสำเร็จหรือไม่ กดย้ายอีกครั้งด้วยจำนวนเดิมได้เลย ระบบจะไม่ย้ายซ้ำ",
  another: "ย้ายอีกจำนวน",
  seeInAccount: "ดูในบัญชีหลัก", // after a move: opens #/account
};

export const PAYDAY_OUTCOME: Record<PaydayOutcome, string> = {
  over_budget: "เดือนนี้ค่างวดเกินงบ",
  leftover_saved: "ออมส่วนที่เหลือจากงบแล้ว",
  no_leftover: "ค่างวดพอดีงบ ไม่มีส่วนเหลือให้ออม",
  leftover_off: "ไม่ได้เปิดการออมส่วนที่เหลือ",
  safety_net: "ข้ามการออมเพราะเงินในบัญชีหลักจะเหลือน้อยกว่า 500 บาท",
};

export const ALERTS = {
  title: "แจ้งเตือน",
  empty: "ยังไม่มีแจ้งเตือน ทุกครั้งที่มีหนี้ใหม่ KidNee จะบอกทันที",
  openMonths: "ดูภาระผ่อนรายเดือน",
  openBuffer: "ดูกันชน",
  more: (shown: number, count: number) => `แสดง ${shown} รายการล่าสุด จากทั้งหมด ${count} รายการ`,
};

/**
 * The assistant plan's parts (GET /assistant/plan), spread over the screens:
 * ภาระผ่อนรายเดือน, the form hint, the buffer card and Home's consolidation card.
 * Every number is the API's; these only put words around them (assistantText.ts).
 */
export const ASSIST = {
  backInBudget: (month: string) => `กลับมาอยู่ในงบเดือน ${month}`,
  allInBudget: "ทุกเดือนอยู่ในงบ",
  pauseNow: "ตอนนี้ยังไม่ควรผ่อนเพิ่ม",
  safeNew: (month: string, amount: string) => `ตั้งแต่ ${month} ผ่อนเพิ่มได้ไม่เกินเดือนละ ${amount}`,
  safeNone: (month: string) => `ตั้งแต่ ${month} ยังผ่อนเพิ่มไม่ได้โดยไม่เกินงบ`,
  safeTerm: (months: number) => `(คิดจากแผนผ่อน ${months} เดือน ไม่เกินงบ และไม่เกิน 1 ใน 3 ของรายได้)`,
  formHint: (amount: string, month: string) => `ผ่อนเพิ่มได้ไม่เกินเดือนละ ${amount} ตั้งแต่ ${month}`,
  bufferTitle: "ถ้าเดือนไหนเกินงบ",
  bufferNone: "ทุกเดือนอยู่ในงบ ยังไม่ต้องใช้กันชน",
  shortfall: (amount: string) => `ค่างวดส่วนที่เกินงบรวมทุกเดือน ${amount}`,
  covered: (balance: string) => `กันชน ${balance} พอจ่ายส่วนที่เกินได้ทั้งหมด`,
  stillShort: (balance: string, short: string) => `กันชน ${balance} ยังขาดอีก ${short}`,
  notPrepared: (gap: string) => `ยังไม่ได้เตรียม ${gap}`,
  allPrepared: "เตรียมเงินจากกันชนครบทุกเดือนที่เกินงบแล้ว",
  notNeeded: "ตอนนี้ยังไม่จำเป็นต้องรวมหนี้",
  notWorth: "ตอนนี้ยังไม่คุ้มที่จะรวมหนี้",
  reason: {
    NOT_NEEDED: "ยังไม่มีช่วงที่ค่างวดรวมเกินงบติดกัน 3 เดือนขึ้นไป",
    OVERDUE_DEBT: "มีรายการที่ค้างชำระอยู่ ควรจัดการรายการนั้นก่อน",
    DISPUTED_DEBT: "มีรายการที่คุณแจ้งว่าไม่ใช่ของคุณ จึงยังรวมไม่ได้",
    ESTIMATE_TOO_LARGE: "ยอดรวมสูงเกินกว่าที่จะประมาณได้",
    PAYMENT_ABOVE_BUDGET: "ถึงรวมแล้ว ค่างวดใหม่ก็ยังเกินงบ",
    PAYMENT_ABOVE_ONE_THIRD_OF_INCOME: "ถึงรวมแล้ว ค่างวดใหม่ก็ยังเกินเกณฑ์ที่ ธปท. แนะนำ (1 ใน 3 ของรายได้)",
    ELIGIBLE: "",
  } satisfies Record<ConsolidationReason, string>,
  worth: "รวมหนี้อาจช่วยให้ทุกเดือนกลับมาอยู่ในงบ",
  exampleTag: "ตัวอย่างการประมาณ",
  newMonthly: "ค่างวดใหม่ต่อเดือน",
  totalCost: "ต้นทุนรวมทั้งหมด",
  nowColumn: "ตอนนี้",
  ifConsolidated: "ถ้ารวมหนี้ (ตัวอย่าง)",
  totalAll: "ยอดรวมทั้งหมด",
  terms: (months: number, rate: string) => `ผ่อน ${months} เดือน ดอกเบี้ยสมมติ ${rate}% ต่อปี (ไม่ใช่อัตราจริง)`,
  benefit: (reduction: string) => `ค่างวดลดลงเดือนละ ${reduction} ทุกเดือนกลับมาอยู่ในงบ`,
  interested: "สนใจรวมหนี้",
  bankWillCall: "ธนาคารจะติดต่อกลับเพื่อพิจารณา",
  bankDecides: "ธนาคารพิจารณาจากข้อมูลของธนาคารเอง ตัวเลขนี้ยังไม่ใช่ข้อเสนอ",
  aiTitle: "ผู้ช่วย KidNee สรุปให้ฟัง",
  aiLoading: "กำลังสรุป...",
  aiMore: "อ่านต่อ ›",
  aiLess: "ย่อ",
};

export const DEMO = {
  paydayFailed: "จำลองไม่สำเร็จ ลองอีกครั้งได้เลย",
  open: "Demo",
  title: "Demo panel",
  note: "สำหรับนำเสนอเท่านั้น ไม่ใช่ส่วนหนึ่งของแอป",
  close: "ปิด",
  paydayTitle: "จำลองวันเงินเดือนออก",
  paydayMonth: "เดือน",
  paydayRun: "จำลองวันเงินเดือนออก",
  paydayRepeat: "เดือนนี้จำลองไปแล้ว ผลเดิม ไม่มีอะไรเปลี่ยน",
  paydayResult: (total: string, budget: string) => `ค่างวดรวม ${total} งบ ${budget}`,
  paydayUnavailable: "ยังเปิดใช้ไม่ได้ (ต้องเปิด DEMO_ENDPOINTS_ENABLED ที่ backend)",
  scenesTitle: "ฉาก",
  sceneFirst: "เริ่มใหม่: ยังไม่ตั้งค่า",
  scenePersona: "ม่อน: ตั้งค่าแล้ว",
  sceneOver: "ม่อน: มีเดือนเกินงบ",
  sceneOverNow: "ม่อน: เกินงบตั้งแต่เดือนนี้",
  sceneOverEmpty: "ม่อน: มีเดือนเกินงบ กันชนว่าง",
  sceneAiSlow: "ม่อน: ผู้ช่วยกำลังสรุป (ตอบช้า)",
  sceneAiFailing: "ม่อน: เรียกผู้ช่วยไม่สำเร็จ (ใช้คำของแอป)",
  done: "เปลี่ยนฉากแล้ว",
  personaTitle: "ผู้ใช้ตัวอย่าง",
  personaNote: "สลับผู้ใช้ที่ seed ไว้ใน lumen_kidnee (X-Demo-User)",
  personaPlain: "ผู้ใช้",
};

/**
 * The host bank app's home (#/account, Session 21). Generic on purpose: no bank,
 * product or company name, and a masked placeholder in place of an account number.
 */
export const ACCOUNT = {
  title: "บัญชีหลัก",
  savings: "ออมทรัพย์",
  maskedNumber: "xxx-x-x1234-x",
  available: "ยอดเงินที่ใช้ได้",
  baht: "บาท",
  mockData: "ข้อมูลจำลองสำหรับเดโม",
  seeRecent: "ดูรายการล่าสุด",
  myAccounts: "บัญชีของฉัน",
  loadedAt: (time: string) => `ข้อมูล ณ เวลา ${time} น.`,
  // The header's example buttons (Session 22): icons only, so each has its label.
  header: { profile: "โปรไฟล์", bell: "การแจ้งเตือน", power: "ออกจากระบบ" },
  tabsLabel: "ประเภทบริการ",
  tabs: { account: "บัญชี", card: "บัตร", loan: "สินเชื่อ", invest: "ลงทุน" },
  shortcutsLabel: "ทางลัด",
  shortcuts: {
    transfer: "โอนเงิน",
    bill: "จ่ายบิล",
    topup: "เติมเงิน",
    scan: "สแกนจ่าย",
    cashout: "ถอนไม่ใช้บัตร",
    statement: "รายการเดินบัญชี",
    goal: "ตั้งเป้าออม",
  },
  newBadge: "ใหม่",
  shortcutNote: "ปุ่มตัวอย่าง ใช้ไม่ได้ในเดโม",
  services: "บริการแนะนำ",
  thisMonth: (total: string) => `ภาระผ่อนเดือนนี้ ${total}`,
  buffer: (balance: string) => `กันชน ${balance}`,
  setUp: "ยังไม่ได้ตั้งค่า KidNee แตะเพื่อเริ่มใช้",
  recent: "รายการล่าสุด",
  movement: {
    auto_save: "กันเงินเข้ากันชน KidNee",
    leftover_save: "เก็บงบที่ใช้ไม่หมดเข้ากันชน",
    withdrawal: "ย้ายเงินจากกันชน KidNee",
  } satisfies Record<MovementKind, string>,
  forMonth: (month: string) => `สำหรับ ${month}`,
  // The passbook's printed line (Session 23, UI-70): short, as a passbook prints them.
  printed: {
    auto_save: "กันเงินเข้ากันชน",
    leftover_save: "เก็บงบเข้ากันชน",
    withdrawal: "ย้ายจากกันชน",
  } satisfies Record<MovementKind, string>,
  empty: "ยังไม่มีรายการ",
  nav: { menu: "เมนูบัญชี", home: "หน้าแรก", history: "ธุรกรรม", scan: "สแกน", kidnee: "KidNee", profile: "โปรไฟล์" },
};
