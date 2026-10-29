"""AI-10 to AI-14, AI-19 and AI-30: the grounding check on the model's text (app.ai.grounding).
Pure: no database, no model. Every number and month in the text must be an input
value, in any format the screens display; the wording rules hold; anything else is
refused, so the caller shows the fallback."""

import re
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.affordability.months import Month
from app.ai.grounding import (
    BANNED,
    THAI_MONTH_NAMES,
    THAI_MONTH_SHORT,
    THAI_MONTH_UNDOTTED,
    Allowed,
    Check,
    MonthMention,
    check,
    extract,
)
from app.notifications.copy import THAI_MONTHS

OCT_2026 = Month(2026 * 12 + 9)
NOV_2026 = OCT_2026.plus(1)
DEC_2026 = OCT_2026.plus(2)
THAI_DIGITS = str.maketrans("0123456789", "๐๑๒๓๔๕๖๗๘๙")


def allowed(
    *numbers: str,
    counts: tuple[int, ...] = (),
    months: tuple[Month, ...] = (OCT_2026,),
    over_by: tuple[str, ...] = (),
    reductions: tuple[str, ...] = (),
    offered: bool = False,
    over_now: bool = False,
    any_over: bool = False,
    red: bool = False,
) -> Allowed:
    return Allowed(
        numbers=frozenset(Decimal(n) for n in (*numbers, *over_by, *reductions)),
        counts=frozenset(Decimal(c) for c in counts),
        months=frozenset(months),
        over_by=frozenset(Decimal(n) for n in over_by),
        reductions=frozenset(Decimal(n) for n in reductions),
        consolidation_offered=offered,
        over_now=over_now,
        any_over=any_over,
        above_one_third=red,
    )


# This month in budget, 2 months over later (from Nov), back in budget in Dec.
BASE = allowed(
    "3500.00",
    "5000.00",
    "1500.00",
    counts=(2,),
    months=(OCT_2026, NOV_2026, DEC_2026),
    any_over=True,
)
# Over budget from this month (Oct) by 1,500.00; the bank's option offered.
OVER_NOW = allowed(
    "6500.00",
    "5000.00",
    counts=(2,),
    months=(OCT_2026, NOV_2026, DEC_2026),
    over_by=("1500.00",),
    reductions=("4130.12",),
    offered=True,
    over_now=True,
    any_over=True,
)
# Every month in budget.
ALL_IN = allowed("3500.00", "5000.00", counts=(0,), months=(OCT_2026,))
# Brand names (rule 5), built from parts so this file does not hold them either.
BRANDS = [
    a + b
    for a, b in (
        ("กสิ", "กร"),
        ("K", "Bank"),
        ("KB", "TG"),
        ("Kasi", "korn"),
        ("Sho", "pee"),
        ("K ", "PLUS"),
        ("K", "PLUS"),
        ("ช้อป", "ปี้"),
        ("ช็อป", "ปี้"),
        ("เคแบ", "งก์"),
        ("เคพ", "ลัส"),
    )
]
GOOD = (
    "เดือน ต.ค. 2569 ค่างวดรวม 3,500.00 บาท อยู่ในงบ 5,000.00 บาท\n"
    "มี 2 เดือนที่ค่างวดเกินงบ กลับมาอยู่ในงบเดือน ธ.ค. 2569\n"
    "ผู้ช่วย KidNee แนะนำให้เตรียมกันชนไว้ 1,500.00 บาท"
)


def failed(text: str, allow: Allowed = BASE) -> Check | None:
    found = check(text, allow)
    return None if found is None else found.check


# --- AI-10: grounded text passes -----------------------------------------------------


def test_AI_10_grounded_text_passes() -> None:
    assert check(GOOD, BASE) is None


