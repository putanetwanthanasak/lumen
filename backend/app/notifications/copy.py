"""Thai copy for new-debt alerts (L43, L50; rule 10: no em dashes).

The wording is fixed by the user (Session 9). 03 section 4 has an older example
without the L43 monthly total and without a cash version.
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
