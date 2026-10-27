"""Thai copy for alerts: new debt (L43, L50) and payday (L67). Rule 10: no em dashes.

The wording is fixed by the user (Session 9; the manual-entry copy in Session 12).
03 section 4 has an older example without the L43 monthly total and without a
cash version.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.affordability.months import Month
from app.models import InstallmentKind, NotificationKind

CENT = Decimal("0.01")

# Display names for vendor ids. An unknown vendor is shown by its id.
VENDOR_NAMES = {"shopdemo": "ShopDemo"}


def format_baht(amount: Decimal) -> str:
    """20000.00 -> "20,000"; 1234.5 -> "1,234.50". Exact: Decimal formatting, no float."""
    cents = amount.quantize(CENT)
    places = 0 if cents == cents.to_integral_value() else 2
    return f"{cents:,.{places}f}"


def vendor_name(vendor: str) -> str:
    return VENDOR_NAMES.get(vendor, vendor)


@dataclass(frozen=True)
class Template:
    kind: NotificationKind
    title: str
    body: str


TEMPLATES = {
    InstallmentKind.PURCHASE: Template(
        NotificationKind.NEW_DEBT,
        "รายการผ่อนใหม่",
        "มีรายการผ่อนใหม่จาก {vendor} {amount} บาท ผ่อน {months} เดือน "
        "ยอดผ่อนรวมต่อเดือนตอนนี้ {monthly_total} บาท ถ้าไม่ใช่คุณ แตะเพื่อแจ้ง",
    ),
    # The strong alerts (L50, 05 SV-03a).
    InstallmentKind.CASH_WITHDRAWAL: Template(
        NotificationKind.CASH_WITHDRAWAL,
        "แจ้งเตือนเบิกเงินสด",
        "มีการเบิกเงินสด {amount} บาท จาก {vendor} ถ้าไม่ใช่คุณ แจ้งได้ทันที "
        "ยอดผ่อนรวมต่อเดือนตอนนี้ {monthly_total} บาท",
    ),
    InstallmentKind.CASH_LOAN: Template(
        NotificationKind.CASH_LOAN,
        "แจ้งเตือนกู้เงินสด",
        "มีการกู้เงินสด {amount} บาท จาก {vendor} ถ้าไม่ใช่คุณ แจ้งได้ทันที "
        "ยอดผ่อนรวมต่อเดือนตอนนี้ {monthly_total} บาท",
    ),
}


def new_debt_alert(
    *,
    kind: InstallmentKind,
    vendor: str,
    amount: Decimal,
    months: int,
    monthly_total: Decimal,
) -> tuple[NotificationKind, str, str]:
    """(notification kind, title, body). The vendor's display name is trusted config;
    no free text from the webhook (such as item_name) goes into the copy."""
    template = TEMPLATES[kind]
    body = template.body.format(
        vendor=vendor_name(vendor),
        amount=format_baht(amount),
        months=months,
        monthly_total=format_baht(monthly_total),
    )
    return template.kind, template.title, body


# L62: the user recorded this installment themselves, so there is no vendor and no
# "if this isn't you" line. Titles per kind; one body (Session 12 wording).
MANUAL_TITLES = {
    InstallmentKind.PURCHASE: "บันทึกรายการผ่อนแล้ว",
    InstallmentKind.CASH_WITHDRAWAL: "บันทึกการเบิกเงินสดแล้ว",
    InstallmentKind.CASH_LOAN: "บันทึกการกู้เงินสดแล้ว",
}
MANUAL_BODY = (
    "ราคา {item_price} บาท ผ่อน {months} เดือน เดือนละ {monthly_amount} บาท "
    "ยอดผ่อนรวมต่อเดือนตอนนี้ {monthly_total} บาท"
)


def manual_entry_alert(
    *,
    kind: InstallmentKind,
    item_name: str,
    item_price: Decimal,
    months: int,
    monthly_amount: Decimal,
    monthly_total: Decimal,
) -> tuple[NotificationKind, str, str]:
    """(notification kind, title, body) for an installment the user recorded. The
    item name is the user's own text (no control characters, by the schema); when it
    is empty the body starts with "ราคา"."""
    body = MANUAL_BODY.format(
        item_price=format_baht(item_price),
        months=months,
        monthly_amount=format_baht(monthly_amount),
        monthly_total=format_baht(monthly_total),
    )
    if item_name:
        body = f"{item_name} {body}"
    return TEMPLATES[kind].kind, MANUAL_TITLES[kind], body


# Thai short month names, January first; the year is shown in the Buddhist era
# (Session 13, open question 6): November 2026 is "พ.ย. 2569".
THAI_MONTHS = (
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
)
BUDDHIST_ERA_OFFSET = 543


def thai_month(month: Month) -> str:
    return f"{THAI_MONTHS[month.month - 1]} {month.year + BUDDHIST_ERA_OFFSET}"


# L67, the user's wording (Session 13).
SHORTFALL_TITLE = "เดือนนี้ค่างวดเกินงบ"
SHORTFALL_BODY = (
    "เดือน {month} ค่างวดรวม {total} บาท เกินงบ {shortfall} บาท คุณมีกันชน {buffer} บาท ย้ายมาช่วยจ่ายได้"
)
# With an empty buffer there is nothing to move, so point to the payoff assistant
# instead (the user's wording, Session 13 review round 2 F4).
SHORTFALL_BODY_NO_BUFFER = (
    "เดือน {month} ค่างวดรวม {total} บาท เกินงบ {shortfall} บาท ลองเปิดผู้ช่วยปลดหนี้เพื่อดูแผนได้"
)
LEFTOVER_TITLE = "ออมส่วนที่เหลือจากงบแล้ว"
LEFTOVER_BODY = "เดือน {month} ค่างวดรวม {total} บาท ต่ำกว่างบ {leftover} บาท ย้ายเข้ากันชนแล้ว"


def payday_shortfall_alert(
    *, month: Month, total: Decimal, shortfall: Decimal, buffer: Decimal
) -> tuple[NotificationKind, str, str]:
    template = SHORTFALL_BODY if buffer > 0 else SHORTFALL_BODY_NO_BUFFER
    body = template.format(
        month=thai_month(month),
        total=format_baht(total),
        shortfall=format_baht(shortfall),
        buffer=format_baht(buffer),
    )
    return NotificationKind.PAYDAY_SHORTFALL, SHORTFALL_TITLE, body


def leftover_saved_alert(
    *, month: Month, total: Decimal, leftover: Decimal
) -> tuple[NotificationKind, str, str]:
    body = LEFTOVER_BODY.format(
        month=thai_month(month), total=format_baht(total), leftover=format_baht(leftover)
    )
    return NotificationKind.LEFTOVER_SAVED, LEFTOVER_TITLE, body


# L72, the user's wording (Session 14): the monthly payment and the total cost are
# always shown together, with the monthly total now (L43).
CONSOLIDATION_TITLE = "อนุมัติสินเชื่อรวมหนี้แล้ว"
CONSOLIDATION_BODY = (
    "ผ่อนเดือนละ {payment} บาท {term} เดือน ยอดรวมทั้งหมด {total_cost} บาท "
    "ค่างวดรวมต่อเดือนตอนนี้ {monthly_total} บาท"
)


def consolidation_loan_alert(
    *, payment: Decimal, term: int, total_cost: Decimal, monthly_total: Decimal
) -> tuple[NotificationKind, str, str]:
    body = CONSOLIDATION_BODY.format(
        payment=format_baht(payment),
        term=term,
        total_cost=format_baht(total_cost),
        monthly_total=format_baht(monthly_total),
    )
    return NotificationKind.CONSOLIDATION_LOAN, CONSOLIDATION_TITLE, body