@pytest.mark.parametrize(
    "text",
    [
        "ค่างวดรวม 3,500 บาท",  # the alerts' format: no satang on a whole amount
        "ค่างวด 3500.00 บาท",
        "ค่างวด 3500 บาท",
        "ค่างวด๓,๕๐๐.๐๐บาท",  # Thai digits, no spaces
        "เดือนตุลาคม 2569 ถึงเดือน พ.ย. พ.ศ. 2569",  # a full name, and พ.ศ.
        "ตั้งแต่ ต.ค. ปีนี้",  # a month without a year: its month is in the input
        "ปี 2569",  # a Buddhist year of an input month
        "มี 2 เดือนที่เกินงบ",  # a count, as "N เดือน"
        "เดือนตุลา 2569 ถึง ธ.ค 2569",  # a short name, and no last dot
        "ภาพรวมหนี้ของคุณดูได้ที่หน้าหลัก",  # the debt overview, not consolidation
    ],
)
def test_AI_10_every_display_format_of_an_input_value_passes(text: str) -> None:
    assert check(text, BASE) is None, check(text, BASE)


def test_AI_10_consolidation_as_an_option_the_bank_considers_passes() -> None:
    text = "ถ้าสนใจรวมหนี้ ธนาคารจะติดต่อกลับเพื่อพิจารณา"
    assert check(text, allowed(offered=True)) is None


# --- AI-11, AI-12: a number or month not in the input --------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "ค่างวดรวม 3,600.00 บาท",  # wrong by 100
        "ค่างวดรวม 3,500.01 บาท",  # wrong by a satang
        "ค่างวดรวม 350.00 บาท",
        "ค่างวด๓,๖๐๐บาท",  # Thai digits, wrong
    ],
)
def test_AI_11_a_wrong_number_is_refused(text: str) -> None:
    assert failed(text) is Check.NUMBER_NOT_IN_INPUT


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("ค่างวดรวม 3,500.00 บาท คิดเป็น 10%", Check.NUMBER_NOT_IN_INPUT),
        ("ค่างวดรวม 3,500.00 บาท มี 3 เดือนที่เกินงบ", Check.NUMBER_NOT_IN_INPUT),
        ("กันชนตอนนี้ 2.00 บาท", Check.NUMBER_NOT_IN_INPUT),  # a count, as an amount
        ("กันชนตอนนี้ 2 บาท", Check.NUMBER_NOT_IN_INPUT),  # a count, not before เดือน
        ("ยอด 2,569.00 บาท", Check.NUMBER_NOT_IN_INPUT),  # a year, as an amount
        ("ยอด 2,569 บาท", Check.NUMBER_NOT_IN_INPUT),
        ("ยอด 2569 บาท", Check.NUMBER_NOT_IN_INPUT),  # a year only after ปี or พ.ศ.
        ("กลับมาอยู่ในงบเดือนกุมภา 2570", Check.MONTH_NOT_IN_INPUT),  # short names
        ("ถึง มกรา 2570", Check.MONTH_NOT_IN_INPUT),
        ("ถึง ม.ค 2570", Check.MONTH_NOT_IN_INPUT),
        ("เดือนมีนา", Check.MONTH_NOT_IN_INPUT),
        ("มีเดือนเดียวที่ค่างวดเกินงบ คือ พ.ย. 2569", Check.NUMBER_IN_WORDS),
        ("ตอนนี้ผ่อนอยู่สามรายการ", Check.NUMBER_IN_WORDS),
        ("สูงกว่างบเกือบสองเท่า", Check.NUMBER_IN_WORDS),
        ("เหลือที่ว่างอีกพันห้าร้อย", Check.NUMBER_IN_WORDS),
        ("ลดลงได้ร้อยละสิบ", Check.NUMBER_IN_WORDS),
        ("ผ่อน 12 งวด", Check.NUMBER_NOT_IN_INPUT),
        ("ส่วนต่าง -1,500.00 บาท", Check.NUMBER_NOT_IN_INPUT),  # negative: never an input
        ("เดือน ม.ค. 2570", Check.MONTH_NOT_IN_INPUT),
        ("เดือนมีนาคม", Check.MONTH_NOT_IN_INPUT),  # no year, and no March in the input
        ("ต.ค. 2026", Check.MONTH_NOT_IN_INPUT),  # we display the Buddhist year
        ("ต.ค. 69", Check.NUMBER_NOT_IN_INPUT),  # a short year is not our format
        ("ปี 2570", Check.NUMBER_NOT_IN_INPUT),  # no input month in 2570
        ("ยอด 35,00 บาท", Check.MALFORMED_NUMBER),  # commas not in groups of three
        ("ยอด 3500² บาท", Check.STRAY_NUMERAL),
        ("ยอดครึ่งหนึ่งของงบ", Check.NUMBER_IN_WORDS),
        ("เกินงบสองเดือน", Check.NUMBER_IN_WORDS),
        ("ค่างวดสามพันห้าร้อยบาท", Check.NUMBER_IN_WORDS),
        ("ยอดหนึ่งหมื่นบาท", Check.NUMBER_IN_WORDS),
    ],
)
def test_AI_12_an_extra_number_month_or_year_is_refused(text: str, why: Check) -> None:
    assert failed(text) is why


