# KidNee (คิดหนี้): design system and screens

Concept prototype for a 2026 hackathon (Track 1). This file is the design
source of truth for `frontend/`. Copy lives in `frontend/src/copy.ts`, tokens in
`frontend/src/index.css`, and API types in `frontend/src/api-types.ts`; this file
explains them and must stay in step with them.

Status (2026-10-29): every screen is built and calls the real API (Session 17):
`npm run dev` and the build call `/api/...`; `npm run dev -- --mode mock` answers
from `src/mock/` instead, for the scenes (section 10). Session 15-UI
reworked Home's visual hierarchy: one card type per job, cards that shrink when
there is nothing to act on, and one accent colour per feature (sections 4, 5.9
and 7.2).

**Structure (user decision, 2026-10-27, final): two features and one card.**
- **Feature 1, ภาพรวมหนี้:** Home, recording, เช็กก่อนผ่อน, ภาระผ่อนรายเดือน.
- **Feature 2, กันชน:** saving on each installment, leftover saving on payday, and
  using the buffer when a month is over budget.
- **The consolidation card** on Home: a one-line banner when it is not needed, the
  bank's offer when it is.
There is no payoff assistant screen and no consolidation request flow (both
were removed in part 4). Their parts moved: the plan's months and safe amount go to
ภาระผ่อนรายเดือน and the form, the buffer plan goes to the buffer screen, and the
consolidation estimate goes to the Home card. The AI summary is also a Home card.

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
2. **เช็กก่อนผ่อน**: before buying, the user enters the price and the plan, and
   sees every month of that plan with the new total, and a verdict: อยู่ในงบ,
   บางเดือนเกินงบ or เกินเกณฑ์ที่ ธปท. แนะนำ.
3. Saves a little into a **buffer** each time an installment is recorded, so a
   heavy month can be covered.
4. Alerts on every new debt and on payday when a month is over budget.
5. Says when the months are back in budget, how much more fits, and whether
   consolidating is worth asking the bank about (`GET /assistant/plan`; every
   number comes from code, never from AI: L69, L70).

**Principle: advice only, never a block.** KidNee never stops a purchase and never
holds the user's money. Recording is always allowed, whatever the verdict.

## 2. Name, tone and logo

- **Name:** KidNee, with the Thai คิดหนี้ ("think about debt") next to it.
  CLAUDE.md rule 5 still says the display name is "Lumen"; the backend session
  updates that rule on 2026-10-28. Lumen stays the name of the backend system.
- **Primary action:** "เช็กก่อนผ่อน" (check before paying in installments). It
  is the largest button on Home and the raised centre tab of the bottom nav. Its
  form button is "ประเมินภาระผ่อน".
- **Tone:** formal but easy, like a friendly older sibling who is good with money. Short sentences,
  "เรา/คุณ", no scolding, no fear. Say what is true and what the user can do next.
  - Yes: "มีบางเดือนที่ค่างวดรวมเกินงบ ลองดูกราฟด้านล่างว่าเป็นเดือนไหน"
  - No: "คุณกำลังก่อหนี้เกินตัว" (judges the person)
  - Yes: "โอเค ยังไม่ซื้อ ไว้ค่อยคิดใหม่ได้เสมอ"
- **Logo:** abstract and friendly, never a realistic kidney or any organ. Two
  options, both inline SVG in `src/components/Logo.tsx`:

**Option A, "Bean" (used in the app: the header, the assistant's card, the
favicon).** A soft green bean with a small smile: "think it through, calmly".
Neither option has a yellow badge: a small yellow circle on the edge read like a
warning sign (UI-44).

```svg
<svg viewBox="0 0 48 48" width="48" height="48">
  <path d="M14 8c6-4 15-3 20 2 4 4 3 9 0 12-2 2-2 4 0 6 4 4 4 11-2 15-6 4-16 4-22-2C4 35 4 25 6 19c1.5-5 4-9 8-11Z" fill="#138a52"/>
  <path d="M16 13c3-2 7-2 10 0" stroke="#aee9c8" stroke-width="3" stroke-linecap="round" fill="none"/>
  <circle cx="17" cy="25" r="2" fill="#ffffff"/><circle cx="26" cy="25" r="2" fill="#ffffff"/>
  <path d="M17 31c2.5 2.5 6.5 2.5 9 0" stroke="#ffffff" stroke-width="2.5" stroke-linecap="round" fill="none"/>
</svg>
```

**Option B, "Filter".** Three rounded layers narrowing to one dark green coin:
"only what fits passes through".

