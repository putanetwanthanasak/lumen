# KidNee (คิดหนี้): design system and screens

Concept prototype for a 2026 hackathon (Track 1). This file is the design
source of truth for `frontend/`. Copy lives in `frontend/src/copy.ts`, tokens in
`frontend/src/index.css`, and API types in `frontend/src/api-types.ts`; this file
explains them and must stay in step with them.

Status (2026-10-27): screens 1 to 3 are built (PR A). Screens 4 to 7 and the Demo
panel follow in PR B. All data is mocked in `src/mock/` until the next backend
session sets `USE_MOCK = false` in `src/api.ts`.

---

## 1. Purpose and users

**Who:** first jobbers aged 22 to 30 with their first salary, a phone full of
shopping apps, and two or three BNPL plans already running.

**Problem:** each plan looks small on its own ("แค่เดือนละ 1,200"). Nobody adds
them up month by month, so the month when three plans overlap arrives as a
surprise on payday.

**What KidNee does** (a concept for a banking-style app, shown here standalone; it is
not any bank's service):
1. Keeps every installment in one list, with this month's total against a budget
   the user chose.
2. **คิดก่อน**: before buying, the user enters the price and the plan, and sees
   every month of that plan with the new total, and a verdict: ไหว, เสี่ยง or
   ไม่ไหว.
3. Saves a little into a **buffer** each time an installment is recorded, so a
   heavy month can be covered.
4. Alerts on every new debt and on payday when a month is over budget.

**Principle: advice only, never a block.** KidNee never stops a purchase and never
holds the user's money. Recording is always allowed, whatever the verdict.

## 2. Name, tone and logo

- **Name:** KidNee, with the Thai คิดหนี้ ("think about debt") next to it.
  CLAUDE.md rule 5 still says the display name is "Lumen"; the backend session
  updates that rule on 2026-10-28. Lumen stays the name of the backend system.
- **Primary action:** "คิดก่อน" (think first). It is the largest button on Home.
- **Tone:** a friendly older sibling who is good with money. Short sentences,
  "เรา/คุณ", no scolding, no fear. Say what is true and what the user can do next.
  - Yes: "มีบางเดือนที่ค่างวดรวมเกินงบ ลองดูกราฟด้านล่างว่าเป็นเดือนไหน"
  - No: "คุณกำลังก่อหนี้เกินตัว" (judges the person)
  - Yes: "โอเค ยังไม่ซื้อ ไว้ค่อยคิดใหม่ได้เสมอ"
- **Logo:** abstract and friendly, never a realistic kidney or any organ. Two
  options, both inline SVG in `src/components/Logo.tsx`:

**Option A, "Bean" (used in the app).** A soft bean with a smile and a small
gold coin: "think, then keep something back".

```svg
<svg viewBox="0 0 48 48" width="48" height="48">
  <path d="M14 8c6-4 15-3 20 2 4 4 3 9 0 12-2 2-2 4 0 6 4 4 4 11-2 15-6 4-16 4-22-2C4 35 4 25 6 19c1.5-5 4-9 8-11Z" fill="#138a52"/>
  <path d="M16 13c3-2 7-2 10 0" stroke="#aee9c8" stroke-width="3" stroke-linecap="round" fill="none"/>
  <circle cx="17" cy="25" r="2" fill="#ffffff"/><circle cx="26" cy="25" r="2" fill="#ffffff"/>
  <path d="M17 31c2.5 2.5 6.5 2.5 9 0" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" fill="none"/>
  <circle cx="37" cy="36" r="6" fill="#ffc94d"/>
  <path d="M37 33v6" stroke="#0a3f28" stroke-width="2" stroke-linecap="round"/>
</svg>
```

**Option B, "Filter".** Three rounded layers narrowing to one coin: "only what
fits passes through".

```svg
<svg viewBox="0 0 48 48" width="48" height="48">
  <rect x="6" y="7" width="36" height="8" rx="4" fill="#7fd8a7"/>
  <rect x="11" y="18" width="26" height="8" rx="4" fill="#22a565"/>
  <rect x="16" y="29" width="16" height="8" rx="4" fill="#0d6e42"/>
  <circle cx="24" cy="43" r="4" fill="#ffc94d"/>
</svg>
```

## 3. Brand and content rules

1. **Never** use the names or logos of real banks, their tech arms or app names,
   or real shopping platforms (CLAUDE.md rule 5), and no wording that suggests an
   official bank service. The only vendor name is **ShopDemo**. A green family
   common in Thai personal-finance apps is used; no logo or mark is copied.
2. **Footer on every screen:** "Concept prototype สำหรับการแข่งขัน".
3. **Thai text has no em dash**, anywhere (rule 10). Use a space, a colon or a
   new sentence.
4. **No claim we cannot back.** The one-third rule is Bank of Thailand
   financial-literacy guidance, so it is always "ธปท. แนะนำ", never "ธปท. กำหนด".
   Screens 6 and 7 are labelled as examples.
5. **The verdict is never colour only:** an icon, the Thai label and a sentence.
   | Verdict | Icon | Label |
   |---|---|---|
   | GREEN | check | ไหว |
   | YELLOW | triangle | เสี่ยง: บางเดือนเกินงบ |
   | RED | octagon | ไม่ไหว: เกิน 1 ใน 3 ของรายได้ |
6. **Money is display only on the client.** The API sends strings ("1500.00");
   the client formats them ("1,500.00 บาท") by string operations and never adds,
   subtracts or rounds. Inputs are checked and sent as typed strings, never
   rounded (L49). Bar heights are computed exactly with BigInt satang and are
   drawing sizes only. Guarded by tests UI-01 to UI-06.
7. **Advice only:** no screen blocks recording or moving buffer money.
8. **No CDN, no Google Fonts, no external images.** System Thai fonts only.

## 4. Tokens (Tailwind v4 `@theme`, `src/index.css`)

Components use tokens only, never raw hex.

### Colour

| Token | Value | Use |
|---|---|---|
| `leaf-50` | `#eefbf3` | tinted backgrounds |
| `leaf-100` / `200` / `300` | `#d6f5e3` / `#aee9c8` / `#7fd8a7` | logo, disabled primary |
| `leaf-500` | `#22a565` | focus ring |
| `leaf-600` | `#138a52` | logo body, field focus |
| `leaf-700` | `#0d6e42` | **primary button**, active toggle |
| `leaf-800` / `900` | `#0b5735` / `#0a3f28` | links, pressed states |
| `sun-300` / `400` | `#ffd977` / `#ffc94d` | logo coin only, never text |
| `ink` | `#10231a` | text |
| `ink-muted` | `#4a5b52` | secondary text |
| `line` | `#dce5df` | borders, dividers |
| `surface` | `#f4f8f5` | screen background |
| `card` | `#ffffff` | cards |
| `desk` | `#e3ebe6` | page behind the phone frame |
| `ok-bg` / `ok-line` / `ok-ink` | `#e8f7ee` / `#9fdcb8` / `#0b5735` | GREEN, success |
| `warn-bg` / `warn-line` / `warn-ink` | `#fff6db` / `#f5c451` / `#6e4500` | YELLOW, budget warning |
| `risk-bg` / `risk-line` / `risk-ink` | `#fdecec` / `#f3a3a3` / `#9b1c1c` | RED, field errors |
| `info-bg` / `info-line` / `info-ink` | `#eaf3fb` / `#a9cbe9` / `#1d4e7a` | neutral notices, Demo tags |
| `bar-ok` / `bar-over` / `bar-risk` | `#138a52` / `#c27c00` / `#9b1c1c` | month bars |

Contrast (WCAG 2.2, measured): white on `leaf-700` 6.31; `ink` on card 16.44;
`ink-muted` on card 7.22 and on surface 6.73; `ok-ink`/`ok-bg` 7.81;
`warn-ink`/`warn-bg` 7.74; `risk-ink`/`risk-bg` 7.14; `info-ink`/`info-bg` 7.72.
Bars against the white card: `bar-ok` 4.39, `bar-over` 3.40, `bar-risk` 8.15
(non-text minimum 3:1).

### Typography

Font stack: `"Sukhumvit Set", "Noto Sans Thai", "Leelawadee UI", Tahoma, sans-serif`
(system fonts: macOS/iOS, Android/Linux, Windows; nothing is downloaded).

| Token | Size / line height | Use |
|---|---|---|
| `text-caption` | 14px / 1.4 | short labels only: footer, nav labels, chart legend, Demo tags, list meta |
| `text-body` | 16px / 1.6 | **every sentence**, help text, errors |
| `text-lead` | 18px / 1.5 | field values, section titles, large buttons |
| `text-title` | 22px / 1.35 | screen headings, verdict label |
| `text-display` | 32px / 1.2 | the one big number on a card |

Month labels under the bars are 12px because 10 to 12 of them share 358px. They
are `aria-hidden`; every month, total and status is also in a screen-reader table
and the over-budget months are listed in a 16px sentence.

### Spacing, radius, shadow

- Spacing: Tailwind's 4px scale. Screen gutter 16px (`px-4`), card padding 20px
  (`p-5`), gap between cards 16px (`gap-4`), between fields 20px (`gap-5`).
- Radius: `field` 12px, `card` 20px, `pill` 999px (buttons, chips).
- Shadow: `card` (soft, two layers), `phone` (the desktop frame only).
- Tap targets: at least 44px (`min-h-11`); buttons 48px (`min-h-12`), the main
  action 56px (`min-h-14`).

## 5. Components (`src/components/`)

### 5.1 Buttons (`ui.tsx` `Button`)
- `primary`: `leaf-700` with white text. One per screen.
- `secondary`: white with a 2px `leaf-700` border ("ยังไม่ซื้อ", retry).
- `ghost`: text only.
- `busy` disables the button and shows the "กำลัง..." label, so a double tap sends
  one request.
- Full width, pill shape, optional leading icon.

### 5.2 Cards (`Card`)
White, `rounded-card`, `shadow-card`, `p-5`. One topic per card.

### 5.3 Verdict card (`Verdict.tsx` `VerdictCard`)
Tinted box (`ok`, `warn` or `risk`) with a 48px round badge holding the icon, the
label at `text-title` (a long label breaks after the colon, never inside a Thai
word), the sentence, and "นี่เป็นคำแนะนำเท่านั้น คุณบันทึกรายการได้เสมอ".
`role="status"`, `aria-live="polite"`.

### 5.4 Month bars (`MonthBars`)
- One bar per month of the plan, drawn with divs (no chart library).
- Scale: the largest of the budget and the month totals. The budget is a dashed
  line.
- Colours: `bar-ok` in budget; `bar-over` and **striped** over budget;
  `bar-risk` and striped above one third of income. The flags come from the API
  (`over_budget`, `over_one_third`); the client never compares money to decide.
- Under the bars: the Thai month names, the budget-line note, a sentence listing
  the over-budget months ("เดือนที่เกินงบ: พ.ย. 2569, ธ.ค. 2569"), the legend,
  and a screen-reader table.

### 5.5 Inputs (`Field`, `Toggle`, `Checkbox`, saving mode radio)
- Visible label above, help text below (16px), error below with an icon and
  `role="alert"`.
- Money fields: `type="text"` with `inputMode="decimal"`, never a number input,
  so the browser cannot turn the value into a float. A "บาท" suffix.
- Placeholders start with "เช่น" so they never look like a value already filled in.
- Toggle: a 44x64 switch with `role="switch"`.
- Saving mode: two large radio cards (percent / fixed). Only the chosen mode's
  input is shown and sent (L63).

### 5.6 Alerts (`Alert`)
Tones `ok`, `warn`, `risk`, `info`, each with its own icon. Connection errors use
`info`, not `risk`: they are not the user's fault and their data is safe.

### 5.7 Shared states
`Loading` (pulsing card skeletons), `ErrorState` (info alert + "ลองอีกครั้ง"),
`SettingsMissing` (info alert + "ไปตั้งค่า").

### 5.8 Shell (`Screen.tsx`)
Header (logo, or back button + title), scrolling body, footer, bottom navigation
(หน้าหลัก, คิดก่อน, ตั้งค่า; กันชน and แจ้งเตือน join in PR B).

## 6. Layout and navigation

- On a desktop the app sits in a 390x844 phone frame centred on the `desk`
  background. Below 640px wide it fills the screen.
- Hash routes, no router package (`src/router.ts`): `#/settings`, `#/home`,
  `#/think` (PR B adds `#/buffer`, `#/alerts`, `#/payoff`, `#/consolidate`).
- With no route, a user without settings starts on screen 1; otherwise Home.

## 7. Screens and their states

Every screen has the footer and handles **loading** (skeleton), **error**
(retry), and **settings missing** (link to screen 1).

### 7.1 Screen 1: First-time settings (`#/settings`)
- Fields: รายได้ต่อเดือน, วันเงินเดือนออก (1 to 31), งบผ่อนต่อเดือน; "เปิดออมอัตโนมัติ"
  with the saving mode (percent 1 to 100 **or** a fixed amount, never both) and
  the 500 บาท safety-net note; "ออมส่วนที่เหลือจากงบ" on payday; consent
  (required when auto-save is on).
- First time: no back button, no bottom nav, intro heading. Later: the same form
  titled "ตั้งค่า", with nav.
- After saving: a success alert. If the response has
  `BUDGET_ABOVE_ONE_THIRD_OF_INCOME`, a warn alert explains the ธปท. guidance and
  says the settings are saved anyway (L64). Then "ไปหน้าหลัก".
- Errors per field: money format, more than 2 decimals (refused, not rounded),
  payday out of range, percent out of range, consent missing. A comma is accepted
  only as a thousands separator ("12,000"); "1,5" is refused, never read as 15.
- With auto-save off, the rule fields are hidden and not checked; an unfinished
  rule is sent as the default 10% (the API needs a rule; it is unused while off).
- States: loading (GET /settings), error, save failed (info alert, try again).

### 7.2 Screen 2: Home (`#/home`)
1. Greeting "สวัสดี มิ้นท์".
2. **This month card:** "ค่างวดรวมเดือน ต.ค. 2569", the total, "จากงบ ...", a
   progress bar, and "เดือนนี้ยังอยู่ในงบ" / "เดือนนี้ค่างวดรวมเกินงบที่ตั้งไว้" with an
   icon (from the API's `over_budget`).
3. **คิดก่อน**, the 56px primary button, with a one-line hint.
4. **Upcoming over-budget months** (the next 5), or "5 เดือนข้างหน้ายังไม่มีเดือนไหนเกินงบ".
5. **Buffer card:** balance and "พอจ่ายค่างวดได้ประมาณ N เดือน".
6. **Installments:** name, source (ShopDemo or บันทึกเอง), months, amount per month,
   remaining. Lines the API marks as not owed (paid off, cancelled) are listed
   under "ไม่นับในยอดต่อเดือน", so the rows above always add up to the total. A
   status chip says "ผ่อนครบแล้ว", "ยกเลิกแล้ว", "คุณแจ้งว่าไม่ใช่รายการของคุณ" or
   "ยกเลิกแล้ว หลังจากคุณแจ้งว่าไม่ใช่รายการของคุณ" (L59(3): the report is never lost).
   Empty: "ยังไม่มีรายการผ่อน ก่อนซื้อชิ้นต่อไป ลองกด คิดก่อน ดูนะ".
- States: loading, error, settings missing, empty list.

### 7.3 Screen 3: คิดก่อน (`#/think`)
1. Form: item name (optional), price, months, monthly amount, first due month
   (next month by default, a choice of four).
2. "ดูว่าไหวไหม" calls the preview (writes nothing).
3. Result: the verdict card, the month bars, "ตอนนี้ค่างวดรวมเดือนละ ...", then
   "ยังไม่ซื้อ" and "บันทึก" side by side. Both are always enabled (advice only).
4. Changing any field after a verdict clears it: a changed plan is a new plan.
5. **บันทึก** sends the same body with the same `client_request_id` as the
   preview, so a retry records once. Recorded: a check, "บันทึกรายการผ่อนแล้ว",
   the new monthly total, the amount saved to the buffer (or "ครั้งนี้ไม่ได้กันเงิน
   เข้ากันชน"), and the verdict again if it was not GREEN.
6. **ยังไม่ซื้อ**: "โอเค ยังไม่ซื้อ ไว้ค่อยคิดใหม่ได้เสมอ", nothing is written.
- Demo strip: three buttons fill มิ้นท์'s GREEN, YELLOW and RED examples.
- States: loading, error (try again), settings missing (also from a 409
  `SETTINGS_REQUIRED`).

### 7.4 to 7.7 and the Demo panel (PR B)
- **4. Buffer** (`#/buffer`): balance, months covered, "ย้ายกลับบัญชีหลัก" with an
  amount; 422 `AMOUNT_ABOVE_BALANCE` shown as a field error, never a block.
- **5. Notifications** (`#/alerts`): new debt, over-budget payday, leftover saved,
  in the backend's wording (`backend/app/notifications/copy.py`).
- **6. Payoff assistant** (mock): back-in-budget month, pause advice, headroom
  "ผ่อนเพิ่มได้ไม่เกินเดือนละ X ตั้งแต่ Y", buffer plan, an example AI explanation
  and a question box; "ขอรวมหนี้" only when eligible.
- **7. Consolidation request** (mock): steps to get payoff amounts per app,
  inputs, consent, and a result with BOTH the new monthly payment AND the total
  cost, labelled as an example estimate.
- **Demo panel:** clearly marked "Demo"; simulate payday for a month.

## 8. Thai copy

Source of truth: `frontend/src/copy.ts`. The key strings:

| Where | Thai |
|---|---|
| Footer | Concept prototype สำหรับการแข่งขัน |
| Primary button | คิดก่อน |
| GREEN | ไหว · ทุกเดือนค่างวดรวมยังอยู่ในงบที่คุณตั้งไว้ |
| YELLOW | เสี่ยง: บางเดือนเกินงบ · มีบางเดือนที่ค่างวดรวมเกินงบ ลองดูกราฟด้านล่างว่าเป็นเดือนไหน |
| RED | ไม่ไหว: เกิน 1 ใน 3 ของรายได้ · บางเดือนค่างวดรวมสูงกว่าที่ ธปท. แนะนำ คือค่างวดหนี้ทั้งหมดต่อเดือนไม่ควรเกิน 1 ใน 3 ของรายได้ |
| Advice note | นี่เป็นคำแนะนำเท่านั้น คุณบันทึกรายการได้เสมอ |
| Budget warning (L64) | งบนี้เกิน 1 ใน 3 ของรายได้ ธปท. แนะนำว่าค่างวดหนี้ทั้งหมดต่อเดือนไม่ควรเกิน 1 ใน 3 ของรายได้ บันทึกไว้แล้ว ปรับได้ทุกเมื่อ |
| Safety net | ถ้าเงินในบัญชีหลักจะเหลือน้อยกว่า 500 บาท ระบบจะข้ามการออมครั้งนั้นทั้งก้อน |
| Consent | ฉันยินยอมให้ KidNee ย้ายเงินจากบัญชีหลักเข้ากันชนตามกติกาด้านบน |
| Record | บันทึก / ยังไม่ซื้อ |
| Recorded | บันทึกรายการผ่อนแล้ว · กันเงินเข้ากันชนให้แล้ว |
| Not buying | โอเค ยังไม่ซื้อ ไว้ค่อยคิดใหม่ได้เสมอ |
| Connection error | เชื่อมต่อไม่สำเร็จ ข้อมูลของคุณยังอยู่ครบ ลองอีกครั้งได้เลย |
| Settings missing | บอกรายได้และงบผ่อนต่อเดือนก่อน KidNee ถึงจะช่วยคิดให้ได้ |
| Money errors | กรอกจำนวนเงินด้วยนะ · ทศนิยมได้ไม่เกิน 2 ตำแหน่ง · จำนวนเงินต้องมากกว่า 0 |

Months are Thai short names with the Buddhist-era year ("พ.ย. 2569"), as the
backend writes them.

## 9. API types per screen

All in `frontend/src/api-types.ts`, copied from the merged backend. Money is a
string. `src/api.ts` is the only module that gets data (test UI-07); it sends
`X-Demo-User: demo-mint` (L60, demo only) and calls `/api/...`, which the Vite
proxy forwards to `http://127.0.0.1:8000` with `/api` stripped (the backend has no
prefix; to be confirmed when wiring).

| Screen | Call | Request | Response | Errors |
|---|---|---|---|---|
| 1 | `GET /settings` | | `SettingsOut` | 404 = none yet |
| 1 | `POST /settings` / `PUT /settings` | `SettingsIn` (`saving_rule` is `{mode:"percent",percent}` or `{mode:"fixed",amount}`) | `SettingsOut` with `warnings` | 409 exists (POST), 404 none (PUT), 422 |
| 2 | `GET /debts/summary` | | `DebtSummary` (`installments: InstallmentLine[]`) | |
| 2 | `GET /debts/months` **TODO, mock only** | `?count=6` | `{ months: MonthRow[] }` from this month, no candidate | 409 `SETTINGS_REQUIRED` |
| 2, 4 | `GET /buffer` | | `BufferOut` (`months_covered` null when nothing is owed) | |
| 3 | `POST /installments/preview` | `ManualEntryIn` | `VerdictOut` | 409 `SETTINGS_REQUIRED`, 422 |
| 3 | `POST /installments` | `ManualEntryIn` (same `client_request_id`) | `RecordedOut` (`saved_amount`, `monthly_total`, `warnings: VerdictOut`); 201 new, 200 repeat | 409 reused id with other fields, 409 `SETTINGS_REQUIRED` |
| 4 | `POST /buffer/move-to-main` | `MoveIn` | `MovedOut`; 201, 200 repeat | 409, 422 `AMOUNT_ABOVE_BALANCE` |
| Demo | `POST /demo/payday` | `{ month: "YYYY-MM" }` | `PaydayOut` | 404 when demo endpoints are off |
| 5 | `GET /notifications` **TODO** | | shape in PR B | |
| 6, 7 | payoff, consolidation **TODO** | | shapes in PR B | |

Error bodies: `{"detail": {"code", "message"}}` for coded errors, a plain string
`detail` for older ones, and FastAPI's list for 422. `ApiError` exposes `status`
and `code`.

## 10. Demo persona and scenes

**มิ้นท์**, 24, first job. Income 20,000.00, payday the 25th, installment budget
5,000.00, auto-save 10% of the price, leftover saving on, consent given. Main
account 9,500.00, buffer 4,800.00.

Existing installments (months relative to the demo month; on 27 Oct 2026):
- หูฟังไร้สาย, ShopDemo: 2,000.00 a month, last month ธ.ค. 2569 (ends soon).
- ตู้เย็น, recorded by hand: 1,500.00 a month, last month มิ.ย. 2570.
- กระเป๋าเป้, ShopDemo: paid off (listed under "ไม่นับในยอดต่อเดือน").
Now: 3,500.00 a month.

| Example | Price | Plan | Busiest month | Verdict |
|---|---|---|---|---|
| โทรศัพท์ | 12,000.00 | 10 x 1,200.00 | 4,700.00 (in budget) | GREEN ไหว |
| โน้ตบุ๊ก | 30,000.00 | 10 x 3,000.00 | 6,500.00 (over budget, under one third: 19,500 <= 20,000) | YELLOW เสี่ยง |
| มอเตอร์ไซค์ | 48,000.00 | 12 x 4,000.00 | 7,500.00 (7,500 x 3 = 22,500 > 20,000) | RED ไม่ไหว |

### Scenes, in order
1. **Settings** (`/#/settings`): empty first-time form. Tap "Demo: กรอกข้อมูลตัวอย่างของ
   มิ้นท์", save. Optionally change the budget to 7,000 to show the one-third
   warning (7,000 x 3 > 20,000), then back to 5,000.
2. **Home**: 3,500.00 of 5,000.00, no over-budget month ahead, buffer 4,800.00
   (about 1 month), two installments. Tap **คิดก่อน**.
3. **คิดก่อน, YELLOW**: tap "เสี่ยง". Nov and Dec are striped and listed. Point
   out "บันทึกได้เสมอ". Tap "ยังไม่ซื้อ".
4. **คิดก่อน, RED**: tap "ไม่ไหว". The ธปท. guidance sentence.
5. **คิดก่อน, GREEN**: tap "ไหว", then **บันทึก**: 1,200.00 saved to the buffer,
   new total 4,700.00.
6. **Home** again: the installments now total 4,700.00 a month (from next month), buffer 6,000.00.
7. (PR B) Buffer, payday over budget, notifications, payoff assistant,
   consolidation.

Shortcuts for slides: `http://127.0.0.1:5173/?persona#/home` starts with the
settings saved; `?persona&scene=YELLOW#/think` opens with that example checked.
Reloading the page resets the mock.

## 11. How to run

Node 22.12 or later (Vite 8). From `frontend/`:

```bash
npm ci              # exact versions from package-lock.json
npm run dev         # http://127.0.0.1:5173 (loopback only, never 0.0.0.0)
npm test            # UI-01 to UI-12 (compiled with tsc, run with node --test)
npm run typecheck   # tsc --noEmit, strict
npm run build       # typecheck + production build to dist/
npm audit
```

To use the real backend: run it on `127.0.0.1:8000` with
`DEMO_ENDPOINTS_ENABLED=true` for payday, then set `USE_MOCK = false` in
`src/api.ts`.

Dependencies (exact pins, nothing else without asking): react 19.3.0, react-dom
19.3.0, vite 8.3.4, @vitejs/plugin-react 6.1.2, typescript 7.0.2, tailwindcss
4.3.3, @tailwindcss/vite 4.3.3, @types/react 19.3.0, @types/react-dom 19.3.0.

## 12. ui-ux-pro-max: what was used and what was overridden

Run locally (`search.py --design-system`, `--domain color`, `--domain ux`), no
`--persist`, no network, no package installs.

Used:
- The rule priorities and the pre-delivery checklist: 4.5:1 text contrast, 44px
  targets, visible focus, reduced motion, SVG icons and no emoji, visible labels,
  errors next to the field, `inputmode` for number keyboards, thousands separators.
- "Minimalism" direction: white space, one primary action per screen, clear
  type hierarchy.
- Three-layer token idea (primitive `leaf-700`, semantic `ok-ink`, component bar
  colours).

Overridden (our rules win):
- Its palette (gold and purple on dark) and "personal finance" palette (blue on
  dark): replaced by the green family, light mode only, for a calm and
  trustworthy feel.
- Its font pairing (IBM Plex Sans via Google Fonts): replaced by the system Thai
  font stack; no Google Fonts, no CDN.
- "Use `type=number`" for numbers: replaced by `type="text"` +
  `inputMode="decimal"`, so money is never parsed as a float.
- "Trust and authority" landing pattern, logo carousels, case studies: not for an
  in-app feature.
- shadcn/ui, Chart.js, GSAP, Heroicons/Lucide packages: not added (minimal
  dependencies). Icons are a handful of inline SVG paths; bars are divs.
- Its "responsive 375 to 1440" check: the prototype targets the phone frame only.