# --- AI-13: dashes (rule 10) -----------------------------------------------------------


@pytest.mark.parametrize("dash", ["\u2014", "\u2013", "\u2015", "\u2012", "\u2e3a", "\u2e3b"])
def test_AI_13_an_em_dash_or_a_look_alike_is_refused(dash: str) -> None:
    assert failed(f"ค่างวดรวม 3,500.00 บาท {dash} อยู่ในงบ") is Check.DASH


# --- AI-14: wording rules --------------------------------------------------------------


@pytest.mark.parametrize("phrase", BANNED)
def test_AI_14_every_banned_phrase_is_refused(phrase: str) -> None:
    assert failed(f"ค่างวดรวม 3,500.00 บาท {phrase}") is Check.BANNED_PHRASE


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("แนะนำให้โปะหนี้ก้อนนี้ก่อน", Check.BANNED_PHRASE),  # L69: no prepaying
        ("ปิดยอดก่อนกำหนดได้", Check.BANNED_PHRASE),
        ("ยังผ่อนเพิ่มได้อีกเดือนละ 1,500.00 บาท", Check.BANNED_PHRASE),  # more debt
        ("กู้เงินมาจ่ายก่อนได้", Check.BANNED_PHRASE),
        ("ธนาคารอนุมัติการรวมหนี้แล้ว พิจารณาแล้ว", Check.BANNED_PHRASE),  # L71
        ("ธปท. กำหนดว่าไม่ควรเกิน 1 ใน 3 ของรายได้ ตามที่แนะนำ", Check.BANNED_PHRASE),
        (f"เปิดแอป{BRANDS[0]}เพื่อดู", Check.BANNED_PHRASE),  # rule 5
        (f"ดูใน {BRANDS[1]} ได้เลย", Check.NOT_THAI),  # rule 5, and English
        ("ลองแบ่งเงินไปลงทุน", Check.BANNED_PHRASE),  # 05 AI-06: no investing
        ("ลองปลดหนี้ก้อนเล็กก่อน", Check.BANNED_PHRASE),  # L69: no payoff order
        ("เคลียร์หนี้ให้หมดเร็ว ๆ", Check.BANNED_PHRASE),
        ("เดือน ต.ค. 2569 ค่างวดรวม 3,500.00 บาท ยังผ่อนเพิ่มอีกได้", Check.BANNED_PHRASE),
        ("ยังซื้อเพิ่มอีกได้", Check.BANNED_PHRASE),
        ("ลองรวบหนี้กับธนาคาร", Check.CONSOLIDATION_NOT_OFFERED),  # L70: a synonym
        ("ลองรีไฟแนนซ์ดู", Check.CONSOLIDATION_NOT_OFFERED),
        ("Your total is fine", Check.NOT_THAI),
        ("ค่างวด **3,500.00** บาท", Check.MARKUP),
        ("ค่างวด\u200b3,500.00 บาท", Check.CONTROL_CHARACTER),  # zero-width space
        ("ค่างวด\t3,500.00 บาท", Check.CONTROL_CHARACTER),
        ("ถ้าสนใจรวมหนี้ ธนาคารจะติดต่อกลับเพื่อพิจารณา", Check.CONSOLIDATION_NOT_OFFERED),
        ("เกินงบบ่อย ลองคุยกับธนาคาร", None),
        ("เกิน 1 ใน 3 ของรายได้", Check.ONE_THIRD_WORDING),  # without "แนะนำ"
        ("ตามเกณฑ์ของ ธปท.", Check.ONE_THIRD_WORDING),
        ("", Check.EMPTY),
        ("  \n ", Check.EMPTY),
        ("ก" * 501, Check.TOO_LONG),
        ("หนึ่ง\nสอง\nสาม\nสี่\nห้า", Check.TOO_MANY_LINES),
        ("ก\nข\nค\nง", Check.TOO_MANY_LINES),  # at most 3 sentences
        # Every amount is exact: no hedge next to one.
        ("ค่างวดอาจลดลงเดือนละ 1,500 บาท", Check.HEDGED_AMOUNT),
        ("กันชนประมาณ 1,500 บาท", Check.HEDGED_AMOUNT),
        ("เหลือราว ๆ 1,500 บาท", Check.HEDGED_AMOUNT),
        ("ค่างวดเกือบ 3,500 บาท", Check.HEDGED_AMOUNT),
        ("ค่างวด 3,500 บาทโดยประมาณ", Check.HEDGED_AMOUNT),
        ("ค่างวด ๓,๕๐๐ บาท อาจ", None),  # after the unit, and no amount after it
        ("กันชนอาจช่วยได้", None),  # no amount next to it
    ],
)
def test_AI_14_wording_rules(text: str, why: Check | None) -> None:
    assert failed(text) is why