```svg
<svg viewBox="0 0 48 48" width="48" height="48">
  <rect x="6" y="7" width="36" height="8" rx="4" fill="#7fd8a7"/>
  <rect x="11" y="18" width="26" height="8" rx="4" fill="#22a565"/>
  <rect x="16" y="29" width="16" height="8" rx="4" fill="#0d6e42"/>
  <circle cx="24" cy="43" r="4" fill="#0a3f28"/>
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
   | GREEN | check | อยู่ในงบ |
   | YELLOW | triangle | บางเดือนเกินงบ |
   | RED | octagon | เกินเกณฑ์ที่ ธปท. แนะนำ (1 ใน 3 ของรายได้) |

   The RED label breaks before the brackets, never inside them.
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
| `leaf-800` / `900` | `#0b5735` / `#0a3f28` | links, pressed states; `900` is also logo B's coin |
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
| `teal-50` / `100` / `200` / `700` / `800` | `#e8f7f7` / `#c4ebec` / `#94d9dc` / `#0c6a72` / `#0a535a` | the buffer (feature 2) |
| `teal-edge` | `#358b92` | the wallet's edge (Home and the buffer screen), where it meets the page |
| `bank-50` / `200` / `700` / `800` | `#eef3fd` / `#b3c9f2` / `#2a4fa0` / `#1f3d7d` | the bank's consolidation offer |
| `ai-from` / `ai-to` / `ai-line` / `ai-ink` / `ai-edge` | `#f3effe` / `#e8f4fd` / `#d6ccf6` / `#4b3699` / `#8a76d6` | the assistant only (soft gradient; `ai-edge` is the panel's edge) |
| `quiet-bg` / `quiet-line` / `quiet-ink` / `quiet-edge` | `#eef2f6` / `#d3dce6` / `#3f5166` / `#7a8a9d` | a note with nothing to act on (`quiet-edge` is the banner's edge) |

Contrast (WCAG 2.2, measured): white on `leaf-700` 6.31; `ink` on card 16.44;
`ink-muted` on card 7.22 and on surface 6.73; `ok-ink`/`ok-bg` 7.81;
`warn-ink`/`warn-bg` 7.74; `risk-ink`/`risk-bg` 7.14; `info-ink`/`info-bg` 7.72.
Bars against the white card: `bar-ok` 4.39, `bar-over` 3.40, `bar-risk` 8.15
(non-text minimum 3:1); the ⚠ above a bar, `risk-ink` on card, 8.15; the new
item's white share against the rest of its bar and its outline against the card,
the same three pairs (4.39, 3.40, 8.15); the legend's grey part swatches,
`ink-muted` on card, 7.22.
Accents: `teal-800` on `teal-50` 7.96, on card 8.76; white on `teal-700` 6.32;
`bank-800` on `bank-50` 9.33; `ai-ink` on `ai-from` 8.13 and on `ai-to` 8.22;
`quiet-ink` on `quiet-bg` 7.23; `warn-ink` on card 8.35. The hero while hovered
(`leaf-50`): `ink` 15.44, `ink-muted` 6.78, `leaf-800` 8.12, `warn-ink` 7.85,
`teal-800` 8.23. Non-text: `teal-700` on `teal-50` 5.75, on `teal-200` 3.98 (the
meter's filled and empty segments); `bank-700` on `bank-50` 6.93; the hero bar on
its `leaf-50` track, `bar-ok` 4.12 and `bar-over` 3.19, and its budget mark, `ink`,
15.44 on the track, 3.75 on `bar-ok` and 4.84 on `bar-over`. The offer's title,
white on `bank-700`, 7.71; its tag, `bank-800` on white, 10.39.
Card edges against the page (surface / card), at least 3:1 (1.4.11): `bank-700`
7.19 / 7.71, `ai-edge` 3.47 / 3.72, `quiet-edge` 3.29 / 3.53, `teal-edge` 3.73 /
3.99. The light lines they replace blend in: `bank-200`
1.56, `ai-line` 1.42, `quiet-line` 1.29, `warn-line` 1.52, `teal-100` 1.19 on surface. Test UI-35 recomputes these pairs
from `index.css`, the edges from `EDGE` in `accent.ts`.

### Feature accents (`src/accent.ts`)

One colour per feature, and never colour only: each accent comes with its icon
and its text. The teal, bank, ai and quiet classes appear in `accent.ts` only
(UI-34 scans `src/`), and the coloured lines on Home are `Marked` values (accent,
icon, text). A tinted card that meets the page takes its `EDGE`, so its light tint
never blends into the page: the bank's offer (`bank-700`, 2px), the assistant's panel (`ai-edge`), the consolidation
banner (`quiet-edge`), and the buffer's wallet on Home and the buffer screen's
balance card (`teal-edge`, 2px). UI-35 measures each edge, and checks Home's markup
in four scenes and the buffer screen's card for a tinted card without its edge.
Alerts (5.6) keep their light lines: they are messages, carried by their icon and
words, not cards.

| Accent | Tokens | Icon | Text | Used for |
|---|---|---|---|---|
| `debt` green | `leaf-*` | home, check | ภาพรวมหนี้ | debt overview, main actions, in-budget lines |
| `buffer` teal | `teal-*` | shield | กันชน | the wallet, the buffer screen's header and balance card, its nav tab, the hero's buffer line and "ใช้กันชนจ่ายส่วนที่เกิน", a prepared month's check |
| `warn` amber | `warn-*` | triangle | เกินงบ | a month over budget: the hero's warning line and the part of its bar above the budget |
| `bank` blue | `bank-*` | bank columns | ทางเลือกจากธนาคาร | the consolidation offer only |
| `ai` soft tint | `ai-*` | chat bubble with a sparkle | ผู้ช่วย KidNee | the assistant only, never a solid colour |
| `quiet` grey-blue | `quiet-*` | info | ข้อมูลเพิ่มเติม | the consolidation banner |

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

Month labels under the bars are `text-caption` (14px). Up to 7 months each has one;
beyond that every k-th month (k = months / 7, rounded up), so label centres are at
least 42px apart in the 298px plot of the 370px frame, and the widest label is 29px
in Noto Sans Thai (34px allowed for other system fonts; UI-40). They are
`aria-hidden`: every month, total and status is also in a screen-reader table, and a
16px sentence says how many months are over budget and from when to when.

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
- `bank`: the secondary outline in the bank's blue ("สนใจรวมหนี้"), from `OUTLINE`
  in `accent.ts`.
- `buffer`: filled teal (`FILL.buffer`), the month's move "ใช้กันชนจ่ายส่วนที่เกิน"
  on Home's hero and the buffer screen. `bufferOutline`: the same in a teal outline
  (`OUTLINE.buffer`), on each month of ภาระผ่อนรายเดือน, where it is not the
  screen's main action.
- `busy` disables the button and shows the "กำลัง..." label. A money move is also
  guarded outside React (`mover`), since two taps can land before the re-render
  that disables it.
- Full width, pill shape, optional leading icon.

### 5.2 Cards (`Card`)
White, `rounded-card`, `shadow-card`, `p-5`. One topic per card.

### 5.3 Verdict card (`Verdict.tsx` `VerdictCard`)
Tinted box (`ok`, `warn` or `risk`) with a 48px round badge holding the icon, the
label at `text-title` (a long label breaks after the colon, never inside a Thai
word), the sentence, and "นี่เป็นคำแนะนำเท่านั้น คุณบันทึกรายการได้เสมอ".
`role="status"`, `aria-live="polite"`.

### 5.4 Month bars (`MonthBars`)
- One bar per month of the plan, drawn with divs (no chart library), on one CSS
  grid of equal columns (`repeat(n, minmax(0, 1fr))`): the bars, the month labels
  and the dashed budget line share it, so each label sits under its own bar at any
  number of months and nothing overflows the card (UI-40).
- Scale: the largest of the budget and the month totals.
- Colours, solid (no hatch): `bar-ok` in budget, `bar-over` over budget, `bar-risk`
  above one third of income, with a small ⚠ above that bar (`risk-ink`, at most
  16px and never wider than its bar, so a run of such months never overlaps). The
  flags come from the API (`over_budget`, `over_one_third`); the client never
  compares money to decide.
- The new item's share is the top of each bar and looks the same on every bar,
  whatever its status: a white fill (`bg-card`) with a closed 2px outline in that
  bar's colour, its height the item's monthly amount as a share of that month's
  total (`barPermille`, a drawing size). The outline is closed so that a month with
  nothing else due, where the share is the whole bar, is still a box on its base.
- Legend: only what this chart shows, each entry one 12px square. First the
  statuses its months have, in a fixed order (in budget, over budget, over one
  third with the ⚠); a status no month has is left out. Then, with an item, the
  two parts of a bar in neutral swatches, since both take each month's colour on
  the bars: "ค่างวดที่มีอยู่" (a solid `ink-muted` square; only when some month's
  total is more than the item's amount, so its bar has a solid part) and
  "ค่างวดชิ้นใหม่" (a white square with a 2px `ink-muted` outline).
- Labels: `text-caption`, plain (never bold or amber), on one line, centred under
  their own bar; every month up to 7, beyond that every k-th (Typography).
- Under the bars: the budget-line note, one plain sentence (`text-body`, ink, no
  icon) "เกินงบ {n} เดือน: {first} ถึง {last}", counted from the API's rows
  (`overRange`; "ในช่วง" when they are not one run, "เกินงบ 1 เดือน: {month}" for
  one; a month is never split from its year at a line break), the legend, and a
  screen-reader table. The verdict card above holds the warning; nothing else
  repeats it (UI-41).

### 5.5 Inputs (`Field`, `Toggle`, `Checkbox`, saving mode radio)
- Visible label above, help text below (16px), error below with an icon and
  `role="alert"`.
- Money fields: `type="text"` with `inputMode="decimal"`, never a number input,
  so the browser cannot turn the value into a float. A "บาท" suffix. A comma is
  accepted only as a thousands separator in groups of three ("12,000",
  "12,000.50"); "1,5" is refused, never read as 15. Counts (months):
  `inputMode="numeric"`.
- Placeholders start with "เช่น" so they never look like a value already filled in,
  and show a form the field takes ("เช่น 12,000").
- A field shows its error once the user leaves it with something typed. An empty
  field is only not done yet, which the form's check says (7.3).
- Toggle: a 44x64 switch with `role="switch"`.
- Saving mode: two large radio cards (percent / fixed). Only the chosen mode's
  input is shown and sent (L63).

### 5.6 Alerts (`Alert`)
Tones `ok`, `warn`, `risk`, `info` and `buffer` (teal, the buffer plan when it
covers), each with its own icon. Connection errors use
`info`, not `risk`: they are not the user's fault and their data is safe.

### 5.7 Shared states
`Loading` (pulsing card skeletons), `ErrorState` (info alert + "ลองอีกครั้ง"),
`SettingsMissing` (info alert + "ไปตั้งค่า").

### 5.8 Shell (`Screen.tsx`)
- **Header:** logo, or back button + title. On the right, in this order: the
  dashed "Demo" button (opens the Demo panel; shown only while the demo endpoints
  answer, 7.8), the notifications bell with no badge (the API keeps no read state),
  and settings as a gear icon. A screen can take
  its feature's accent (`Screen`'s `accent` prop): the buffer screen's header is
  tinted teal with the shield before the title.
- **Body:** scrolls; inside the phone frame its scrollbar is hidden
  (`.phone-scroll`: `scrollbar-width: none` and `::-webkit-scrollbar`), while
  wheel, touchpad, touch and keyboard scrolling still work (the body takes focus,
  with a visible focus ring). Nothing outside the frame hides a scrollbar (UI-22).
- **Action bar** (optional): fixed under the body, above the nav: the result
  screen's บันทึก / ยังไม่ซื้อ (no nav there), and the form's ประเมินภาระผ่อน (with the
  nav). With the nav under it, the bar's bottom padding is the centre button's raise
  plus at least 12px (`ACTIONS_PAD_WITH_NAV`, `pb-8`, UI-27): its button keeps 16px
  clear of the raised button, measured at 390px and in the 370px desktop frame.
- **Bottom nav: three tabs**, one line each at 390px: หน้าหลัก (feature 1),
  **เช็กก่อนผ่อน** (centre, a raised 56px round button), กันชน (feature 2). The list and
  which tab is selected live in `navStyle.ts` (`NAV_TABS`, `navActive`, UI-30):
  หน้าหลัก stays selected on ภาระผ่อนรายเดือน, เช็กก่อนผ่อน on the result. The centre
  tab uses the full name: at 14px it is 74px wide, one line in a 130px tab at 390px
  (and in 120px at 360px), so the short "เช็ก" is not needed (UI-25). Always "เช็ก"
  ending in ก (ก ไก่), never in ค (ค ควาย). Every button and nav label that checks
  uses "เช็ก" (เช็กก่อนผ่อน, เช็กรายการอื่น), never "ตรวจสอบ" (UI-32). The preview button stays "ประเมินภาระผ่อน". Settings and notifications are not
  tabs.
  - **Selected is the same shape for every tab:** a filled icon background and a
    bold label (`navStyle.ts`, UI-25), green for หน้าหลัก and เช็กก่อนผ่อน, teal for
    กันชน, whose icon stays teal when not selected. The centre button is larger
    but, when not selected, only a green outline on white, never filled.
- **Pinned bars:** header, action bar and nav never shrink; only `<main>` scrolls.
  While the nav shows, `<main>` has bottom padding of the centre button's raise
  plus at least 24px (`pb-14`; `SCROLL_PAD_WITH_NAV` in `navStyle.ts`, UI-27), so
  the last item is never hidden behind it; with an action bar, `pb-6`, since the
  bar takes the raise (`bottomPads`).
  The frame uses `overflow: clip`, which nothing can scroll, and every visually
  hidden input sits in a `relative` label (UI-26). Without that, focusing a hidden
  radio scrolled the frame itself and lifted the nav into the middle of the screen.
- **Layers (UI-27):** the body, the action bar and the nav are each their own layer
  (`isolate`), drawn in that order, so the nav, raised centre button included, is
  always on top of what scrolls under it. Nothing in the body can rise over it,
  whatever lifts it (`position`, `opacity`, a transform or a z-index): it stays inside
  the body's layer. No z-index number does this. The only one in `src` is the Demo
  panel's `z-30`, the overlay over the whole frame, nav included (a guard checks it).
  Without the layers, CSS drew each positioned or semi-transparent box after every
  plain one, so the assistant's bubble (`relative` for its tail), the uncounted
  installments (`opacity-80`), the offer's two boxes, the month bars and the saving
  mode choice covered the raised button as they scrolled under it. Checked in Chrome
  on every screen and scene, at 390px and in the 370px desktop frame, by
  `scripts/nav-layer-check.mjs` (run by hand, section 11).

### 5.9 Card types (Home, `homeLayout.ts`)
Each job has its own shape, and size follows importance. A card with nothing to
act on shrinks to one line or is left out. The rules are pure functions of the API
data (UI-33); they format, never add up.

| Card | Shape | Shrinks or goes when |
|---|---|---|
| Hero, this month | one white card, the only one with a `text-display` number, and no box inside it: a chevron › at the top right (the whole card opens 7.2b), the bar with the budget marked, one status or warning line, one buffer line with its text link | nothing over budget: one status line, no warning, no buffer line |
| เช็กก่อนผ่อน | the 56px green pill and its hint | never |
| Wallet | one wide teal button framed in `teal-edge` (2px): shield badge, "กันชนของคุณ ›", the balance at `text-title`; on the right 6 segments and "พอ {n} เดือน" | never; the meter is empty at 0 months |
| Assistant bubble | a soft gradient panel with an `ai-edge` border; the mascot speaks from the left into a white bubble with a tail | loading: "กำลังสรุป..." at a fixed height, no spinner; error: one line and "ลองอีกครั้ง"; no plan: left out |
| Consolidation banner | one slim grey-blue line, 44px, with a `quiet-edge` border, "ⓘ ... ›"; tap to show the reason | it is the offer's shrunk form |
| Bank offer | a white card framed in `bank-700` (2px) with a solid blue header band: the bank icon, the white title, the "ตัวอย่างการประมาณ" tag. On the white body (`p-4`): two light-blue boxes "ตอนนี้" and "ถ้ารวมหนี้ (ตัวอย่าง)", every amount at `text-lead` bold, the arrow on the gap between them (not a column of its own, so each amount keeps its "บาท" on one line in the 370px frame); one benefit line (left out when the answer has no `monthly_reduction`); the example rate | shown only when the plan says eligible (L70) |
| Installments | flat (border, no shadow), last | empty: one sentence |

## 6. Layout and navigation

- On a desktop the app sits in a 390x844 phone frame centred on the `desk`
  background. Below 640px wide it fills the screen.
- Hash routes, no router package (`src/router.ts`): `#/settings`, `#/home`,
  `#/months`, `#/think`, `#/result` (PR B adds `#/buffer` and `#/alerts`). There is
  no `#/payoff` or `#/consolidate` (UI-30).
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
The card types are in 5.9; `homeView` in `homeLayout.ts` picks each card's state.
1. Greeting "สวัสดี ม่อน".
2. **Hero, this month** (`GET /debts/months`, every month from this one to the last
   one due), one card (UI-42): "ค่างวดรวมเดือน ต.ค. 2569" with a chevron › at the top
   right (read aloud "ดูทุกเดือน"; the whole card opens 7.2b), the total, "จากงบ ...",
   and the bar on the larger of the budget and the total: green up to the budget,
   amber only above it, never all amber, with an ink mark where the budget is. Then:
   - every month in budget: "✓ เดือนนี้และอีก {n} เดือนอยู่ในงบ", {n} being the rows
     after this month ("เดือนนี้ยังอยู่ในงบ" when there are none);
   - a later month over: "✓ เดือนนี้ยังอยู่ในงบ", then the warning;
   - this month over: the warning alone, which covers this month too.
   The warning is one line, "⚠ เกินงบ {n} เดือน ({first} ถึง {last})", counted from
   the rows (UI-41; "ในช่วง" when they are not one run, "เกินงบ 1 เดือน ({month})" for
   one). Then one buffer line for the first month over budget, from
   `GET /buffer/shortfalls` (UI-46), as the API's `state` says: "{month} เกินงบ
   {shortfall}" (amber triangle, not prepared), "{month} เกินงบ {shortfall}
   เตรียมจากกันชนแล้ว {prepared} ยังขาด {gap}" (amber, partly prepared), or
   "{month} เกินงบ {shortfall} เตรียมเงินจากกันชนแล้ว" (teal check, prepared). While
   the buffer can pay some of the gap, the filled teal button "ใช้กันชนจ่ายส่วนที่เกิน"
   opens the buffer screen at that month. The line stays on the first month over, so
   after a move it shows that month prepared. No month over, or no answer, gives no
   buffer line. No month chips, no
   amount over budget and no total over all months: 7.2b has them month by month.
   There is no separate upcoming-months card.
3. **เช็กก่อนผ่อน**, the 56px primary button, with a one-line hint.
4. **Wallet** (`GET /buffer`, framed in `teal-edge`): the balance, and segments filled up to the API's
   `months_covered` (at most 6) with "พอ {n} เดือน", "ยังไม่พอ 1 เดือน" at 0, or
   "ไม่มีค่างวด" when nothing is owed. Tap: the buffer screen.
5. **Assistant bubble** (`AssistantCards.tsx`, `POST /assistant/summary`, loaded
   when Home opens): "ผู้ช่วย KidNee", the summary's first line, the rest behind
   "อ่านต่อ ›" / "ย่อ", tagged "ตัวอย่าง" while the text is an example. Mock text now;
   it only puts words around the plan's numbers.
6. **Consolidation** (the plan's `consolidation`, L70):
   - not eligible: the banner "ตอนนี้ยังไม่จำเป็นต้องรวมหนี้" for `NOT_NEEDED`, else
     "ตอนนี้ยังไม่คุ้มที่จะรวมหนี้"; it opens to the reason in plain words
     (`ASSIST.reason`);
   - eligible: "ทางเลือกจากธนาคาร" in the blue band, tagged "ตัวอย่างการประมาณ".
     "ตอนนี้" shows `monthly_total` and `current_remaining_total`; "ถ้ารวมหนี้
     (ตัวอย่าง)" shows `monthly_payment` and `total_cost`. Each total is as large and
     as bold as its monthly amount (UI-38), so a lower payment that costs more in
     total is plain to see without a line of its own. Then one benefit line at body
     size, "ค่างวดลดลงเดือนละ {monthly_reduction} ทุกเดือนกลับมาอยู่ในงบ", from the API
     (never worked out on screen) and left out unless it is above 0.00, and when
     the answer has no readable `monthly_reduction` (UI-39: the card shows whole
     without it, and the console says why);
     "ทุกเดือนกลับมาอยู่ในงบ" holds for every offer, since the plan offers only a loan
     that brings every month back within budget (L70 b). Then the term and the example rate
     "(ไม่ใช่อัตราจริง)". A phrase that does not fit moves to the next line whole
     (`KeepLastPhrase`), never split inside it. "สนใจรวมหนี้" only shows
     "ธนาคารจะติดต่อกลับเพื่อพิจารณา" with "ตัวเลขนี้ยังไม่ใช่ข้อเสนอ": no form and no
     request (UI-31, L71).
7. **Installments**, grouped by the app the user named (apps in the order they
   first appear, then "ไม่ระบุแอป"): name, "งวดที่ {x} จาก {y} · หมด {last month}",
   amount per month, remaining (UI-43). The line comes from `GET /debts/months`:
   the number in this
   month's row and the month marked `is_last`; "เริ่ม {first} · หมด {last}" for one that starts later, never
   "งวดที่ 1" as if due now; "ผ่อน {months} เดือน" when no row lists it. Each part
   stays whole, so a line breaks only at the dot. Paid-off lines fold into one line,
   "ผ่อนครบแล้ว {n} รายการ ›", that opens to their names, each with a check. Other
   lines the API marks as not owed (cancelled) stay under "ไม่นับในยอดต่อเดือน" with
   their chip, "ยกเลิกแล้ว" or "ยกเลิกแล้ว หลังจากคุณแจ้งว่าไม่ใช่รายการของคุณ" (L59(3):
   the report is never lost), never as paid off. So the rows above always add up
   to the total. A disputed line still owed keeps "คุณแจ้งว่าไม่ใช่รายการของคุณ".
   Empty: "ยังไม่มีรายการผ่อน ก่อนผ่อนชิ้นต่อไป กด เช็กก่อนผ่อน ได้เลย".
- States: loading, error, settings missing, empty list. If the plan fails to load,
  Home still shows and cards 5 and 6 are left out; if the shortfalls fail, the hero
  has no buffer line.
- At 390x844 the last card ends at least 90px, and the footer at least 40px, above
  the raised centre button.

### 7.2b ภาระผ่อนรายเดือน (`#/months`)
- Every month from this month to the last month with an installment, from
  `GET /debts/months`.
- Each month over budget also shows its buffer state line (as the hero's, from
  `GET /buffer/shortfalls`) and, while the buffer can pay some of the gap, an
  outlined teal "ใช้กันชนจ่ายส่วนที่เกิน" that opens the buffer screen at that month
  (UI-48). The screen still shows the months when that answer fails.
- At the bottom, one quiet caption (`text-caption`, muted, never a warning box,
  UI-48): "ยอดในแอปผ่อนไม่ตรงกับที่นี่? อาจมีรายการที่คุณไม่ได้ทำ
  ติดต่อแอปผ่อนโดยตรงจากช่องทางในแอป อย่าโอนเงินให้ใครที่โทรมาทวง".
- Per month: "3,500.00 บาท จากงบ 5,000.00 บาท", a bar on one scale for all months
  with a budget mark, and a status chip with icon + text: "อยู่ในงบ" (check),
  "เกินงบ" (triangle) or "เกินเกณฑ์ที่ ธปท. แนะนำ" (octagon; wins over เกินงบ).
- Tap a month (a button with `aria-expanded`) to list its installments: name, app
  if given, monthly amount, "งวดที่ x จาก y", and "งวดสุดท้าย" on its last month.
- **On top, the plan card** (`GET /assistant/plan`, PR B): "กลับมาอยู่ในงบเดือน
  {back_in_budget_month}" (or "ทุกเดือนอยู่ในงบ"), then "ตั้งแต่ {safe_new_from}
  ผ่อนเพิ่มได้ไม่เกินเดือนละ {safe_new_monthly}". When this month is over budget
  (`pause_until` set), the line starts "ตอนนี้ยังไม่ควรผ่อนเพิ่ม" and the card gets a
  warn border. A caption says the amount is for a 12-month plan, within the budget
  and within a third of income. No ranking of which debt to pay first (L69).
- No money arithmetic: totals, flags and instalment numbers come from the API.
- Its colours already follow the accents: green in budget, amber over budget. Red
  above a third of income is a level only this screen and the verdict show.
- States: loading, error, settings missing, no months.

### 7.3 Screen 3: เช็กก่อนผ่อน, the form (`#/think`)
0. **Hint** under the intro (PR B, from the plan): "ผ่อนเพิ่มได้ไม่เกินเดือนละ
   {safe_new_monthly} ตั้งแต่ {safe_new_from}", or "ตั้งแต่ ... ยังผ่อนเพิ่มไม่ได้โดยไม่เกินงบ"
   when it is 0.00. Advice only; nothing is blocked. Left out if the plan fails.
1. Fields, every one in view and none folded, in this order (UI-37): **ชื่อสินค้า
   (ไม่บังคับ)**, then **แอปที่ผ่อน (ไม่บังคับ)** (free text, at most 60 characters,
   placeholder "เช่น ShopDemo"; never a list of real platforms, rule 5), then the four
   the preview needs: **ราคาสินค้า** (**ยอดเงิน** for a cash kind),
   **จำนวนเดือนที่ผ่อน** with quick picks "3 เดือน", "6 เดือน", "10 เดือน" and "12
   เดือน" under it (a tap fills the field, typing still works, the picked one is
   `aria-pressed`), **ค่างวดต่อเดือน**, **เริ่มจ่ายงวดแรก**.
1b. **Kind:** "ผ่อนสินค้า" is preselected. The small link "เป็นรายการเงินสด?" sits
   between แอปที่ผ่อน and the price, whose label it changes. It shows the three kinds
   (the link goes, the keyboard moves to the checked kind): ผ่อนสินค้า on its own row,
   กดเงินสด and สินเชื่อเงินสด side by side. A cash kind shows
   "รายการเงินสดจะไม่กันเงินเข้ากันชน", and the kinds stay shown while one is chosen.
2. **Monthly amount:** once price and months are valid, it is prefilled with the
   0% suggestion from `src/api.ts` (price / months rounded UP to 0.01; the screen
   computes nothing). Help: "คิดแบบผ่อน 0% ถ้าแอปแจ้งยอดต่อเดือนไม่ตรงนี้
   แก้ให้ตรงกับแอปได้". Once the user types in it, a suggestion never replaces it
   (UI-18).
3. **First due month:** no default. Two required choices of equal size, the word on
   one line and the month on a smaller second line: "เดือนนี้" / "ต.ค. 2569" and
   "เดือนหน้า" / "พ.ย. 2569". Help: "ดูได้ในหน้าสรุปก่อนกดผ่อนของแอปผ่อน".
4. **"ประเมินภาระผ่อน"** sits in the action bar above the nav (5.8), always in view.
   It stays disabled until the four fields are valid (`canPreview`, UI-37); while it
   is, "กรอกราคา จำนวนเดือน ค่างวด และเดือนเริ่มจ่ายให้ครบก่อน" sits above it (its
   `aria-describedby`), naming the four so it never reads as the first four fields. It
   calls the preview (writes nothing) and opens 7.3b. The form is kept, so "แก้ไข"
   there returns to it with every value.
5. Changing a field while the preview is in flight drops its answer.
- Demo strip: three buttons (อยู่ในงบ, เกินงบ, เกินเกณฑ์) fill ม่อน's examples,
  first due month next month.
- No label wraps or clips at 390px or in the 370px desktop frame (measured in the
  DOM, every state).
- States: loading, error (try again), settings missing (also from a 409
  `SETTINGS_REQUIRED`). One screen from loading to the form: the header (and its
  bell) and the nav are mounted once.

### 7.3b ผลการประเมิน (`#/result`), the main slide screenshot
1. Top: a one-line summary ("โน้ตบุ๊ก 30,000.00 บาท · 10 เดือน · เดือนละ 3,000.00
   บาท · เริ่ม พ.ย. 2569 · ShopDemo") and "แก้ไข" (back to the form, values kept).
2. A large verdict card: 64px icon, the label, the sentence, the advice note.
3. Month bars against the dashed budget line (5.4): solid colours, a ⚠ above a
   month over a third of income, the new item's share as the white, outlined top of
   each bar, a legend of only what the chart shows, and one plain line
   "เกินงบ {n} เดือน: {first} ถึง {last}". The verdict card holds the
   warning, and each fact is said once (UI-41).
4. "ถ้าบันทึก จะกันเงินเข้ากันชน" and the amount (`saving_if_recorded`), or why
   nothing is saved this time.
5. Action bar: **บันทึก** (primary, wider) and **ยังไม่ซื้อ** (secondary), always
   enabled (advice only). On RED, a link "ดูภาระผ่อนรายเดือน" under them (PR B).
6. **บันทึก** sends the previewed body with the same `client_request_id`, so a
   retry records once. Recorded: a check, "บันทึกรายการผ่อนแล้ว", the new monthly
   total, the amount saved (or "ครั้งนี้ไม่ได้กันเงินเข้ากันชน"), and the verdict
   again if it was not GREEN.
7. **ยังไม่ซื้อ**: "โอเค ยังไม่ซื้อ ไว้ค่อยคิดใหม่ได้เสมอ", nothing is written.
8. After 6 or 7: **เช็กรายการอื่น** (back to an empty form) and หน้าหลัก.
- Opened without a preview (a reload): "ยังไม่มีรายการที่ประเมิน กรอกข้อมูลก่อนนะ" and "ไปกรอกข้อมูล".

### 7.4 Screen 4: Buffer, feature 2 (`#/buffer`, `screens/Buffer.tsx`)
- Teal: the header is tinted with the shield. The balance card is the wallet's
  colour and edge (`EDGE.buffer`, UI-35): shield badge, "ยอดในกันชน", the balance, the 6-segment meter,
  "พอจ่ายค่างวดได้ประมาณ N เดือน" (or nothing owed), and the monthly total. After a
  move the new balance shows at once; the meter and the months wait for `GET /buffer`
  to answer for it (`walletFor`, UI-13), so they never show the old balance's months.
- **"ถ้าเดือนไหนเกินงบ", the buffer plan** (the plan's `buffer_plan`): "ค่างวดส่วนที่
  เกินงบรวมทุกเดือน {shortfall}", then "กันชน {balance} พอจ่ายส่วนที่เกินได้ทั้งหมด"
  (teal) or "กันชน {balance} ยังขาดอีก {still_short}" (amber); with no month over,
  "ทุกเดือนอยู่ในงบ ยังไม่ต้องใช้กันชน". It reloads after a move, so it always matches
  the balance above it. Its `covered` and `still_short` are measured against the
  `remaining_gap`, what the moves made for each month have not yet prepared, so once
  some is prepared a line "ยังไม่ได้เตรียม {remaining_gap}" sits between them, and with
  every month prepared the card says "เตรียมเงินจากกันชนครบทุกเดือนที่เกินงบแล้ว".
- **"เดือนที่ค่างวดเกินงบ"**: one card per month over budget (`GET /buffer/shortfalls`,
  UI-47), opened scrolled to the month that Home or 7.2b asked for. The state line,
  then, while the month is not prepared, three numbered steps:
  ① "ใช้กันชน {amount}", ② "ย้ายเข้าบัญชีหลัก +{amount}", ③ "จ่ายค่างวดในแอปผ่อน
  (ผู้ใช้ทำเอง) ค่างวด {month} {total}"; the helper "ย้ายก่อนวันที่แอปผ่อนตัดเงิน
  แนะนำทำในวันเงินเดือนเข้า"; and the filled teal button "ใช้กันชนจ่ายส่วนที่เกิน".
  {amount} is the API's `remaining_gap`, or the balance when that is smaller (a
  comparison; screens never add or subtract money, UI-51). The move sends
  `for_month`. After it, ① and ② get a check, ① reads "ใช้กันชน {amount} (กันชน
  {before} → {after})" with both balances from the API, and a success line says
  "ย้าย {amount}เข้าบัญชีหลักแล้ว กันชนเหลือ {balance} จ่ายค่างวดในแอปผ่อนได้เลย". The
  "after" balance shows only once the move is done: before it, it would need
  arithmetic on the client. Step ③ stays the user's own: KidNee never pays the app.
  A prepared month shows its check line and no steps. Between the user's own
  accounts the word is "ย้าย", never "โอน" (UI-47).
- "ย้ายกลับบัญชีหลัก": an amount and an outlined button (the month's move is the
  primary), always enabled (L66: the user's own action, never automatic, never
  blocked); it sends no `for_month`. Every move keeps one `client_request_id` per
  amount and month, reused on a retry. All moves on the screen share one lock
  (`mover` in `bufferMove.ts`): while one is out, every other move button is disabled
  and a press is ignored, so a double tap, or two months pressed together, moves the
  money once. "Before" is the balance the API last gave, and only the newest
  `GET /buffer` answer is shown (UI-13, UI-47).
- 422 `AMOUNT_ABOVE_BALANCE` is a field error that names the balance. Any other
  failure is an unknown outcome: the screen never says where the money is, reads
  the balance again, and asks to press again with the same amount (same id, so it
  never moves twice). Done: the new balance.

### 7.5 Screen 5: Notifications (`#/alerts`, `screens/Notifications.tsx`)
- Opened from the header bell (with a back button to Home). The API keeps no read
  state, so there is no badge and no "ใหม่" tag. When the user has more alerts than
  the answer lists, a line under them says "แสดง {shown} รายการล่าสุด จากทั้งหมด
  {count} รายการ" (UI-24). A consolidation loan's alert has the bank icon.
- Newest first; icon per kind; the text is the backend's (`notifications/copy.py`,
  copied verbatim into `mock/alerts.ts`). A payday shortfall links to the buffer
  while it holds money, else to ภาระผ่อนรายเดือน (UI-17). Empty:
  "ยังไม่มีแจ้งเตือน".
- A recorded cash entry (`cash_withdrawal`, `cash_loan`) gets its own title and the
  strong (risk-coloured) alert, as the backend sends it (L50).
- The persona's installments are recorded by hand, so every alert uses the manual
  entry copy (L62). The webhook's "Not me" sentence never appears: manual entries
  have no "Not me" (L68), and no frontend source contains it (UI-24).

### 7.6 Removed: payoff assistant and consolidation request
Screens 6 (`#/payoff`) and 7 (`#/consolidate`) and their code were deleted in part
4, with `payoffSteps.ts`, the old mock and their tests (UI-15, UI-23). Nothing
else imported them, so deleting was safe. Their parts now live in 7.2 (cards 4 and
6), 7.2b (the plan card), 7.3 (the hint) and 7.4 (the buffer plan).

### 7.8 Demo panel (`components/DemoPanel.tsx`)
- A dashed "Demo" button in the header opens a sheet over the phone frame, marked
  "สำหรับนำเสนอเท่านั้น ไม่ใช่ส่วนหนึ่งของแอป".
- The button shows only while the demo endpoints answer: on open, the app sends
  `POST /demo/payday` with an empty body, which writes nothing. A 422 means they are
  on; a 404, or no answer, means off, and there is no button (UI-49).
- "ผู้ใช้ตัวอย่าง" (the real API only): switches between the personas seeded in
  `lumen_kidnee` (`demo-mon` ม่อน, `demo-over`, `demo-consolidate`, each with its
  one-line story; section 10). It sets `X-Demo-User`, keeps the choice in
  `localStorage` (an unknown id is ignored), goes Home and reloads (UI-49).
- Payday: pick a month, run `POST /demo/payday`, see the outcome in words; a
  second run for the same month says it already ran (L67, once a month). The
  screen on show reloads after it.
- Scenes (`--mode mock` only): first launch; ม่อน with settings; "มีเดือนเกินงบ" (records
  the YELLOW laptop from next month: 2 months over, the buffer covers it, no
  consolidation); "เกินงบตั้งแต่เดือนนี้" (records the RED motorbike from this
  month: 9 months over, the pause line, the buffer still short, consolidation
  eligible); "มีเดือนเกินงบ กันชนว่าง" (the laptop, then the whole buffer moved back to
  the main account, so the hero has no buffer line); "ผู้ช่วยกำลังสรุป (ตอบช้า)" (the summary takes 15
  seconds) and "ผู้ช่วยสรุปไม่สำเร็จ" (it fails with 503). The screen on show reloads.

## 8. Thai copy

Source of truth: `frontend/src/copy.ts`. The key strings:

| Where | Thai |
|---|---|
| Footer | Concept prototype สำหรับการแข่งขัน |
| Primary button | เช็กก่อนผ่อน |
| Preview button | ประเมินภาระผ่อน |
| GREEN | อยู่ในงบ · ค่างวดรวมทุกเดือนตลอดแผนผ่อนนี้ไม่เกินงบที่คุณตั้งไว้ |
| YELLOW | บางเดือนเกินงบ · มีบางเดือนที่ค่างวดรวมเกินงบที่คุณตั้งไว้ ดูได้จากกราฟด้านล่าง |
| RED | เกินเกณฑ์ที่ ธปท. แนะนำ (1 ใน 3 ของรายได้) · บางเดือนค่างวดรวมสูงกว่าเกณฑ์ที่ ธปท. แนะนำ คือค่างวดหนี้ทั้งหมดต่อเดือนไม่ควรเกิน 1 ใน 3 ของรายได้ |
| Monthly help | คิดแบบผ่อน 0% ถ้าแอปแจ้งยอดต่อเดือนไม่ตรงนี้ แก้ให้ตรงกับแอปได้ |
| First due help | ดูได้ในหน้าสรุปก่อนกดผ่อนของแอปผ่อน |
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
| Hero | เดือนนี้และอีก {n} เดือนอยู่ในงบ · เดือนนี้ยังอยู่ในงบ · เกินงบ {n} เดือน ({first} ถึง {last}) · ดูทุกเดือน (the chevron, to screen readers) |
| Buffer state line (hero, 7.2b, 7.4) | {month} เกินงบ {shortfall} · เตรียมจากกันชนแล้ว {prepared} ยังขาด {gap} · เตรียมเงินจากกันชนแล้ว · ใช้กันชนจ่ายส่วนที่เกิน |
| Buffer steps | ใช้กันชน {amount} · ย้ายเข้าบัญชีหลัก +{amount} · จ่ายค่างวดในแอปผ่อน (ผู้ใช้ทำเอง) ค่างวด {month} {total} · ย้ายก่อนวันที่แอปผ่อนตัดเงิน แนะนำทำในวันเงินเดือนเข้า · ย้าย {amount}เข้าบัญชีหลักแล้ว กันชนเหลือ {balance} จ่ายค่างวดในแอปผ่อนได้เลย |
| Months, last line | ยอดในแอปผ่อนไม่ตรงกับที่นี่? อาจมีรายการที่คุณไม่ได้ทำ ติดต่อแอปผ่อนโดยตรงจากช่องทางในแอป อย่าโอนเงินให้ใครที่โทรมาทวง |
| Rejected field (422) | ระบบไม่รับค่านี้ ลองแก้แล้วกดอีกครั้ง |
| Result bars | เกินงบ {n} เดือน: {first} ถึง {last} · อยู่ในงบ · เกินงบ · เกินเกณฑ์ที่ ธปท. แนะนำ · ค่างวดที่มีอยู่ · ค่างวดชิ้นใหม่ |
| Installments | งวดที่ {x} จาก {y} · หมด {month} · เริ่ม {month} · ผ่อนครบแล้ว {n} รายการ · ไม่นับในยอดต่อเดือน |
| Wallet | กันชนของคุณ › · พอ {n} เดือน · ยังไม่พอ 1 เดือน · ไม่มีค่างวด |
| Assistant | ผู้ช่วย KidNee · ตัวอย่าง · อ่านต่อ › · ย่อ · กำลังสรุป... |
| Consolidation | ตอนนี้ยังไม่จำเป็นต้องรวมหนี้ · ทางเลือกจากธนาคาร · ตอนนี้ · ถ้ารวมหนี้ (ตัวอย่าง) · ยอดรวมทั้งหมด · ค่างวดลดลงเดือนละ {monthly_reduction} ทุกเดือนกลับมาอยู่ในงบ · สนใจรวมหนี้ |
| Form | ชื่อสินค้า (ไม่บังคับ) · แอปที่ผ่อน (ไม่บังคับ) · เป็นรายการเงินสด? · ยอดเงิน · {n} เดือน · กรอกราคา จำนวนเดือน ค่างวด และเดือนเริ่มจ่ายให้ครบก่อน |

Months are Thai short names with the Buddhist-era year ("พ.ย. 2569"), as the
backend writes them.

## 9. API types per screen

All in `frontend/src/api-types.ts`, copied from the backend; every call and field
with its exact JSON is in `docs/api/kidnee-endpoints.md`. Money is a string.
`src/api.ts` is the only module that gets data (test UI-07). It sends
`X-Demo-User` for the chosen persona (`src/personas.ts`, `demo-mon` by default;
L60, demo only) and calls `/api/...`: in dev the Vite proxy forwards it to
`http://127.0.0.1:8000` with `/api` stripped, and in the one-server demo the API
is mounted at `/api` (L73). With `--mode mock` the same calls are answered by
`src/mock/server.ts`, and nothing reaches a server (UI-50).

| Screen | Call | Request | Response | Errors |
|---|---|---|---|---|
| 1 | `GET /settings` | | `SettingsOut` | 404 = none yet |
| 1 | `POST /settings` / `PUT /settings` | `SettingsIn` (`saving_rule` is `{mode:"percent",percent}` or `{mode:"fixed",amount}`) | `SettingsOut` with `warnings` | 409 exists (POST), 404 none (PUT), 422 |
| 2 | `GET /debts/summary` | | `DebtSummary` (`installments: InstallmentLine[]`, with `platform_name`, `first_due_date`, `last_due_date`) | |
| 2, 2b | `GET /debts/months` | `?count=N` (optional; Home and 2b leave it out) | `MonthsOut { months: MonthDetail[], months_truncated }`; `MonthDetail` = `MonthRow` + `budget`, `over_by` + `installments: MonthInstallment[]` (`installment_id, item_name, platform_name, monthly_amount, installment_no, installments_total, is_last, last_month`) | 409 `SETTINGS_REQUIRED`, 422 bad count |
| 3 | `GET /installments/suggested-monthly` | `?item_price=&months=` | `SuggestedMonthlyOut { monthly_amount }`: price / months rounded UP to 0.01 | 422 |
| 2, 4 | `GET /buffer` | | `BufferOut` (`months_covered` null when nothing is owed) | |
| 2, 2b, 4 | `GET /buffer/shortfalls` | | `ShortfallsOut`: `balance`, `shortfall`, `remaining_gap`, `covered`, `still_short`, and `months: ShortfallMonth[]` (`month, total, budget, shortfall, prepared, remaining_gap, state, covered_by_buffer, still_short`), `months_truncated`; `state` is `not_prepared`, `partly_prepared` or `prepared` | 409 `SETTINGS_REQUIRED` |
| 3 | `POST /installments/preview` | `ManualEntryIn` | `PreviewOut` = `VerdictOut` + `saving_if_recorded` | 409 `SETTINGS_REQUIRED`, 422 |
| 3b | `POST /installments` | `ManualEntryIn` (same `client_request_id` on a retry; `platform_name` trimmed, `null` when blank, at most 60 characters) | `RecordedOut` (`saved_amount`, `monthly_total`, `warnings: VerdictOut`); 201 new, 200 repeat | 409 reused id with other fields, 409 `SETTINGS_REQUIRED`, 422 |
| 4 | `POST /buffer/move-to-main` | `MoveIn` (`client_request_id`, `amount`, and `for_month` only for a month's move) | `MovedOut` (with `for_month`); 201, 200 repeat | 409 reused id with another amount or month, 422 `AMOUNT_ABOVE_BALANCE` |
| Demo | `POST /demo/payday` | `{ month: "YYYY-MM" }` (`{}` as the probe, 7.8) | `PaydayOut` | 404 when demo endpoints are off |
| 5 | `GET /notifications` | | `NotificationsOut` (`notifications: NotificationOut[]`, newest first: `kind`, `title`, `body`, `created_at`, `installment_id`; and `count`, every alert the user has) | |
| 2, 2b, 3, 4 | `GET /assistant/plan` | | `AssistantPlanOut`: `months`, `months_truncated`, `back_in_budget_month`, `pause_until`, `safe_new_monthly`, `safe_new_from`, `safe_new_months`, `buffer_plan {shortfall, remaining_gap, balance, covered, still_short}`, `consolidation {eligible, reason, estimate}`; `EstimateOut` adds `current_monthly_total` (the offer's "ตอนนี้") and `monthly_reduction` | 409 `SETTINGS_REQUIRED` |
| 2 | (no call) the assistant's example | | Worded from `GET /assistant/plan` by `exampleSummary` and always labelled ตัวอย่าง (AI is roadmap only). `POST /assistant/summary` exists only in the mock | |
| Demo | `POST /demo/scene` **mock only** | `{ scene }` | 204 | |

Error bodies: `{"detail": {"code", "message"}}` for coded errors, a plain string
`detail` for older ones, and FastAPI's list for 422. `ApiError` exposes `status`,
`code` and `fields`, the last name in each 422 `loc` (UI-50). The forms map those
names to their own fields and mark them "ระบบไม่รับค่านี้ ลองแก้แล้วกดอีกครั้ง"; a 422
on nothing the user can fix shows the general failure. `SETTINGS_REQUIRED` opens
settings (the form keeps its draft).

**Readers (UI-39, `src/apiFields.ts`).** The backend now sends `monthly_reduction`,
`current_monthly_total` and `platform_name`. `api.ts` still passes these answers
through its reader, so a screen never crashes on such a field:
- absent or not what the contract says (a JSON number, a sign, a comma): read as
  null, with one console warning per answer and field;
- the screen leaves out only what needs it: the offer's benefit line, a row's app
  name. Nothing is guessed, and the answer given is not changed;
- the summary without `text` is an error (the bubble's state with "ลองอีกครั้ง");
  without `is_example` it keeps its example tag, the safe side for AI text.

Fields not listed here are not checked again on screen.

## 10. Demo personas and scenes

**On the real API** (`python -m demo.kidnee reset --yes`, then `serve`; KD-04,
KD-05), the Demo panel switches between three seeded personas, each telling one
story. Their numbers are in `docs/api/kidnee-endpoints.md`:
- `demo-mon`, ม่อน: every month in budget.
- `demo-over`: this month and next over budget by 1,500.00 each; the buffer
  covers both. The one to show the three steps and the prepared state.
- `demo-consolidate`: nine months over budget, a small buffer that pays part of the
  first month (partly prepared), and the bank's consolidation offer.
Platform names are fictional ("ShopDemo", "RideDemo"), and one item is unnamed.

**In the mock** (`npm run dev -- --mode mock`), the rest of this section:
**ม่อน** (demo user `demo-mon`; UI-45 checks that no older name is left in
`frontend/` or here), 24, first job. Income 20,000.00, payday the 25th, installment budget
5,000.00, auto-save 10% of the price, leftover saving on, consent given. Main
account 9,500.00, buffer 4,800.00.

Existing installments (months relative to the demo month; on 27 Oct 2026):
All recorded by hand; the app is the user's own text.
- หูฟังไร้สาย, app ShopDemo: 2,000.00 a month, last month ธ.ค. 2569 (ends soon).
- ตู้เย็น, no app given ("ไม่ระบุแอป"): 1,500.00 a month, last month มิ.ย. 2570.
- กระเป๋าเป้, app ShopDemo: paid off (folded into "ผ่อนครบแล้ว 1 รายการ ›").
Now: 3,500.00 a month.

| Example | Price | Plan | Busiest month | Verdict |
|---|---|---|---|---|
| โทรศัพท์ | 12,000.00 | 10 x 1,200.00 | 4,700.00 (in budget) | GREEN อยู่ในงบ |
| โน้ตบุ๊ก | 30,000.00 | 10 x 3,000.00 | 6,500.00 (over budget, under one third: 19,500 <= 20,000) | YELLOW บางเดือนเกินงบ |
| มอเตอร์ไซค์ | 48,000.00 | 12 x 4,000.00 | 7,500.00 (7,500 x 3 = 22,500 > 20,000) | RED เกินเกณฑ์ที่ ธปท. แนะนำ |

### Scenes, in order
1. **Settings** (`/#/settings`): empty first-time form. Tap "Demo: กรอกข้อมูลตัวอย่างของ
   ม่อน", save. Optionally change the budget to 7,000 to show the one-third
   warning (7,000 x 3 > 20,000), then back to 5,000.
2. **Home**: 3,500.00 of 5,000.00, "เดือนนี้และอีก 8 เดือนอยู่ในงบ", the wallet
   4,800.00 (พอ 1 เดือน), installments grouped by app ("งวดที่ 4 จาก 6 · หมด ธ.ค.
   2569"), and "ผ่อนครบแล้ว 1 รายการ ›". Tap the month card for
   "ภาระผ่อนรายเดือน" (Oct 2569 to Jun 2570; open ธ.ค. to see "งวดสุดท้าย"), back,
   then tap **เช็กก่อนผ่อน**.
3. **Form**: type 1000 and tap "3 เดือน" to show the 0% suggestion 333.34; point
   out that the check waits for the first due month
   ("กรอกราคา จำนวนเดือน ค่างวด และเดือนเริ่มจ่ายให้ครบก่อน").
4. **YELLOW**: tap "เกินงบ", then **ประเมินภาระผ่อน**. On the result screen, Nov
   and Dec are amber, the laptop's share is the white top of each bar, and the line
   under them says "เกินงบ 2 เดือน: พ.ย. 2569 ถึง ธ.ค. 2569". Point out
   "บันทึกได้เสมอ". Tap "ยังไม่ซื้อ".
5. **RED**: "แก้ไข" back, tap "เกินเกณฑ์", ประเมินภาระผ่อน. The ธปท. guidance
   sentence.
6. **GREEN**: tap "อยู่ในงบ", ประเมินภาระผ่อน, then **บันทึก**: 1,200.00 saved to
   the buffer, new total 4,700.00.
7. **Home** again: the installments now total 4,700.00 a month (from next month), buffer 6,000.00.
8. The bell: the ตู้เย็น manual-entry alert, newest first.
   Home's assistant bubble and the banner "ตอนนี้ยังไม่จำเป็นต้องรวมหนี้".
9. Demo, "ม่อน: เกินงบตั้งแต่เดือนนี้": Home's hero bar turns amber past the budget
   mark, with one warning line "⚠ เกินงบ 9 เดือน (ต.ค. 2569 ถึง มิ.ย. 2570)" and one
   buffer line "ต.ค. 2569 เกินงบ 2,500.00 บาท" with "ใช้กันชนจ่ายส่วนที่เกิน". "ทางเลือกจากธนาคาร": 7,500.00 a month
   now, 3,369.88 if consolidated, but 80,877.12 in total against 67,500.00, all four
   the same size; "ค่างวดลดลงเดือนละ 4,130.12 บาท ทุกเดือนกลับมาอยู่ในงบ" (example rate
   18%, 24 months); "สนใจรวมหนี้". Tap the hero: "กลับมาอยู่ในงบเดือน ก.ค. 2570"
   and "ตอนนี้ยังไม่ควรผ่อนเพิ่ม". The form's hint. กันชน: 10,500.00 over in all,
   900.00 still short. Demo payday.

Home per scene (UI-33 tests the rules behind it):

| Scene | Hero | Buffer line | Assistant | Consolidation |
|---|---|---|---|---|
| ม่อน: ตั้งค่าแล้ว | all in budget, one line | none | summary | banner |
| มีเดือนเกินงบ | this month in budget; "เกินงบ 2 เดือน (พ.ย. 2569 ถึง ธ.ค. 2569)" | พ.ย. 2569 เกินงบ 1,500.00 บาท, ใช้กันชนจ่ายส่วนที่เกิน | summary | banner |
| เกินงบตั้งแต่เดือนนี้ | "เกินงบ 9 เดือน (ต.ค. 2569 ถึง มิ.ย. 2570)" | ต.ค. 2569 เกินงบ 2,500.00 บาท, ใช้กันชนจ่ายส่วนที่เกิน | summary | bank offer |
| มีเดือนเกินงบ กันชนว่าง | as มีเดือนเกินงบ, wallet empty | พ.ย. 2569 เกินงบ 1,500.00 บาท, no button | summary | banner |
| ผู้ช่วยกำลังสรุป (ตอบช้า) | all in budget | none | loading | banner |
| ผู้ช่วยสรุปไม่สำเร็จ | all in budget | none | error, retry | banner |

Shortcuts for slides (mock only): `http://127.0.0.1:5173/?persona#/home` starts with the
settings saved; `?persona&scene=YELLOW#/think` fills that example and opens its
result screen.
Reloading the page resets the mock.

## 11. How to run

Node 22.12 or later (Vite 8). From `frontend/`:

```bash
npm ci              # exact versions from package-lock.json
npm run dev         # http://127.0.0.1:5173 (loopback only, never 0.0.0.0), calls the API on 127.0.0.1:8000
npm run dev -- --mode mock   # the same screens on the in-browser mock, with the scenes
npm test            # UI-01 to UI-51 (compiled with tsc, run with node --test)
npm run typecheck   # tsc --noEmit, strict
npm run build       # typecheck + production build to dist/
npm audit
```

After switching branches (or after `npm ci`), stop the dev server and start it
again with `npm run dev -- --force`. Vite keeps pre-bundled dependencies in
`node_modules/.vite`, and a stale copy makes the browser get "504 (Outdated
Optimize Dep)" for files such as `react-dom_client.js`, which leaves a blank page.
If it still happens, delete `node_modules/.vite` and run `npm run dev -- --force`.

Manual check, never in CI (it needs Chrome and the dev server): with
`npm run dev -- --mode mock` running (it uses the scenes), `node scripts/nav-layer-check.mjs` checks that the nav is the top layer
over everything that scrolls, on every screen (5.8, "Layers"; `scripts/README.md`).

The real backend for `npm run dev`: run it on `127.0.0.1:8000` with
`DEMO_ENDPOINTS_ENABLED=true` for payday and the persona switcher. The one-server
demo (`python -m demo.kidnee serve`, L73) serves the built `dist/` with the API
and its own `lumen_kidnee` database; build first (`npm run build`).

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

Session 15-UI (Home hierarchy), searched with `--domain ux`, `--domain color`
and `--stack html-tailwind`, plus its pro rules checklist:
- Used: never colour only (every accent has an icon and text, UI-34); a loading
  state that keeps its height, with `aria-busy` and no spinner-like icon; an empty
  state as one line, not a card; `aria-expanded` on every disclosure; decorative
  icons and the mascot `aria-hidden`; meaningful icons and meter segments at least
  3:1; the 4/8px spacing rhythm; 44px targets.
- Overridden: its dark-mode rules (light mode only) and its fintech palettes (we
  keep the green family and add one accent per feature).
