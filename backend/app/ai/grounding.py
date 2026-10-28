"""The grounding check on AI text (04 section 14, Session 18). Pure: no I/O.

The model only words numbers our code computed. Every number and month in its text
must be one of the input values, in any format the screens or alerts display
("3,500.00", "3,500", "3500", Thai digits, "ต.ค. 2569", "ตุลาคม 2569", a Buddhist
year on its own). Anything in doubt rejects the text: the caller then shows the
fallback template, so a false rejection only costs the AI wording, never a number.

Numbers are also tied to what they may mean: a count only as "N เดือน", a Buddhist
year only as four bare digits, and the amount after "เกินงบ" or "ลดลง" only an
over-budget amount or the consolidation's reduction. Claims about the budget must
match the facts: no "every month is within budget" while a month is over, and so on.
It cannot prove every sentence true; it refuses the wrong claims we know to look for.

The wording rules come from the product rules: no prepaying or closing early (L69),
no more debt or investing, consolidation only as an option the bank considers (L71),
the third of income is what the Bank of Thailand recommends, never "requires" (L65),
no em dashes (rule 10) and no brand names (rule 5).
"""

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.affordability.months import Month
from app.notifications.copy import BUDDHIST_ERA_OFFSET, THAI_MONTHS

MAX_CHARS = 500
MAX_LINES = 4

THAI_MONTH_NAMES = (
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
)
MONTH_OF = {
    name: i + 1 for names in (THAI_MONTHS, THAI_MONTH_NAMES) for i, name in enumerate(names)
}
# Longest first, so "พฤศจิกายน" is never read as a shorter name. The year is taken
# only when it is a whole 4-digit number ("ต.ค. 25690" leaves 25690 a plain number).
MONTH_RE = re.compile(
    "(?P<name>"
    + "|".join(re.escape(n) for n in sorted(MONTH_OF, key=len, reverse=True))
    + r")(?:\s*(?:พ\.ศ\.\s*)?(?P<year>\d{4})(?!\d|[,.]\d))?"
)
# Digit runs, commas only between runs, an optional decimal part, and a minus sign
# (hyphen, minus or any dash) right before it, so "-1,500" is negative and never
# matches an amount.
SIGNS = "-\u2212\u2010\u2011\u2012\u2013\u2014"
NUMBER_RE = re.compile(f"(?P<sign>[{SIGNS}]?)" r"(?P<digits>\d+(?:,\d+)*(?:\.\d+)?)")
GROUPED = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?")
# The 1/3-of-income rule is a fixed phrase, not a number from the input (L65).
ONE_THIRD_RE = re.compile(r"1\s*ใน\s*3")

# Rule 10: the em dash, and its look-alikes (en dash, bar, figure dash, 2- and 3-em).
DASHES = ("\u2014", "\u2013", "\u2015", "\u2012", "\u2e3a", "\u2e3b")
ALLOWED_LATIN = ("KidNee",)  # the display name (rule 5); any other Latin text is refused
MARKUP = frozenset("*#`_~|<>[]{}")  # the card shows plain text

