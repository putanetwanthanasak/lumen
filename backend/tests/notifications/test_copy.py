"""Thai alert copy (L43, L50, rule 10) and money formatting. No database."""

from decimal import Decimal

import pytest

from app.affordability.months import Month
from app.models import InstallmentKind, NotificationKind
from app.notifications.copy import (
    LEFTOVER_BODY,
    LEFTOVER_TITLE,
    MANUAL_BODY,
    MANUAL_TITLES,
    SHORTFALL_BODY,
    SHORTFALL_BODY_NO_BUFFER,
    SHORTFALL_TITLE,
    TEMPLATES,
    THAI_MONTHS,
    format_baht,
    leftover_saved_alert,
    manual_entry_alert,
    new_debt_alert,
    payday_shortfall_alert,
    thai_month,
)
from app.rules.config import load_rules

# Every kind a webhook or a manual entry can carry. A consolidation loan comes only
# from an approved consolidation (CO-05) and has its own alert (L72).
RECORDABLE_KINDS = set(InstallmentKind) - {InstallmentKind.CONSOLIDATION_LOAN}


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


def test_NT_01_every_recordable_kind_has_a_template_and_strong_kinds_are_not_plain() -> None:
    assert set(TEMPLATES) == RECORDABLE_KINDS
    # The loan is never recorded through a webhook or a manual entry (CO-05), so it
    # has no new-debt template; its approval brings its own alert (L72).
    assert InstallmentKind.CONSOLIDATION_LOAN not in TEMPLATES
    for kind in load_rules().alerts.strong_alert_kinds:
        assert TEMPLATES[kind].kind != NotificationKind.NEW_DEBT


def test_rule_10_no_em_dash_and_rule_5_no_bank_brand_in_copy() -> None:
    em_dash = chr(0x2014)  # spelled out, so this file has none either
    # The names built from parts, so this file does not hold them (AI-14's scan).
    parts = [
        ("kb", "ank"),
        ("kb", "tg"),
        ("kasi", "korn"),
        ("k ", "plus"),
        ("kp", "lus"),
        ("sho", "pee"),
    ]
    banned = (em_dash, *(a + b for a, b in parts), "กสิ" + "กร")
    copy = [f"{t.title} {t.body}" for t in TEMPLATES.values()]
    copy += [*MANUAL_TITLES.values(), MANUAL_BODY]
    copy += [SHORTFALL_TITLE, SHORTFALL_BODY, SHORTFALL_BODY_NO_BUFFER]
    copy += [LEFTOVER_TITLE, LEFTOVER_BODY, *THAI_MONTHS]
    for text in copy:
        assert not [word for word in banned if word in text.lower()]


def test_MI_08_manual_entry_copy_exact() -> None:
    # Session 12 wording (L62, L43): no vendor and no "if this isn't you" line.
    kind, title, body = manual_entry_alert(
        kind=InstallmentKind.PURCHASE,
        item_name="หูฟัง",
        item_price=Decimal("1200.00"),
        months=10,
        monthly_amount=Decimal("130.00"),
        monthly_total=Decimal("4583.33"),
    )
    assert (kind, title) == (NotificationKind.NEW_DEBT, "บันทึกรายการผ่อนแล้ว")
    assert body == (
        "หูฟัง ราคา 1,200 บาท ผ่อน 10 เดือน เดือนละ 130 บาท ยอดผ่อนรวมต่อเดือนตอนนี้ 4,583.33 บาท"
    )


def test_MI_08_manual_entry_copy_without_item_name_starts_with_price() -> None:
    _, _, body = manual_entry_alert(
        kind=InstallmentKind.PURCHASE,
        item_name="",
        item_price=Decimal("999.50"),
        months=3,
        monthly_amount=Decimal("333.17"),
        monthly_total=Decimal("333.17"),
    )
    assert body == ("ราคา 999.50 บาท ผ่อน 3 เดือน เดือนละ 333.17 บาท ยอดผ่อนรวมต่อเดือนตอนนี้ 333.17 บาท")