def test_AI_14_no_brand_name_is_written_out_in_backend_code_or_tests() -> None:
    """Rule 5: the block list and the tests build the names from parts."""
    root = Path(__file__).resolve().parents[2]
    # Whole words only: "MockBankAccountProvider" is not a name.
    names = "|".join(re.escape(n).replace(r"\ ", r"\s*") for n in BRANDS)
    pattern = re.compile(f"(?<![A-Za-z])(?:{names})(?![A-Za-z])", re.I)
    hits = [
        f"{path.relative_to(root)}: {found.group(0)}"
        for folder in ("app", "demo", "tests")
        for path in sorted((root / folder).rglob("*"))
        if path.suffix in {".py", ".md", ".json", ".toml"}
        for found in pattern.finditer(path.read_text(encoding="utf-8"))
    ]
    assert hits == []


def test_AI_14_consolidation_must_say_the_bank_considers_it() -> None:
    assert failed("รวมหนี้แล้วค่างวดลดลง", allowed(offered=True)) is Check.CONSOLIDATION_WORDING


def test_AI_14_the_first_broken_rule_is_reported_with_its_token() -> None:
    found = check("โปะหนี้ 9,999.00 บาท", BASE)
    assert found is not None
    assert (found.check, found.token) == (Check.BANNED_PHRASE, "โปะ")
    found = check("ค่างวดรวม 3,600.00 บาท", BASE)
    assert found is not None
    assert (found.check, found.token) == (Check.NUMBER_NOT_IN_INPUT, "3600.00")


# --- AI-30: budget claims and labelled amounts must match the facts -----------------