# Each entry is refused anywhere in the text.
BANNED = (
    # Never advise prepaying or closing an installment early (L69).
    "โปะ",
    "ปิดหนี้",
    "ปิดยอด",
    "ปิดบัญชี",
    "ปิดงวด",
    "ปิดก่อน",
    "จ่ายล่วงหน้า",
    "ชำระล่วงหน้า",
    "ผ่อนล่วงหน้า",
    "จ่ายก่อน",
    "ชำระก่อน",
    "จ่ายหมด",
    "ชำระหมด",
    "จ่ายเพิ่ม",
    "ชำระเพิ่ม",
    "ปลดหนี้",
    "เคลียร์",
    # Never suggest more debt, or investing (05 AI-06).
    "กู้",
    "ยืม",
    "สินเชื่อ",
    "ผ่อนเพิ่มได้",
    "ผ่อนได้อีก",
    "ซื้อเพิ่มได้",
    "ซื้อได้อีก",
    "ก่อหนี้",
    "สร้างหนี้",
    "กดเงินสด",
    "เบิกเงินสด",
    "รูดบัตร",
    "ลงทุน",
    "หุ้น",
    "กองทุน",
    "คริปโต",
    # Consolidation is never approved by anyone but the bank (L71).
    "อนุมัติ",
    "การันตี",
    "รับประกัน",
    "รับรอง",
    "ควรรวมหนี้",
    "ต้องรวมหนี้",
    # The third of income is guidance, never a rule (L65): "ธปท. แนะนำ", never "กำหนด".
    "กำหนด",
    "กฎหมาย",
    "บังคับ",
    "ระเบียบ",
    # Rule 5: no bank or shop brand. Built from parts, so this file does not hold the
    # names it forbids (as frontend/tests/guards.test.ts does).
    *(a + b for a, b in (("กสิ", "กร"), ("เคแบ", "งก์"), ("เคพ", "ลัส"), ("ช้อป", "ปี้"), ("ช็อป", "ปี้"))),
)
# Consolidating, not "ภาพรวมหนี้" (the debt overview) or "ยอดรวมหนี้" (the total owed),
# and its synonyms.
CONSOLIDATION_RE = re.compile("(?<!ภาพ)(?<!ยอด)รวมหนี้|รวบหนี้|รีไฟแนนซ์")
# Numbers in words: a magnitude or a percentage anywhere, a digit word next to ร้อย or
# พัน ("ห้าร้อย", "พันห้า"), or a digit word right before a counted word.
DIGIT_WORD = "(?:หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ|ยี่|เอ็ด)"
NUMBER_WORDS_RE = re.compile(
    r"หมื่น|แสน|ล้าน|ครึ่ง|ร้อยละ|เปอร์เซ็น"
    rf"|{DIGIT_WORD}(?:ร้อย|พัน)|(?:ร้อย|พัน){DIGIT_WORD}"
    rf"|(?<!เรียบ)(?:{DIGIT_WORD}|ร้อย|พัน)+"
    r"\s*(?:เดือน|บาท|งวด|ปี|ครั้ง|รายการ|เท่า|ชิ้น|ส่วน|ก้อน|อย่าง|แอป|วัน|สัปดาห์)"
)
# Claims about the budget, checked against the facts.
ALL_IN_BUDGET_RE = re.compile(r"ทุกเดือน(?:ยัง|ก็)?\s*อยู่ในงบ|ไม่มี(?:เดือน)?\S{0,8}?เกินงบ|ไม่เกินงบเลย")
IN_BUDGET_RE = re.compile("(?<!กลับมา)(?<!ไม่)อยู่ในงบ")
OVER_BUDGET_RE = re.compile("(?<!ไม่)เกินงบ")
THIS_MONTH_OVER_RE = re.compile(r"เดือนนี้(?:ค่างวด(?:รวม)?)?(?:ก็)?\s*เกินงบ")
ABOVE_THIRD_RE = re.compile(r"(?<!ไม่)(?<!ไม่ควร)เกิน\s*(?:1\s*ใน\s*3|หนึ่งในสาม)")
# An amount right after these words must be one of these facts.
SIGNED = f"[{SIGNS}]?" r"\d[\d,]*(?:\.\d+)?"
OVER_BY_RE = re.compile(rf"เกินงบ(?:อยู่|ไป)?\s*(?P<num>{SIGNED})(?P<unit>\s*เดือน)?")
REDUCTION_RE = re.compile(rf"ลด(?:ลง)?(?:ได้)?(?:อีก)?(?:เดือนละ)?\s*(?P<num>{SIGNED})")


class Check(StrEnum):
    """Why a text was refused: the first rule it broke, in this order."""

    EMPTY = "empty"
    TOO_LONG = "too_long"
    TOO_MANY_LINES = "too_many_lines"
    CONTROL_CHARACTER = "control_character"
    DASH = "dash"
    NOT_THAI = "not_thai"
    MARKUP = "markup"
    BANNED_PHRASE = "banned_phrase"
    CONSOLIDATION_NOT_OFFERED = "consolidation_not_offered"
    CONSOLIDATION_WORDING = "consolidation_wording"
    ONE_THIRD_WORDING = "one_third_wording"
    CLAIM_NOT_IN_INPUT = "claim_not_in_input"
    NUMBER_IN_WORDS = "number_in_words"
    MONTH_NOT_IN_INPUT = "month_not_in_input"
    MALFORMED_NUMBER = "malformed_number"
    NUMBER_NOT_IN_INPUT = "number_not_in_input"
    STRAY_NUMERAL = "stray_numeral"