@pytest.mark.parametrize(
    ("kind", "notification_kind", "title"),
    [
        (InstallmentKind.CASH_WITHDRAWAL, NotificationKind.CASH_WITHDRAWAL, "บันทึกการเบิกเงินสดแล้ว"),
        (InstallmentKind.CASH_LOAN, NotificationKind.CASH_LOAN, "บันทึกการกู้เงินสดแล้ว"),
    ],
)
def test_MI_08_manual_cash_entry_titles(
    kind: InstallmentKind, notification_kind: NotificationKind, title: str
) -> None:
    result = manual_entry_alert(
        kind=kind,
        item_name="",
        item_price=Decimal("5000.00"),
        months=5,
        monthly_amount=Decimal("1100.00"),
        monthly_total=Decimal("1100.00"),
    )
    assert result[:2] == (notification_kind, title)
    assert set(MANUAL_TITLES) == RECORDABLE_KINDS


# --- Payday copy (L67, Session 13 wording) ----------------------------------------------


def month(year: int, number: int) -> Month:
    return Month(year * 12 + number - 1)


@pytest.mark.parametrize(
    ("year", "number", "text"),
    [
        (2026, 1, "ม.ค. 2569"),
        (2026, 4, "เม.ย. 2569"),
        (2026, 11, "พ.ย. 2569"),
        (2026, 12, "ธ.ค. 2569"),
        (2027, 1, "ม.ค. 2570"),  # the year boundary: Buddhist era moves with it
        (2027, 2, "ก.พ. 2570"),
    ],
)
def test_PD_09_thai_short_month_with_buddhist_era_year(year: int, number: int, text: str) -> None:
    assert thai_month(month(year, number)) == text


def test_PD_09_thai_month_table_has_twelve_distinct_names() -> None:
    assert len(THAI_MONTHS) == len(set(THAI_MONTHS)) == 12
    assert THAI_MONTHS[0] == "ม.ค."
    assert THAI_MONTHS[11] == "ธ.ค."


def test_PD_01_shortfall_copy_exact() -> None:
    kind, title, body = payday_shortfall_alert(
        month=month(2026, 11),
        total=Decimal("10500.00"),
        shortfall=Decimal("1500.00"),
        buffer=Decimal("820.50"),
    )
    assert kind == NotificationKind.PAYDAY_SHORTFALL
    assert title == "เดือนนี้ค่างวดเกินงบ"
    assert body == (
        "เดือน พ.ย. 2569 ค่างวดรวม 10,500 บาท เกินงบ 1,500 บาท คุณมีกันชน 820.50 บาท ย้ายมาช่วยจ่ายได้"
    )


@pytest.mark.parametrize(
    ("buffer", "body"),
    [
        (
            Decimal("0.00"),
            "เดือน พ.ย. 2569 ค่างวดรวม 10,500 บาท เกินงบ 1,500 บาท "
            "ลองดูภาระผ่อนรายเดือนว่าจะกลับมาอยู่ในงบเมื่อไร",
        ),
        (
            Decimal("0.01"),  # any buffer at all: the move-the-buffer wording
            "เดือน พ.ย. 2569 ค่างวดรวม 10,500 บาท เกินงบ 1,500 บาท คุณมีกันชน 0.01 บาท ย้ายมาช่วยจ่ายได้",
        ),
    ],
    ids=["empty_buffer", "one_satang"],
)
def test_PD_01_shortfall_copy_depends_on_the_buffer(buffer: Decimal, body: str) -> None:
    kind, title, text = payday_shortfall_alert(
        month=month(2026, 11),
        total=Decimal("10500.00"),
        shortfall=Decimal("1500.00"),
        buffer=buffer,
    )
    assert (kind, title, text) == (NotificationKind.PAYDAY_SHORTFALL, "เดือนนี้ค่างวดเกินงบ", body)


def test_LO_01_leftover_copy_exact() -> None:
    kind, title, body = leftover_saved_alert(
        month=month(2026, 12), total=Decimal("7200.00"), leftover=Decimal("1800.00")
    )
    assert kind == NotificationKind.LEFTOVER_SAVED
    assert title == "ออมส่วนที่เหลือจากงบแล้ว"
    assert body == "เดือน ธ.ค. 2569 ค่างวดรวม 7,200 บาท ต่ำกว่างบ 1,800 บาท ย้ายเข้ากันชนแล้ว"