@pytest.mark.parametrize(
    ("text", "allow"),
    [
        # Over budget from this month: "every month is within budget" is wrong.
        ("เดือน ต.ค. 2569 ค่างวดรวม 6,500.00 บาท\nทุกเดือนอยู่ในงบ", OVER_NOW),
        ("ค่างวดรวม 6,500.00 บาท อยู่ในงบ 5,000.00 บาท", OVER_NOW),
        ("ไม่มีเดือนไหนเกินงบ", OVER_NOW),
        ("เดือน ต.ค. 2569 ค่างวดรวม 6,500.00 บาท ยังไม่เกินงบ", OVER_NOW),
        ("ค่างวดรวม 6,500.00 บาท อยู่ภายในงบ", OVER_NOW),
        ("ทุกเดือนยังอยู่ในงบ", BASE),  # months over later
        ("ทุกเดือนไม่เกินงบ", BASE),
        ("ทุก ๆ เดือนยังอยู่ในงบ", BASE),
        ("เดือนนี้เกินงบ", BASE),  # this month is in budget
        ("ค่างวดรวม 3,500.00 บาท เกินงบ", ALL_IN),  # nothing is over budget
        (
            "ค่างวดทุกเดือนไม่เกิน 1 ใน 3 ของรายได้ ตามที่ ธปท. แนะนำ",
            replace(BASE, above_one_third=True),  # RED: some month is above a third
        ),
        # A real amount with the wrong label.
        ("เกินงบ 5,000.00 บาท", OVER_NOW),  # the budget, not the amount over it
        ("เกินงบ 2 เดือน", allowed("5000.00", counts=(3,), any_over=True)),  # not the count
        (
            "ถ้าสนใจรวมหนี้ ค่างวดจะลดลงเดือนละ 1,500.00 บาท ธนาคารจะติดต่อกลับเพื่อพิจารณา",
            OVER_NOW,  # 1,500.00 is the amount over budget, not the reduction
        ),
        ("ค่างวดลดลง 3,500.00 บาท", BASE),  # no reduction in the facts
    ],
)
def test_AI_30_a_claim_the_facts_do_not_support_is_refused(text: str, allow: Allowed) -> None:
    assert failed(text, allow) is Check.CLAIM_NOT_IN_INPUT


@pytest.mark.parametrize(
    ("text", "allow"),
    [
        (
            "เดือน ต.ค. 2569 ค่างวดรวม 6,500.00 บาท เกินงบ 1,500.00 บาท\n"
            "มี 2 เดือนที่เกินงบ กลับมาอยู่ในงบเดือน ธ.ค. 2569",
            OVER_NOW,
        ),
        ("ค่างวดรวม 6,500.00 บาท ไม่อยู่ในงบ", OVER_NOW),
        ("เกินงบ 2 เดือน", OVER_NOW),  # the count, as "N เดือน"
        (
            "ถ้ารวมหนี้ ค่างวดจะลดลงเดือนละ 4,130.12 บาท ถ้าสนใจ ธนาคารจะติดต่อกลับเพื่อพิจารณา",
            OVER_NOW,
        ),
        ("เดือนนี้อยู่ในงบ แต่ ธ.ค. 2569 เกินงบ", BASE),
        ("ทุกเดือนอยู่ในงบ และไม่เกินงบเลย", ALL_IN),
        ("กลับมาอยู่ภายในงบเดือน ธ.ค. 2569", OVER_NOW),
        ("ค่างวดรวม 3,500 บาท อยู่ในงบ 5,000 บาท", ALL_IN),  # whole baht, no ".00"
    ],
)
def test_AI_30_a_claim_the_facts_support_passes(text: str, allow: Allowed) -> None:
    assert check(text, allow) is None, check(text, allow)


# The demo-mon text the check refused in the first real ai-check (Session 19). Line 2
# says no month is over budget: a negation, true for demo-mon. Line 3 brings up the
# third of income for a GREEN verdict, and says the months from now on meet it.
AI_CHECK_REFUSED = (
    "เดือน ต.ค. 2569 ค่างวดรวม 3,500.00 บาท อยู่ในงบ 5,000.00 บาท\n"
    "ตอนนี้ไม่มีเดือนไหนที่ค่างวดเกินงบ\n"
    "ธปท. แนะนำให้ค่างวดไม่เกิน 1 ใน 3 ของรายได้ และทุกเดือนจากนี้อยู่ในเกณฑ์นี้"
)
NO_MONTH_OVER = [
    "ตอนนี้ไม่มีเดือนไหนที่ค่างวดเกินงบ",  # the exact line ai-check refused
    "ไม่มีเดือนไหนเกินงบ",
    "ยังไม่มีเดือนใดที่ค่างวดรวมเกินงบเลย",
    "ไม่มีสักเดือนที่เกินงบ",
    "ไม่มีเดือนไหนเลย ที่ค่างวดเกินงบ",
    "ไม่มีช่วงไหนที่ค่างวดเกินงบ",
]


