# KidNee screens: the backend API

Every endpoint the KidNee screens use, with request and response JSON. Each example was captured from the real app on 2026-10-28. The capture used the test database, with the clock fixed at 2026-11-10 and every write rolled back afterwards. The Session 17 fields (marked "(Session 17)") were added to those examples by hand from the models, then checked against the one-server demo on `lumen_kidnee` on 2026-10-29. Ids and timestamps differ per run. Where a list was long, it is shortened and marked `(shortened)`. Every key is shown.

Source of truth: the pydantic models named under each endpoint. If this file and the code disagree, the code wins. Report the difference as a bug.

## Conventions
- **Prefix.** The browser always calls `/api/...`; see "How the browser reaches the API" at the end. The paths below are written without `/api`, the way the backend routes them.
- **User.** Every request names the user in the header `X-Demo-User` (1 to 128 characters, no control characters). A missing or malformed header gives `401 {"detail": "unauthorized"}`. This is demo-only identification, not auth (L60 1).
- **Money** is always a JSON string with exactly 2 decimals in responses, for example `"1500.00"`.
  - In requests it is a string with at most 2 decimals and no sign, exponent, comma or space: `"1500"` and `"1500.5"` are fine.
  - A JSON number or a third decimal is a 422. It is never rounded (L49).
- **Months** are `"YYYY-MM"`. "This month" is the current month in Bangkok (UTC+7).
- **Errors.**
  - 422 is `{"detail": [{"type": ..., "loc": [...]}]}`. It never echoes the input.
  - Coded errors are `{"detail": {"code": ..., "message": ...}}`.
  - `SETTINGS_REQUIRED` (409) means the user has no income and budget yet:
    `{"detail": {"code": "SETTINGS_REQUIRED", "message": "set income and budget with POST /settings first"}}`.
- **Bodies** are strict: unknown keys are a 422, and ints must be JSON ints.