@dataclass(frozen=True)
class Failure:
    check: Check
    token: str  # what broke it, for the morning check's console; never logged


@dataclass(frozen=True)
class Allowed:
    """What the model was given. `numbers` are amounts, in any display format;
    `counts` are numbers of months, allowed only as "N เดือน"; a Buddhist year of a
    given month is allowed as four bare digits. `over_by` are the amounts over budget
    and `reductions` the consolidation's monthly reduction, for the amounts right after
    "เกินงบ" and "ลดลง". The flags are what the budget claims may say."""

    numbers: frozenset[Decimal]
    counts: frozenset[Decimal]
    months: frozenset[Month]
    over_by: frozenset[Decimal]
    reductions: frozenset[Decimal]
    consolidation_offered: bool
    over_now: bool  # this month's total is above the budget
    any_over: bool  # some month from now on is above the budget
    above_one_third: bool  # some month is above a third of income (verdict RED)


@dataclass(frozen=True)
class MonthMention:
    text: str
    month: int  # 1-12
    year: int | None  # Buddhist era, as written; None when no year follows


@dataclass(frozen=True)
class NumberMention:
    value: Decimal
    bare: bool  # digits only, no comma or decimal part: may be a count or a year
    months_after: bool  # "เดือน" right after it: a number of months


@dataclass(frozen=True)
class Extracted:
    months: list[MonthMention]
    mentions: list[NumberMention]
    malformed: list[str]  # digits in a shape we never display ("35,00")
    stray: list[str]  # numerals \d does not read: "²", "½", "Ⅻ"

    @property
    def numbers(self) -> list[Decimal]:
        return [n.value for n in self.mentions]


def ascii_digits(text: str) -> str:
    """Thai and other decimal digits as 0-9; anything else unchanged."""
    return "".join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in text)


def extract(text: str) -> Extracted:
    """Every month and number in the text. Months first (their dots and years are not
    numbers), then the fixed "1 ใน 3", then the numbers left."""
    months = [
        MonthMention(
            m.group(0),
            MONTH_OF[m.group("name")],
            None if m.group("year") is None else int(ascii_digits(m.group("year"))),
        )
        for m in MONTH_RE.finditer(text)
    ]
    rest = ONE_THIRD_RE.sub(" ", MONTH_RE.sub(" ", text))
    mentions: list[NumberMention] = []
    malformed: list[str] = []
    for m in NUMBER_RE.finditer(rest):
        digits = ascii_digits(m.group("digits"))
        if "," in digits and GROUPED.fullmatch(digits) is None:
            malformed.append(m.group(0))
            continue
        value = _decimal(digits)
        bare = digits.isdigit()
        after = re.match(r"\s*เดือน", rest[m.end() :]) is not None
        mentions.append(NumberMention(-value if m.group("sign") else value, bare, after))
    left = NUMBER_RE.sub(" ", rest)
    stray = [c for c in left if unicodedata.numeric(c, None) is not None]
    return Extracted(months, mentions, malformed, stray)


def _decimal(text: str) -> Decimal:
    """A number as the patterns above match it ("-1,500.00", Thai digits)."""
    sign = text[:1] != "" and text[0] in SIGNS
    digits = ascii_digits(text[1:] if sign else text).replace(",", "")
    try:
        value = Decimal(digits)
    except InvalidOperation:  # pragma: no cover - the patterns only admit digits
        return Decimal("NaN")  # equal to nothing, so never an allowed value
    return -value if sign else value


