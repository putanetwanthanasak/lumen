"""AI-01 to AI-05 and AI-10: the grounding check on the model's text (app.ai.grounding).
Pure: no database, no model. Every number and month in the text must be an input
value, in any format the screens display; the wording rules hold; anything else is
refused, so the caller shows the fallback."""

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.affordability.months import Month
from app.ai.grounding import (
    BANNED,
    THAI_MONTH_NAMES,
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
    *numbers: str, months: tuple[Month, ...] = (OCT_2026,), offered: bool = False
) -> Allowed:
    return Allowed(frozenset(Decimal(n) for n in numbers), frozenset(months), offered)


BASE = allowed("3500.00", "5000.00", "1500.00", "2", months=(OCT_2026, NOV_2026, DEC_2026))
GOOD = (
    "เดือน ต.ค. 2569 ค่างวดรวม 3,500.00 บาท อยู่ในงบ 5,000.00 บาท\n"
    "มี 2 เดือนที่ค่างวดเกินงบ กลับมาอยู่ในงบเดือน ธ.ค. 2569\n"
    "ผู้ช่วย KidNee แนะนำให้เตรียมกันชนไว้ 1,500.00 บาท"
)


def failed(text: str, allow: Allowed = BASE) -> Check | None:
    found = check(text, allow)
    return None if found is None else found.check


# --- AI-01: grounded text passes -----------------------------------------------------


def test_AI_01_grounded_text_passes() -> None:
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
        "เกิน 1 ใน 3 ของรายได้ ที่ ธปท. แนะนำ",  # the fixed phrase of the L65 guidance
        "ภาพรวมหนี้ของคุณดูได้ที่หน้าหลัก",  # the debt overview, not consolidation
    ],
)
def test_AI_01_every_display_format_of_an_input_value_passes(text: str) -> None:
    assert check(text, BASE) is None, check(text, BASE)


def test_AI_01_consolidation_as_an_option_the_bank_considers_passes() -> None:
    text = "ถ้าสนใจรวมหนี้ ธนาคารจะติดต่อกลับเพื่อพิจารณา"
    assert check(text, allowed(offered=True)) is None


# --- AI-02, AI-03: a number or month not in the input --------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "ค่างวดรวม 3,600.00 บาท",  # wrong by 100
        "ค่างวดรวม 3,500.01 บาท",  # wrong by a satang
        "ค่างวดรวม 350.00 บาท",
        "ค่างวด๓,๖๐๐บาท",  # Thai digits, wrong
    ],
)
def test_AI_02_a_wrong_number_is_refused(text: str) -> None:
    assert failed(text) is Check.NUMBER_NOT_IN_INPUT


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("ค่างวดรวม 3,500.00 บาท ลดได้ 10%", Check.NUMBER_NOT_IN_INPUT),
        ("ค่างวดรวม 3,500.00 บาท เกินงบ 3 เดือน", Check.NUMBER_NOT_IN_INPUT),
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
def test_AI_03_an_extra_number_month_or_year_is_refused(text: str, why: Check) -> None:
    assert failed(text) is why


# --- AI-04: dashes (rule 10) -----------------------------------------------------------


@pytest.mark.parametrize("dash", ["\u2014", "\u2013", "\u2015", "\u2012", "\u2e3a", "\u2e3b"])
def test_AI_04_an_em_dash_or_a_look_alike_is_refused(dash: str) -> None:
    assert failed(f"ค่างวดรวม 3,500.00 บาท {dash} อยู่ในงบ") is Check.DASH


# --- AI-05: wording rules --------------------------------------------------------------


@pytest.mark.parametrize("phrase", BANNED)
def test_AI_05_every_banned_phrase_is_refused(phrase: str) -> None:
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
        ("เปิดแอปกสิกรเพื่อดู", Check.BANNED_PHRASE),  # rule 5
        ("ดูใน KBank ได้เลย", Check.NOT_THAI),  # rule 5, and English
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
    ],
)
def test_AI_05_wording_rules(text: str, why: Check | None) -> None:
    assert failed(text) is why


def test_AI_05_consolidation_must_say_the_bank_considers_it() -> None:
    assert failed("รวมหนี้แล้วค่างวดลดลง", allowed(offered=True)) is Check.CONSOLIDATION_WORDING


def test_AI_05_the_first_broken_rule_is_reported_with_its_token() -> None:
    found = check("โปะหนี้ 9,999.00 บาท", BASE)
    assert found is not None
    assert (found.check, found.token) == (Check.BANNED_PHRASE, "โปะ")
    found = check("ค่างวดรวม 3,600.00 บาท", BASE)
    assert found is not None
    assert (found.check, found.token) == (Check.NUMBER_NOT_IN_INPUT, "3600.00")


# --- AI-10: the extractor finds every number and month, in every display format ------

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


@given(value=AMOUNTS, pick=st.integers(min_value=0, max_value=7), before=FILLER, after=FILLER)
def test_AI_10_every_display_format_of_an_amount_is_read_as_its_value(
    value: Decimal, pick: int, before: str, after: str
) -> None:
    forms = display_formats(value)
    text = f"{before}{forms[pick % len(forms)]}{after}"
    found = extract(text)
    assert found.numbers == [value]
    assert found.months == []
    assert found.malformed == []
    assert found.stray == []


@given(
    index=st.integers(min_value=1900 * 12, max_value=2400 * 12),
    full=st.booleans(),
    era=st.booleans(),
    thai_digits=st.booleans(),
    before=FILLER,
)
def test_AI_10_a_thai_month_and_buddhist_year_is_read_as_that_month(
    index: int, full: bool, era: bool, thai_digits: bool, before: str
) -> None:
    month = Month(index)
    name = (THAI_MONTH_NAMES if full else THAI_MONTHS)[month.month - 1]
    year = str(month.year + 543)
    year = year.translate(THAI_DIGITS) if thai_digits else year
    text = f"{before}เดือน {name} {'พ.ศ. ' if era else ''}{year}"
    found = extract(text)
    assert found.months == [MonthMention(text[text.index(name) :], month.month, month.year + 543)]
    assert found.numbers == []
    assert found.malformed == []
    assert found.stray == []


@given(shown=AMOUNTS, given_value=AMOUNTS, pick=st.integers(min_value=0, max_value=7))
def test_AI_10_an_amount_passes_exactly_when_it_equals_an_input(
    shown: Decimal, given_value: Decimal, pick: int
) -> None:
    forms = display_formats(shown)
    text = f"ค่างวดรวม {forms[pick % len(forms)]} บาท"
    result = check(text, allowed(str(given_value), months=()))
    assert (result is None) == (shown == given_value)
