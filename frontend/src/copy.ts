/**
 * Every Thai string the screens show (DESIGN.md section 8).
 *
 * Rules: friendly helper tone, never scolding; no em dash; no claim we cannot back;
 * the one-third rule is "ธปท. แนะนำ" (guidance), never "ธปท. กำหนด" (L64, L65).
 * Amounts come in already formatted by money.ts; this file never touches money.
 */
import type { ConsolidationReason, PaydayOutcome, Verdict } from "./api-types.ts";

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

export const NAV = {
  home: "หน้าหลัก",
  // Short labels: a quarter of 390px, one line each. Full names stay on titles and buttons.
  think: "ตรวจสอบ",
  buffer: "กันชน",
  alerts: "แจ้งเตือน",
  alertsUnread: (count: number) => `แจ้งเตือน ยังไม่ได้อ่าน ${count} รายการ`,
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
  demoFill: "กรอกข้อมูลตัวอย่างของมิ้นท์",
  next: "ไปหน้าหลัก",
};

export const HOME = {
  greeting: (name: string) => `สวัสดี ${name}`,
  greetingPlain: "สวัสดี",
  thisMonthTitle: (month: string) => `ค่างวดรวมเดือน ${month}`,
  seeAllMonths: "ดูทุกเดือน ›",
  ofBudget: (budget: string) => `จากงบ ${budget}`,
  overBudgetNow: "เดือนนี้ค่างวดรวมเกินงบที่ตั้งไว้",
  withinBudgetNow: "เดือนนี้ยังอยู่ในงบ",
  installments: "รายการผ่อนของคุณ",
  totalPerMonth: (total: string) => `รวม ${total} ต่อเดือน`,
  emptyInstallments: "ยังไม่มีรายการผ่อน ก่อนผ่อนชิ้นต่อไป กด ตรวจสอบก่อนผ่อน ได้เลย",
  noPlatform: "ไม่ระบุแอป",
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
  thinkCta: "ตรวจสอบก่อนผ่อน",
  thinkCtaHelp: "ก่อนกดผ่อนชิ้นต่อไป ประเมินภาระผ่อนรายเดือนได้ที่นี่",
};

export const THINK = {
  title: "ตรวจสอบก่อนผ่อน",
  intro: "กรอกราคาและแผนผ่อน KidNee จะประเมินค่างวดรวมของทุกเดือนตลอดแผนผ่อนนี้",
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
  checking: "กำลังประเมิน...",
  monthsTitle: "ค่างวดรวมแต่ละเดือน ถ้าผ่อนชิ้นนี้",
  budgetLine: (budget: string) => `เส้นประ คืองบ ${budget}`,
  overMonths: (months: string) => `เดือนที่เกินงบ: ${months}`,
  legendOk: "อยู่ในงบ",
  legendOver: "เกินงบ",
  legendRisk: "เกินเกณฑ์ที่ ธปท. แนะนำ",
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
  demoScenario: { GREEN: "อยู่ในงบ", YELLOW: "เกินงบ", RED: "เกินเกณฑ์" },
  backHome: "กลับหน้าหลัก",
  another: "ตรวจสอบรายการอื่น",
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

export const MONTHS_VIEW = {
  title: "ภาระผ่อนรายเดือน",
  intro: "ค่างวดรวมของทุกเดือน ตั้งแต่เดือนนี้ถึงเดือนสุดท้ายที่มีงวดผ่อน แตะเดือนเพื่อดูรายการ",
  ofBudget: (total: string, budget: string) => `${total} จากงบ ${budget}`,
  ok: "อยู่ในงบ",
  over: "เกินงบ",
  risk: "เกินเกณฑ์ที่ ธปท. แนะนำ",
  showItems: "ดูรายการ",
  hideItems: "ซ่อนรายการ",
  instalmentOf: (n: number, total: number) => `งวดที่ ${n} จาก ${total}`,
  lastInstalment: "งวดสุดท้าย",
  empty: "ไม่มีงวดผ่อนที่ต้องจ่ายตั้งแต่เดือนนี้",
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
  unread: "ใหม่",
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
  consolidateTitle: "ควรรวมหนี้ไหม",
  notWorth: "ตอนนี้ยังไม่คุ้มที่จะรวมหนี้",
  reason: {
    NOT_NEEDED: "ยังไม่มีช่วงที่ค่างวดรวมเกินงบติดกัน 3 เดือนขึ้นไป",
    OVERDUE_DEBT: "มีรายการที่ค้างชำระอยู่ ควรจัดการรายการนั้นก่อน",
    DISPUTED_DEBT: "มีรายการที่คุณแจ้งว่าไม่ใช่ของคุณ จึงยังรวมไม่ได้",
    ESTIMATE_TOO_LARGE: "ยอดรวมสูงเกินกว่าที่จะประมาณได้",
    PAYMENT_ABOVE_BUDGET: "ถึงรวมแล้ว ค่างวดใหม่ก็ยังเกินงบ",
    ELIGIBLE: "",
  } satisfies Record<ConsolidationReason, string>,
  worth: "รวมหนี้อาจช่วยให้ทุกเดือนกลับมาอยู่ในงบ",
  exampleTag: "ตัวอย่างการประมาณ",
  newMonthly: "ค่างวดใหม่ต่อเดือน",
  totalCost: "ต้นทุนรวมทั้งหมด",
  terms: (months: number, rate: string) => `ผ่อน ${months} เดือน ดอกเบี้ยสมมติ ${rate}% ต่อปี (ไม่ใช่อัตราจริง)`,
  extraCost: (extra: string, now: string) => `จ่ายรวมมากกว่าแผนเดิม ${extra} (ตอนนี้คงเหลือ ${now})`,
  interested: "สนใจรวมหนี้",
  bankWillCall: "ธนาคารจะติดต่อกลับเพื่อพิจารณา",
  bankDecides: "ธนาคารพิจารณาจากข้อมูลของธนาคารเอง ตัวเลขนี้ยังไม่ใช่ข้อเสนอ",
  aiTitle: "ผู้ช่วย KidNee สรุปให้ฟัง",
  aiHelp: "สรุปภาพรวมหนี้ กันชน และการรวมหนี้ในไม่กี่ประโยค",
  aiButton: "สรุปให้ฟัง",
  aiLoading: "กำลังสรุป...",
  aiExample: "ตัวอย่าง",
  aiFailed: "สรุปไม่สำเร็จ ลองอีกครั้งได้เลย",
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
  scenePersona: "มิ้นท์: ตั้งค่าแล้ว",
  sceneOver: "มิ้นท์: มีเดือนเกินงบ",
  sceneOverNow: "มิ้นท์: เกินงบตั้งแต่เดือนนี้",
  done: "เปลี่ยนฉากแล้ว",
};