def test_AI_30_the_ai_check_refusal_now_fails_only_on_the_third_of_income() -> None:
    lines = AI_CHECK_REFUSED.split("\n")
    assert check("\n".join(lines[:2]), ALL_IN) is None
    assert failed(AI_CHECK_REFUSED, ALL_IN) is Check.ONE_THIRD_NOT_RED
    red = replace(ALL_IN, above_one_third=True)
    found = check(AI_CHECK_REFUSED, red)  # even when RED: the months do not meet it
    assert found is not None
    assert (found.check, found.token) == (Check.CLAIM_NOT_IN_INPUT, "เกณฑ์")


@pytest.mark.parametrize("text", NO_MONTH_OVER)
def test_AI_30_no_month_over_budget_is_a_negation_not_an_over_budget_claim(text: str) -> None:
    assert check(text, ALL_IN) is None, check(text, ALL_IN)
    assert failed(text, BASE) is Check.CLAIM_NOT_IN_INPUT  # while a month is over
    assert failed(text, OVER_NOW) is Check.CLAIM_NOT_IN_INPUT


@pytest.mark.parametrize("text", ["ค่างวดไม่ได้เกินงบ", "ค่างวดไม่เคยเกินงบ"])
def test_AI_30_not_over_budget_in_other_words(text: str) -> None:
    assert check(text, ALL_IN) is None, check(text, ALL_IN)
    assert failed(text, OVER_NOW) is Check.CLAIM_NOT_IN_INPUT  # this month is over


RED = replace(BASE, above_one_third=True)


@pytest.mark.parametrize(
    "text",
    [
        "ธปท. แนะนำว่าไม่ควรเกิน 1 ใน 3 ของรายได้",
        "บางเดือนเกิน 1 ใน 3 ของรายได้ ที่ ธปท. แนะนำ",
        "บางเดือนเกินกว่า 1 ใน 3 ของรายได้ ที่ ธปท. แนะนำ",
        "ค่างวดไม่ถึงหนึ่งในสามของรายได้ ที่แนะนำ",
        "ธนาคารแห่งประเทศไทยแนะนำให้ผ่อนแต่พอดี",
    ],
)
def test_AI_30_the_third_of_income_is_said_only_when_the_verdict_is_red(text: str) -> None:
    assert failed(text, BASE) is Check.ONE_THIRD_NOT_RED
    assert failed(text, ALL_IN) is Check.ONE_THIRD_NOT_RED


@pytest.mark.parametrize(
    "text",
    [
        "ธปท. แนะนำให้ค่างวดไม่เกิน 1 ใน 3 ของรายได้ และทุกเดือนจากนี้อยู่ในเกณฑ์นี้",
        "บางเดือนเกิน 1 ใน 3 ของรายได้ ซึ่ง ธปท. แนะนำ แต่ตั้งแต่ ธ.ค. 2569 จะไม่เกิน 1 ใน 3",
        "ตั้งแต่ ธ.ค. 2569 ค่างวดจะต่ำกว่า 1 ใน 3 ของรายได้ ที่ ธปท. แนะนำ",
        "หลังจากนี้ค่างวดจะไม่เกินที่ ธปท. แนะนำ",
        "ทุกเดือนผ่านเกณฑ์ที่ ธปท. แนะนำ",
        "ค่างวดเดือนนี้เป็นไปตามคำแนะนำของ ธปท.",
    ],
)
def test_AI_30_months_that_meet_the_third_are_never_said(text: str) -> None:
    assert failed(text, RED) is Check.CLAIM_NOT_IN_INPUT