## Changes the frontend must make against the mock (`frontend/src/api-types.ts`)
All made in Session 17 PR B (`feat/kidnee-wiring-frontend`): the screens call this API, and `npm run dev -- --mode mock` keeps the mock.
| Mock today | Backend | What to change |
|---|---|---|
| `ManualEntryIn.platform_name` | Accepted (Session 17): optional, 1 to 60 characters, no control characters | Send it, or `null` when the field is blank. `""` is a 422. |
| `InstallmentLine.platform_name`, `MonthInstallment.platform_name` | Returned (Session 17); `null` when not named | Group `null` under "ไม่ระบุแอป". |
| `MonthDetail.over_by` | Returned (Session 17) | Remove its `TODO(backend)`. |
| `MonthInstallment.last_month` | New (Session 17) | Optional: the line's last due month. |
| `EstimateOut.monthly_reduction`, `current_monthly_total` | Returned (Session 17) | Remove its `TODO(backend)`. Show `current_monthly_total` as the offer's "ตอนนี้", so both of the card's figures come from the same month as the hero. |
| `POST /buffer/move-to-main` `for_month` | New (Session 17) | Send it from "ใช้กันชนจ่ายส่วนที่เกิน"; leave it out for "ย้ายกลับบัญชีหลัก". |
| `GET /buffer/shortfalls` rows | Add `prepared`, `remaining_gap`, `state` (Session 17) | Show the prepared state from `state`; never compute it. |
| `NotificationsOut.unread_count`, `NotificationOut.read`, `POST /notifications/read` | No read state; `count` = every alert the user has | Use `count`; drop the unread badge logic and the mark-read call. |
| `NotificationOut` | Adds `installment_id` (null for payday alerts) | Add the field. |
| `NotificationKind` | Adds `consolidation_loan` | Add it to the union. |
| `MonthDetail` | Adds `budget`. `MonthsOut` adds `months_truncated` | Add both. |
| `GET /buffer/shortfalls` | New (the buffer's "ถ้าเดือนไหนเกินงบ" card) | Used by Home's hero, the months screen and the buffer screen for each month's state. |
| `InstallmentKind` | Responses may also say `consolidation_loan` (a request may not) | Add it to response types only. |
| `InstallmentStatus` | Adds `consolidated` (L72: paid off by a consolidation loan, not owed) | Add it; show it with the not-counted lines. |
| `POST /demo/scene` | Not built (mock only) | Kept in the mock; scenes exist only in the mock. |
| `POST /assistant/summary` (mock) | `GET /assistant/summary` (Session 18) | Done in Session 18: both modes call the GET; the mock answers it as the backend does without a key. No `is_example` and no ตัวอย่าง tag. |

---

## Settings (L63, L64)
### `POST /settings` (first time) and `PUT /settings` (afterwards)
Model: `user_settings/schemas.py` (`SettingsIn`, `SettingsOut`).

Request:
```json
{
  "income": "20000.00",
  "payday": 25,
  "monthly_installment_budget": "5000.00",
  "saving_rule": {"mode": "percent", "percent": 10},
  "auto_save_enabled": true,
  "auto_save_consent": true,
  "leftover_saving_enabled": true
}
```
- `saving_rule` is exactly one of `{"mode": "percent", "percent": 1-100}` or `{"mode": "fixed", "amount": "<money > 0>"}`.
- `auto_save_enabled: true` needs `auto_save_consent: true` in the same body.

Response: 201 for POST, 200 for PUT.
```json
{
  "income": "20000.00",
  "payday": 25,
  "monthly_installment_budget": "5000.00",
  "saving_rule": {"mode": "percent", "percent": 10},
  "auto_save_enabled": true,
  "consent_at": "2026-10-28T07:23:38.129584Z",
  "leftover_saving_enabled": true,
  "warnings": []
}
```
- `warnings` is `["BUDGET_ABOVE_ONE_THIRD_OF_INCOME"]` when `budget * 3 > income`. The settings are saved either way.
- Errors:
  - POST when settings already exist: `409 {"detail": "settings already exist"}`. Retry as PUT.
  - PUT before any POST: `404 {"detail": "settings not found"}`.

### `GET /settings`
- 200 with the same body as above.
- 404 `{"detail": "settings not found"}` before the first save.

## Debts
### `GET /debts/summary`
Model: `debts/service.py` (`DebtSummary`). Every installment of the user, with the totals over the owed ones (L43).
```json
{
  "monthly_total": "3500.00",
  "total_remaining": "27000.00",
  "debt_free_date": "2027-07-01",
  "installments": [
    {
      "id": "3cc1d482-8891-4727-9ba7-2314e3f0291b",
      "vendor": "manual",
      "contract_id": "db0a92b4-24bc-4079-b548-f5c125ea9e0b",
      "kind": "purchase",
      "item_name": "ตู้เย็น",
      "platform_name": null,
      "principal": "15000.00",
      "monthly_amount": "1500.00",
      "months": 10,
      "paid_amount": "0.00",
      "late_fees_accrued": "0.00",
      "remaining": "15000.00",
      "status": "active",
      "disputed_at": null,
      "owed": true,
      "first_due_date": "2026-10-01",
      "last_due_date": "2027-07-01"
    }
  ]
}
```
- `installments` is shortened here: the user's second line is left out.
- `status` is one of `active`, `paid_off`, `cancelled`, `disputed` or `consolidated`.
- `owed` is false for lines that do not count toward the totals.
- Entries the user records (`vendor: "manual"`) never receive payments, so `paid_amount` stays `"0.00"`.
- `platform_name` (Session 17) is the app the user named for a manual entry, or `null`. Platform rows always have `null`: their `vendor` names them.

### `GET /debts/months[?count=N]` (new)
Model: `debts/months.py` (`MonthsOut`). This feeds the monthly view and Home's month card.
- Rows start at this month.
- Without `count`, rows run to the last month an owed installment is due: at least one row and at most 600, with `months_truncated`. With `count` (1 to 600), there are exactly N rows, and months with nothing due have `"total": "0.00"` and `"installments": []`.
- Totals use the L43 owed set at the full monthly amount in every scheduled month, the same as `POST /installments/preview` and `GET /assistant/plan`.
- `over_budget` is `total > budget`.
- `over_by` (Session 17) is `total - budget` when over budget, else `"0.00"`. Exactly the budget gives `"0.00"`.
- `over_one_third` is `total * 3 > income` (Bank of Thailand financial-literacy guidance, not a regulation). Exactly the budget, or exactly a third, is not flagged.
- Each row's `installments` lists what is due that month, in the order recorded:
  - `installment_no` is 1 in the item's first due month;
  - `installments_total` is its months;
  - `is_last` marks its last due month;
  - `last_month` (Session 17) is that last due month, `"YYYY-MM"`;
  - `platform_name` (Session 17) is as in `GET /debts/summary`.

`GET /debts/months?count=3`:
```json
{
  "months": [
    {
      "month": "2026-11",
      "total": "3500.00",
      "budget": "5000.00",
      "over_budget": false,
      "over_by": "0.00",
      "over_one_third": false,
      "installments": [
        {"installment_id": "3cc1d482-8891-4727-9ba7-2314e3f0291b", "item_name": "ตู้เย็น", "platform_name": null, "monthly_amount": "1500.00", "installment_no": 2, "installments_total": 10, "is_last": false, "last_month": "2027-07"},
        {"installment_id": "b0a917e0-f9fe-4797-81fd-5e5e72369092", "item_name": "หูฟังไร้สาย", "platform_name": null, "monthly_amount": "2000.00", "installment_no": 4, "installments_total": 6, "is_last": false, "last_month": "2027-01"}
      ]
    },
    {
      "month": "2026-12",
      "total": "3500.00",
      "budget": "5000.00",
      "over_budget": false,
      "over_by": "0.00",
      "over_one_third": false,
      "installments": [
        {"installment_id": "3cc1d482-8891-4727-9ba7-2314e3f0291b", "item_name": "ตู้เย็น", "platform_name": null, "monthly_amount": "1500.00", "installment_no": 3, "installments_total": 10, "is_last": false, "last_month": "2027-07"},
        {"installment_id": "b0a917e0-f9fe-4797-81fd-5e5e72369092", "item_name": "หูฟังไร้สาย", "platform_name": null, "monthly_amount": "2000.00", "installment_no": 5, "installments_total": 6, "is_last": false, "last_month": "2027-01"}
      ]
    },
    {
      "month": "2027-01",
      "total": "3500.00",
      "budget": "5000.00",
      "over_budget": false,
      "over_by": "0.00",
      "over_one_third": false,
      "installments": [
        {"installment_id": "3cc1d482-8891-4727-9ba7-2314e3f0291b", "item_name": "ตู้เย็น", "platform_name": null, "monthly_amount": "1500.00", "installment_no": 4, "installments_total": 10, "is_last": false, "last_month": "2027-07"},
        {"installment_id": "b0a917e0-f9fe-4797-81fd-5e5e72369092", "item_name": "หูฟังไร้สาย", "platform_name": null, "monthly_amount": "2000.00", "installment_no": 6, "installments_total": 6, "is_last": true, "last_month": "2027-01"}
      ]
    }
  ],
  "months_truncated": false
}
```
Errors:
- 409 `SETTINGS_REQUIRED`.
- 422 when `count` is not plain digits from 1 to 600. For `?count=0`: `{"detail": [{"type": "greater_than_equal", "loc": ["count"]}]}`.
- An unknown or repeated query key is also a 422.

## เช็กก่อนผ่อน and recording (L62, L63, L65)
### `GET /installments/suggested-monthly?item_price=&months=` (new)
Model: `installments/suggest.py`. This is the 0% monthly amount the form prefills: `item_price / months`, rounded UP to 0.01, so the payments never add up to less than the price.

`?item_price=12000.00&months=10` gives `200 {"monthly_amount": "1200.00"}`, and `?item_price=1000.00&months=3` gives `{"monthly_amount": "333.34"}`.

Errors are 422:
- `item_price` breaks the money rules or is 0. For `item_price=12000.001`: `{"detail": [{"type": "value_error", "loc": ["item_price"]}]}`.
- `months` is not plain digits from 1 to 600.
- A parameter is missing, repeated or unknown.
- `months * monthly_amount` would pass 9,999,999,999.99, which POST /installments would refuse.

### `POST /installments/preview`
Model: `affordability/schemas.py` (`PreviewOut`). It writes nothing.

Request (the same body as `POST /installments`):
```json
{
  "client_request_id": "c1a8f6a0-1111-4c1e-9d55-0d5f2b8f7a01",
  "kind": "purchase",
  "item_price": "12000.00",
  "months": 10,
  "monthly_amount": "1200.00",
  "first_due_month": "2026-12",
  "item_name": "โทรศัพท์",
  "platform_name": "ShopDemo"
}
```
- `kind` is `purchase`, `cash_withdrawal` or `cash_loan`.
- `item_name` is optional, at most 500 characters, and defaults to `""`.
- `platform_name` (Session 17) is optional: the app the user pays it in, as they call it. 1 to 60 characters, no control characters (U+0000 to U+001F), or `null`. `""` is a 422 (`string_too_short`), so send `null` for a blank field. It is part of the same-request comparison below.
- `months` is 1 to 600.

Response 200 (`months` shortened: every month of the term is listed, here 2026-12 to 2027-09):
```json
{
  "verdict": "GREEN",
  "months": [
    {"month": "2026-12", "total": "4700.00", "over_budget": false, "over_one_third": false},
    {"month": "2027-01", "total": "4700.00", "over_budget": false, "over_one_third": false},
    {"month": "2027-02", "total": "2700.00", "over_budget": false, "over_one_third": false}
  ],
  "over_budget_months": [],
  "monthly_total": "3500.00",
  "saving_if_recorded": "1200.00"
}
```
- `verdict` is `GREEN`, `YELLOW` or `RED` (L65). It is advice only: recording works for every verdict.
- `saving_if_recorded` (new) is what `POST /installments` would save for this body right now:
  - It uses the user's L63 rule, the 500.00 safety net (the whole saving is skipped if the bank balance would drop below 500.00), and the kind (cash never saves).
  - It is `"0.00"` when nothing would be saved.
  - For a `client_request_id` already recorded, it is what POST would report: the first saving for the same fields, and `"0.00"` for different ones (POST answers 409).
- 409 `SETTINGS_REQUIRED`. 422 for an invalid body.

### `POST /installments`
Model: `installments/schemas.py` (`RecordedOut`). Same body as the preview.

Response 201 for a new entry, or 200 with `"status": "duplicate"` and the first answer for the same `client_request_id` and fields (`warnings.months` shortened):
```json
{
  "installment_id": "3cc1d482-8891-4727-9ba7-2314e3f0291b",
  "status": "created",
  "saved_amount": "1500.00",
  "monthly_total": "3500.00",
  "warnings": {
    "verdict": "GREEN",
    "months": [
      {"month": "2026-10", "total": "3500.00", "over_budget": false, "over_one_third": false},
      {"month": "2026-11", "total": "3500.00", "over_budget": false, "over_one_third": false}
    ],
    "over_budget_months": [],
    "monthly_total": "3500.00"
  }
}
```
- `warnings` has no `saving_if_recorded`. The saving is `saved_amount`.
- The same `client_request_id` with other fields (`platform_name` included) is `409 {"detail": "client_request_id reused with other fields"}`.
- 409 `SETTINGS_REQUIRED`.

## กันชน (L66, L67)
### `GET /buffer`
Model: `buffer/schemas.py` (`BufferOut`).
```json
{"balance": "2700.00", "monthly_total": "3500.00", "months_covered": 0}
```
`months_covered` is the whole months of current installments the buffer covers. It is null when nothing is owed.

### `GET /buffer/shortfalls` (new)
Model: `buffer/schemas.py` (`ShortfallsOut`). Each month over budget from this month on, less what the user already moved for it, with the buffer spent on what is left in date order. It is advice only: nothing moves.
- Per month (Session 17):
  - `total`, `budget` and `shortfall` (`total - budget`) never change after a move;
  - `prepared` is what the user moved to the main account for that month (`POST /buffer/move-to-main` with `for_month`), summed;
  - `remaining_gap` is `max(0, shortfall - prepared)`: money moved beyond a month's gap never closes another month's;
  - `state` is `not_prepared` (nothing moved), `partly_prepared`, or `prepared` (`prepared >= shortfall`);
  - `covered_by_buffer` and `still_short` split the `remaining_gap`.
- A move for a past month, or for a month within budget, prepares nothing here.
- The top-level `shortfall`, `remaining_gap`, `balance`, `covered` and `still_short` are exactly `GET /assistant/plan` `buffer_plan`. `covered` is `balance >= remaining_gap`, and `still_short` is `max(0, remaining_gap - balance)`.
- `months` stops at 600 rows (`months_truncated`); the totals cover every month.

`demo-over` after moving 1,500.00 for 2026-10 and 600.00 for 2026-11 (checked on `lumen_kidnee`, "today" 2026-10-29):
```json
{
  "balance": "3600.00",
  "shortfall": "3000.00",
  "remaining_gap": "900.00",
  "covered": true,
  "still_short": "0.00",
  "months": [
    {"month": "2026-10", "total": "6500.00", "budget": "5000.00", "shortfall": "1500.00", "prepared": "1500.00", "remaining_gap": "0.00", "state": "prepared", "covered_by_buffer": "0.00", "still_short": "0.00"},
    {"month": "2026-11", "total": "6500.00", "budget": "5000.00", "shortfall": "1500.00", "prepared": "600.00", "remaining_gap": "900.00", "state": "partly_prepared", "covered_by_buffer": "900.00", "still_short": "0.00"}
  ],
  "months_truncated": false
}
```
- Nothing over budget gives `"months": []`, `"shortfall": "0.00"`, `"remaining_gap": "0.00"` and `"covered": true`.
- 409 `SETTINGS_REQUIRED`.

### `POST /buffer/move-to-main`
Model: `buffer/schemas.py` (`MoveIn`, `MovedOut`). The user moves buffer money back to the main account. It is never blocked (L66).

Request: `{"client_request_id": "move-1", "amount": "1500.00", "for_month": "2026-10"}`
- `for_month` (Session 17) is optional, `"YYYY-MM"`: the month this money is for. Send it from "ใช้กันชนจ่ายส่วนที่เกิน" (prefilled with the month's `remaining_gap`); leave it out, or send `null`, for a free move ("ย้ายกลับบัญชีหลัก").
- It is a label only: any valid month is accepted, and it never limits or blocks the move (L66).

Response 201, or 200 with `"status": "duplicate"` for a repeat:
```json
{"transaction_id": "82f9f2ba-8e4f-4a96-bca5-36395bd64cea", "status": "created", "amount": "1500.00", "for_month": "2026-10", "balance": "4200.00"}
```
- `for_month` is `null` for a free move.

Errors:
- An amount above the buffer: `422 {"detail": {"code": "AMOUNT_ABOVE_BALANCE", "message": "the buffer holds less than this amount"}}`.
- A bad month (`"2026-13"`, `"2026-1"`, `"2026-11-01"`, a number): `422 {"detail": [{"type": "value_error", "loc": ["for_month"]}]}`.
- The same id with another amount or another `for_month` (also one added or dropped): `409 {"detail": "client_request_id reused with another amount or month"}`. A double tap with the same body is the 200 duplicate, so the money moves once.

## Home: "ควรรวมหนี้ไหม" and the monthly plan (L69, L70)
### `GET /assistant/plan`
Model: `assistant/schemas.py` (`PlanOut`). It writes nothing; the UI never calls `POST /consolidation/requests` (FEATURE FREEZE).
```json
{
  "months": [
    {"month": "2026-11", "total": "3500.00", "budget": "5000.00", "over_budget": false, "headroom": "1500.00"}
  ],
  "months_truncated": false,
  "back_in_budget_month": null,
  "pause_until": null,
  "safe_new_monthly": "1500.00",
  "safe_new_from": "2026-11",
  "safe_new_months": 12,
  "buffer_plan": {"shortfall": "0.00", "remaining_gap": "0.00", "balance": "2700.00", "covered": true, "still_short": "0.00"},
  "consolidation": {"eligible": false, "reason": "NOT_NEEDED", "estimate": null}
}
```
- `months` is shortened: it runs to 2027-07.
- `consolidation.reason` is one of:
  - `NOT_NEEDED`
  - `OVERDUE_DEBT`
  - `DISPUTED_DEBT`
  - `ESTIMATE_TOO_LARGE`
  - `PAYMENT_ABOVE_BUDGET`
  - `PAYMENT_ABOVE_ONE_THIRD_OF_INCOME`
  - `ELIGIBLE`
- When eligible, `estimate` holds `principal`, `annual_rate`, `rate_is_example: true`, `rate_note: "example, not a real rate"`, `term_months`, `first_due_month`, `monthly_payment`, `total_cost`, `current_remaining_total`, `extra_cost`, `current_monthly_total` and `monthly_reduction`.
- `current_monthly_total` (Session 17) is what the plans cost this month: the current month's total, the same as the first row of `GET /debts/months` (Home's hero). It is not `GET /debts/summary` `monthly_total` (L43), which also holds plans not due this month, for example one that starts later.
- `monthly_reduction` (Session 17) is `max(0, current_monthly_total - monthly_payment)`. It is `"0.00"` when the loan costs as much as this month or more, which can happen when the run over budget comes later; the card then leaves out its benefit line. Show both figures as sent; never compute them. `demo-consolidate` on 2026-10-29: `"current_monthly_total": "7500.00"`, `"monthly_payment": "3369.88"`, `"monthly_reduction": "4130.12"`.
- `buffer_plan.remaining_gap` (Session 17): see `GET /buffer/shortfalls`.
- 409 `SETTINGS_REQUIRED`.

### `GET /assistant/summary` (new, Session 18)
Model: `assistant/schemas.py` (`SummaryOut`); service `assistant/summary.py`. Home's "ผู้ช่วย KidNee สรุปให้ฟัง" card. It writes nothing.
```json
{
  "text": "เดือน พ.ย. 2569 ค่างวดรวม 3,500.00 บาท อยู่ในงบ 5,000.00 บาท\nทุกเดือนอยู่ในงบ\nกันชนตอนนี้ 2,700.00 บาท",
  "source": "fallback",
  "reason": "no_key"
}
```
- `demo-mon` on 2026-11-10 without a key. `text` is one point per line, at most 4 lines; show it as sent, the same way for both sources.
- `source` is `ai` (the model's words passed the grounding check) or `fallback` (the app's own template from the same numbers).
- `reason` is one of:
  - `ok` (only with `source: "ai"`)
  - `no_key`: `LLM_API_KEY` is not set, or `LLM_PROVIDER` names another provider; the model is never called
  - `timeout`: no answer within the 8 s timeout
  - `api_error`: any other API error, a refusal, a cut-off or an empty answer
  - `grounding_failed`: the model's text had a number or month not in its input, a dash, a banned phrase, or broke a wording rule
- The model (Claude Haiku, `LLM_MODEL_PLANNER`, default `claude-haiku-5-5`) gets only numbers, months and flags the plan already computed: no item names, app names or other text the user typed. One call per change of those numbers per user (an in-memory cache keyed by their hash, the prompt version and the model); no retries.
- `demo-over` (2026-11-10, no key): `"text": "เดือน พ.ย. 2569 ค่างวดรวม 6,500.00 บาท เกินงบ 1,500.00 บาท\nมี 2 เดือนที่ค่างวดเกินงบ ตั้งแต่ พ.ย. 2569 ถึง ธ.ค. 2569 กลับมาอยู่ในงบเดือน ม.ค. 2570\nกันชน 5,700.00 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด\nตอนนี้ยังไม่ควรผ่อนเพิ่ม"`.
- `demo-consolidate` (2026-11-10, no key): `"text": "เดือน พ.ย. 2569 ค่างวดรวม 7,500.00 บาท เกินงบ 2,500.00 บาท\nมี 9 เดือนที่ค่างวดเกินงบ ตั้งแต่ พ.ย. 2569 ถึง ก.ค. 2570 กลับมาอยู่ในงบเดือน ส.ค. 2570 บางเดือนค่างวดรวมเกิน 1 ใน 3 ของรายได้ ซึ่ง ธปท. แนะนำว่าไม่ควรเกิน\nกันชน 1,500.00 บาท ยังขาดอีก 9,000.00 บาท\nถ้ารวมหนี้ ค่างวดอาจลดลงเดือนละ 4,130.12 บาท ถ้าสนใจ ธนาคารจะติดต่อกลับเพื่อพิจารณา"`.
- 401 without `X-Demo-User`; 409 `SETTINGS_REQUIRED`. Never a 5xx for a model problem: every one of them is a `fallback`.

## Notifications
### `GET /notifications` (new)
Model: `notifications/router.py` (`NotificationsOut`). The user's alerts, newest first (`created_at`, then `id`), at most the 100 newest; `count` is how many the user has in all. There is no read or unread state. `title` and `body` are the Thai text stored by `notifications/copy.py`; show them as they are.
```json
{
  "notifications": [
    {
      "id": "755a133e-dda8-40e4-9d7c-c0ed62dd016d",
      "kind": "payday_shortfall",
      "title": "เดือนนี้ค่างวดเกินงบ",
      "body": "เดือน พ.ย. 2569 ค่างวดรวม 6,500 บาท เกินงบ 1,500 บาท คุณมีกันชน 5,200 บาท ย้ายมาช่วยจ่ายได้",
      "installment_id": null,
      "created_at": "2026-11-25T02:00:00Z"
    },
    {
      "id": "ff7610d3-422b-495e-aabe-e24868eeca7c",
      "kind": "new_debt",
      "title": "บันทึกรายการผ่อนแล้ว",
      "body": "ตู้เย็น ราคา 15,000 บาท ผ่อน 10 เดือน เดือนละ 1,500 บาท ยอดผ่อนรวมต่อเดือนตอนนี้ 3,500 บาท",
      "installment_id": "3cc1d482-8891-4727-9ba7-2314e3f0291b",
      "created_at": "2026-10-28T07:23:38.129584Z"
    }
  ],
  "count": 2
}
```
- `kind` is one of `new_debt`, `cash_withdrawal`, `cash_loan`, `over_cap`, `payday_shortfall`, `leftover_saved` or `consolidation_loan`.
- `installment_id` is null for payday alerts.
- An empty inbox is `{"notifications": [], "count": 0}`.
- The first alert's `created_at` was edited for the example: in the capture, every alert came from one transaction and shared one timestamp.

## Demo panel
### `POST /demo/payday` (only when `DEMO_ENDPOINTS_ENABLED=true`; otherwise 404)
Request: `{"month": "2026-11"}`. The response is 201 for the month's first run, or 200 with the stored outcome afterwards:
```json
{"month": "2026-11", "status": "created", "outcome": "over_budget", "month_total": "6500.00", "budget": "5000.00", "amount": "1500.00", "buffer_balance": "5200.00"}
```
- `outcome` is one of `over_budget`, `leftover_saved`, `no_leftover`, `leftover_off` or `safety_net`.
- 409 `SETTINGS_REQUIRED`.

### The seeded personas (`X-Demo-User`, `lumen_kidnee` only)
`python -m demo.kidnee reset --yes` rebuilds them; months are relative to today. All have income 20,000.00, payday 25 and budget 5,000.00.

| Persona | Story | Saving rule | Buffer after seeding |
|---|---|---|---|
| `demo-mon` ("ม่อน") | In budget: 3,500.00 a month | 10% | 2,700.00 |
| `demo-over` | 6,500.00 this month and next (3,000.00 over), then within budget; `NOT_NEEDED` | 10% | 5,700.00, which covers it |
| `demo-consolidate` | 9 months over budget from this month (10,500.00 in all); `ELIGIBLE` | 2% | 1,500.00, still short 9,000.00 |

Platform names are fictional ("ShopDemo", "RideDemo"); the fridge is left unnamed.

---

## How the browser reaches the API
- The frontend calls `/api/<path>` in every mode (`API_PREFIX = "/api"` in `frontend/src/api.ts`).
- **Dev** (`npm run dev`): Vite on 127.0.0.1:5173 proxies `/api` to the backend on 127.0.0.1:8000 and strips the prefix (`vite.config.ts`). `npm run dev -- --mode mock` answers every call from the in-browser mock instead.
- **Persona**: the frontend sends `X-Demo-User` for the persona chosen in the Demo panel (`demo-mon` by default).
- **One-server demo**: one server on 127.0.0.1:8000. It serves `frontend/dist` at `/`, and the unchanged API app is mounted at `/api`, so the mount strips the prefix the way the proxy does.
  - Nothing binds 0.0.0.0. There is no end-user auth (L60 1).
  - The screens use hash routes (`#/months`), so no history fallback is needed.
  - The command is in README.md, added with the `feat/kidnee-demo-serving` PR.
- The backend's own routes stay at the root (`/debts/months`, not `/api/debts/months`), so tests, curl and `app.main:app` are unchanged.
