"""Thai copy for new-debt alerts (L43, L50; rule 10: no em dashes).

The wording is fixed by the user (Session 9; the manual-entry copy in Session 12).
03 section 4 has an older example without the L43 monthly total and without a
cash version.
"""

from dataclasses import dataclass
from decimal import Decimal

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