def _wording(text: str, allowed: Allowed) -> Iterator[Failure]:
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        yield Failure(Check.EMPTY, "")
    if len(text) > MAX_CHARS:
        yield Failure(Check.TOO_LONG, str(len(text)))
    if len(lines) > MAX_LINES:
        yield Failure(Check.TOO_MANY_LINES, str(len(lines)))
    for c in text:
        if c != "\n" and unicodedata.category(c) in ("Cc", "Cf"):
            yield Failure(Check.CONTROL_CHARACTER, f"U+{ord(c):04X}")
    for dash in DASHES:
        if dash in text:
            yield Failure(Check.DASH, dash)
    latin = text
    for word in ALLOWED_LATIN:
        latin = latin.replace(word, " ")
    for c in latin:
        if c.isascii() and c.isalpha():
            yield Failure(Check.NOT_THAI, c)
        if c in MARKUP:
            yield Failure(Check.MARKUP, c)
    for phrase in BANNED:
        if phrase in text:
            yield Failure(Check.BANNED_PHRASE, phrase)
    if CONSOLIDATION_RE.search(text) is not None:
        if not allowed.consolidation_offered:
            yield Failure(Check.CONSOLIDATION_NOT_OFFERED, "รวมหนี้")
        if "พิจารณา" not in text:
            yield Failure(Check.CONSOLIDATION_WORDING, "รวมหนี้")
    third = ONE_THIRD_RE.search(text) or re.search("ธปท|หนึ่งในสาม|1/3", text)
    if third is not None and "แนะนำ" not in text:
        yield Failure(Check.ONE_THIRD_WORDING, third.group(0))
    yield from _claims(text, allowed)
    words = NUMBER_WORDS_RE.search(text)
    if words is not None:
        yield Failure(Check.NUMBER_IN_WORDS, words.group(0))


def _claims(text: str, allowed: Allowed) -> Iterator[Failure]:
    """Budget claims the facts do not support, and amounts after "เกินงบ" or "ลดลง"
    that are not what those words mean."""
    refused = [
        (allowed.any_over, ALL_IN_BUDGET_RE),  # "every month is within budget"
        (not allowed.any_over, OVER_BUDGET_RE),  # "over budget" while nothing is
        (allowed.over_now, IN_BUDGET_RE),  # "within budget" while this month is over
        (not allowed.over_now, THIS_MONTH_OVER_RE),  # "this month is over" while it is not
        (not allowed.above_one_third, ABOVE_THIRD_RE),  # "above a third" while none is
    ]
    for applies, pattern in refused:
        found = pattern.search(text) if applies else None
        if found is not None:
            yield Failure(Check.CLAIM_NOT_IN_INPUT, found.group(0))
    for m in OVER_BY_RE.finditer(text):
        value = _decimal(m.group("num"))
        counted = m.group("unit") is not None and value in allowed.counts
        if not counted and value not in allowed.over_by:
            yield Failure(Check.CLAIM_NOT_IN_INPUT, m.group(0))
    for m in REDUCTION_RE.finditer(text):
        if _decimal(m.group("num")) not in allowed.reductions:
            yield Failure(Check.CLAIM_NOT_IN_INPUT, m.group(0))


def _values(found: Extracted, allowed: Allowed) -> Iterator[Failure]:
    years = {Decimal(m.year + BUDDHIST_ERA_OFFSET) for m in allowed.months}
    for mention in found.months:
        if mention.year is None:
            ok = any(m.month == mention.month for m in allowed.months)
        else:
            year = mention.year - BUDDHIST_ERA_OFFSET
            ok = Month(year * 12 + mention.month - 1) in allowed.months
        if not ok:
            yield Failure(Check.MONTH_NOT_IN_INPUT, mention.text)
    for token in found.malformed:
        yield Failure(Check.MALFORMED_NUMBER, token)
    for n in found.mentions:
        counted = n.bare and n.months_after and n.value in allowed.counts
        year = n.bare and n.value in years  # "ปี 2569", never "2,569.00"
        if n.value not in allowed.numbers and not counted and not year:
            yield Failure(Check.NUMBER_NOT_IN_INPUT, str(n.value))
    for c in found.stray:
        yield Failure(Check.STRAY_NUMERAL, c)


def check(text: str, allowed: Allowed) -> Failure | None:
    """None when the text may be shown; else the first rule it broke."""
    failures = [*_wording(text, allowed), *_values(extract(text), allowed)]
    return failures[0] if failures else None
