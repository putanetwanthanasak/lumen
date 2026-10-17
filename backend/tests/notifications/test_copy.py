"""Thai alert copy (L43, L50, rule 10) and money formatting. No database."""

from decimal import Decimal

import pytest

from app.models import InstallmentKind, NotificationKind
from app.notifications.copy import TEMPLATES, format_baht, new_debt_alert
from app.rules.config import load_rules


@pytest.mark.parametrize(
    ("amount", "text"),
    [
        ("0.01", "0.01"),
        ("0.00", "0"),
        ("10.00", "10"),
        ("10", "10"),
        ("999.90", "999.90"),
        ("1000.00", "1,000"),
        ("1234.50", "1,234.50"),
        ("20000.00", "20,000"),
        ("4583.33", "4,583.33"),
        ("1000000.05", "1,000,000.05"),
        ("9999999999.99", "9,999,999,999.99"),  # the largest Numeric(12,2)
    ],
)
def test_format_baht_commas_and_satang_only_when_needed(amount: str, text: str) -> None:
    assert format_baht(Decimal(amount)) == text


def test_new_debt_copy_exact() -> None:
    kind, title, body = new_debt_alert(
        kind=InstallmentKind.PURCHASE,
        vendor="shopdemo",
        amount=Decimal("20000.00"),
        months=6,
        monthly_total=Decimal("4583.33"),
    )
    assert (kind, title) == (NotificationKind.NEW_DEBT, "รายการผ่อนใหม่")
    assert body == (
        "มีรายการผ่อนใหม่จาก ShopDemo 20,000 บาท ผ่อน 6 เดือน "
        "ยอดผ่อนรวมต่อเดือนตอนนี้ 4,583.33 บาท ถ้าไม่ใช่คุณ แตะเพื่อแจ้ง"
    )


@pytest.mark.parametrize(
    ("kind", "expected_kind", "title", "body"),
    [
        (
            InstallmentKind.CASH_WITHDRAWAL,
            NotificationKind.CASH_WITHDRAWAL,
            "แจ้งเตือนเบิกเงินสด",
            "มีการเบิกเงินสด 5,000 บาท จาก ShopDemo ถ้าไม่ใช่คุณ แจ้งได้ทันที "
            "ยอดผ่อนรวมต่อเดือนตอนนี้ 1,250.50 บาท",
        ),
        (
            InstallmentKind.CASH_LOAN,
            NotificationKind.CASH_LOAN,
            "แจ้งเตือนกู้เงินสด",
            "มีการกู้เงินสด 5,000 บาท จาก ShopDemo ถ้าไม่ใช่คุณ แจ้งได้ทันที ยอดผ่อนรวมต่อเดือนตอนนี้ 1,250.50 บาท",
        ),
    ],
)
def test_L50_SV_03a_cash_kinds_get_the_strong_alert(
    kind: InstallmentKind, expected_kind: NotificationKind, title: str, body: str
) -> None:
    assert kind in load_rules().alerts.strong_alert_kinds
    assert new_debt_alert(
        kind=kind,
        vendor="shopdemo",
        amount=Decimal("5000.00"),
        months=4,
        monthly_total=Decimal("1250.50"),
    ) == (expected_kind, title, body)


def test_unknown_vendor_shown_by_its_id() -> None:
    _, _, body = new_debt_alert(
        kind=InstallmentKind.PURCHASE,
        vendor="othervendor",
        amount=Decimal("1.00"),
        months=1,
        monthly_total=Decimal("1.00"),
    )
    assert "จาก othervendor 1 บาท" in body


def test_every_kind_has_a_template_and_every_strong_kind_is_not_plain_new_debt() -> None:
    assert set(TEMPLATES) == set(InstallmentKind)
    for kind in load_rules().alerts.strong_alert_kinds:
        assert TEMPLATES[kind].kind != NotificationKind.NEW_DEBT


def test_rule_10_no_em_dash_and_rule_5_no_bank_brand_in_copy() -> None:
    em_dash = chr(0x2014)  # spelled out, so this file has none either
    banned = (em_dash, "kbank", "kbtg", "kasikorn", "k plus", "kplus", "shopee", "กสิกร")
    for template in TEMPLATES.values():
        text = f"{template.title} {template.body}".lower()
        assert not [word for word in banned if word in text]