@pytest.mark.parametrize(
    "text",
    [
        "บางเดือนค่างวดรวมเกิน 1 ใน 3 ของรายได้ ซึ่ง ธปท. แนะนำว่าไม่ควรเกิน",  # the template's
        "บางเดือนเกิน 1 ใน 3 ของรายได้ ซึ่ง ธปท. แนะนำว่าไม่ควรเกิน 1 ใน 3 ของรายได้",
        "ธปท. แนะนำว่าไม่ควรเกิน 1 ใน 3 ของรายได้",
        "ธปท. แนะนำให้ค่างวดไม่เกิน 1 ใน 3 ของรายได้",  # the guidance, not a claim
        "บางเดือนเกิน 1 ใน 3 ของรายได้ ที่ ธปท. แนะนำ",
    ],
)
def test_AI_30_the_guidance_passes_when_the_verdict_is_red(text: str) -> None:
    assert check(text, RED) is None, check(text, RED)


# --- AI-19: the extractor finds every number and month, in every display format ------

EXAMPLES = 1500  # summed into the progress log's Hypothesis count

AMOUNTS = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("9999999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)
FILLER = st.lists(
    st.sampled_from(["ค่างวด", "รวม", "บาท", "เดือนนี้", "กันชน", "งบ", "เกิน", " ", "ของคุณ"]),
    max_size=4,
).map("".join)


def display_formats(value: Decimal) -> list[str]:
    forms = [f"{value:,.2f}", f"{value:.2f}"]
    if value == value.to_integral_value():
        forms += [f"{value:,.0f}", f"{value:.0f}"]
    return forms + [form.translate(THAI_DIGITS) for form in forms]


@settings(max_examples=EXAMPLES, deadline=None)
@given(value=AMOUNTS, pick=st.integers(min_value=0, max_value=7), before=FILLER, after=FILLER)
def test_AI_19_every_display_format_of_an_amount_is_read_as_its_value(
    value: Decimal, pick: int, before: str, after: str
) -> None:
    forms = display_formats(value)
    text = f"{before}{forms[pick % len(forms)]}{after}"
    found = extract(text)
    assert found.numbers == [value]
    assert found.months == []
    assert found.malformed == []
    assert found.stray == []


@settings(max_examples=EXAMPLES, deadline=None)
@given(
    index=st.integers(min_value=1900 * 12, max_value=2400 * 12),
    names=st.sampled_from([THAI_MONTHS, THAI_MONTH_NAMES, THAI_MONTH_SHORT, THAI_MONTH_UNDOTTED]),
    era=st.booleans(),
    thai_digits=st.booleans(),
    before=FILLER,
)
def test_AI_19_a_thai_month_and_buddhist_year_is_read_as_that_month(
    index: int, names: tuple[str, ...], era: bool, thai_digits: bool, before: str
) -> None:
    month = Month(index)
    name = names[month.month - 1]
    year = str(month.year + 543)
    year = year.translate(THAI_DIGITS) if thai_digits else year
    text = f"{before}เดือน {name} {'พ.ศ. ' if era else ''}{year}"
    found = extract(text)
    assert found.months == [MonthMention(text[text.index(name) :], month.month, month.year + 543)]
    assert found.numbers == []
    assert found.malformed == []
    assert found.stray == []


@settings(max_examples=EXAMPLES, deadline=None)
@given(shown=AMOUNTS, given_value=AMOUNTS, pick=st.integers(min_value=0, max_value=7))
def test_AI_19_an_amount_passes_exactly_when_it_equals_an_input(
    shown: Decimal, given_value: Decimal, pick: int
) -> None:
    forms = display_formats(shown)
    text = f"ค่างวดรวม {forms[pick % len(forms)]} บาท"
    result = check(text, allowed(str(given_value), months=()))
    assert (result is None) == (shown == given_value)
