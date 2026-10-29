"""AI-10, AI-11 to AI-14 (through the service), AI-15 to AI-18, AI-20, AI-21, AI-26 and
AI-31: Home's summary (app.assistant.summary) over the plan's own numbers, with a fake
model and, for the cache, a fake clock.
Pure: no database. The three stories are the KidNee personas' (demo.kidnee), with
"today" in November 2026."""

import logging
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.affordability.months import Month, Scheduled, Verdict
from app.ai.grounding import Allowed, Check, check, extract
from app.ai.provider import WriterError, WriterTimeoutError
from app.assistant import summary
from app.assistant.plan import Debt, PreparedState, build, shortfalls
from app.assistant.summary import (
    ONE_THIRD_NOTE,
    PROMPT,
    PROMPT_FILE,
    RETRY_AFTER_NS,
    STEP_BUFFER,
    STEP_CONSOLIDATION,
    STEP_MONTHS,
    Facts,
    OverMonth,
    Reason,
    SummaryCache,
    allowed_of,
    baht,
    cache_key,
    facts_of,
    facts_text,
    fallback_text,
    model_input,
    summarize,
)
from tests.ai.fakes import FakeWriter

NOW = Month.of(date(2026, 11, 10))
INCOME = Decimal("20000.00")
BUDGET = Decimal("5000.00")
USER = "user_a"


def plan_facts(
    schedules: list[Scheduled], balance: str, prepared: dict[Month, Decimal] | None = None
) -> Facts:
    debts = [
        Debt(s, s.monthly_amount * s.months, manual=True, overdue=False, disputed=False)
        for s in schedules
    ]
    gaps_in = prepared or {}
    plan = build(
        debts,
        now=NOW,
        income=INCOME,
        budget=BUDGET,
        buffer_balance=Decimal(balance),
        annual_rate=Decimal("0.18"),
        term=24,
        prepared=gaps_in,
    )
    gaps = shortfalls(schedules, now=NOW, budget=BUDGET, balance=Decimal(balance), prepared=gaps_in)
    return facts_of(plan, gaps, income=INCOME)


def plan_of(monthly: str, months: int, offset: int) -> Scheduled:
    return Scheduled(NOW.plus(offset), months, Decimal(monthly))


EARBUDS = plan_of("2000.00", 6, -3)
FRIDGE = plan_of("1500.00", 10, -1)
LAPTOP = plan_of("3000.00", 10, 0)
MOTORBIKE = plan_of("4000.00", 12, 0)

MON = plan_facts([EARBUDS, FRIDGE], "2700.00")
OVER = plan_facts([plan_of("2000.00", 6, -4), FRIDGE, LAPTOP], "5700.00")
CONSOLIDATE = plan_facts([EARBUDS, FRIDGE, MOTORBIKE], "1500.00")

MON_AI = "เดือน พ.ย. 2569 ค่างวดรวม 3,500.00 บาท อยู่ในงบ 5,000.00 บาท\nทุกเดือนอยู่ในงบ และมีกันชน 2,700 บาท"


def ask(
    facts: Facts, writer: FakeWriter | None, cache: SummaryCache | None = None
) -> summary.Summary:
    return summarize(facts, user_id=USER, writer=writer, cache=cache or SummaryCache())


# --- The stories' facts and fallbacks ---------------------------------------------------


def test_AI_20_31_each_story_leads_with_what_matters_most_for_it() -> None:
    # In budget: say so first; this month's total out of the budget; the months screen.
    assert fallback_text(MON) == (
        "ค่างวดทุกเดือนอยู่ในงบ เดือนนี้รวม 3,500 บาท จากงบ 5,000 บาท\n"
        "กันชนตอนนี้มี 2,700 บาท\n"
        "ดูค่างวดแต่ละเดือนได้ที่หน้าภาระผ่อนรายเดือน"
    )
    # Over budget, covered: the months over and what the buffer does for them first.
    assert fallback_text(OVER) == (
        "มี 2 เดือนที่ค่างวดเกินงบ ตั้งแต่ พ.ย. 2569 ถึง ธ.ค. 2569 "
        "แต่กันชน 5,700 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด\n"
        "เดือนนี้ค่างวดรวม 6,500 บาท เกินงบ 1,500 บาท และกลับมาอยู่ในงบตั้งแต่ ม.ค. 2570\n"
        "ดูส่วนที่เกินงบแต่ละเดือนได้ที่หน้ากันชน"
    )
    # RED and offered: the months over and the third of income, then consolidation as
    # the card words it, with satang kept when there are some.
    assert CONSOLIDATE.verdict is Verdict.RED  # 7,500.00 x 3 > 20,000.00 (L65)
    assert CONSOLIDATE.monthly_reduction == Decimal("4130.12")
    assert fallback_text(CONSOLIDATE) == (
        "มี 9 เดือนที่ค่างวดเกินงบ ตั้งแต่ พ.ย. 2569 ถึง ก.ค. 2570 "
        "บางเดือนค่างวดรวมเกิน 1 ใน 3 ของรายได้ ซึ่ง ธปท. แนะนำว่าไม่ควรเกิน\n"
        "ถ้ารวมหนี้ ค่างวดจะลดลงเดือนละ 4,130.12 บาท ถ้าสนใจ ธนาคารจะติดต่อกลับเพื่อพิจารณา\n"
        "ดูรายละเอียดได้ที่การ์ดรวมหนี้ในหน้าหลัก"
    )
    for facts in (MON, OVER, CONSOLIDATE):
        assert check(fallback_text(facts), allowed_of(facts)) is None


def test_AI_20_31_red_without_the_bank_says_the_buffer_second() -> None:
    red = replace(CONSOLIDATE, consolidation_offered=False, monthly_reduction=None)
    assert fallback_text(red).split("\n")[1:] == [
        "กันชน 1,500 บาท ยังขาดอีก 9,000 บาท",
        "ดูส่วนที่เกินงบแต่ละเดือนได้ที่หน้ากันชน",
    ]
    in_budget = replace(MON, verdict=Verdict.RED)  # a budget above a third (L64)
    assert fallback_text(in_budget).split("\n")[0] == f"ค่างวดทุกเดือนอยู่ในงบ แต่{ONE_THIRD_NOTE}"
    for facts in (red, in_budget):
        assert check(fallback_text(facts), allowed_of(facts)) is None


def test_AI_20_one_month_over_budget_is_named() -> None:
    one = plan_facts([EARBUDS, FRIDGE, plan_of("2000.00", 1, 1)], "2700.00")
    assert fallback_text(one).split("\n")[:2] == [
        "มี 1 เดือนที่ค่างวดเกินงบ คือ ธ.ค. 2569 แต่กันชน 2,700 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด",
        "เดือนนี้ค่างวดรวม 3,500 บาท ยังอยู่ในงบ",
    ]
    assert check(fallback_text(one), allowed_of(one)) is None


def test_AI_20_prepared_months_are_said_as_the_buffer_screen_says_them() -> None:
    nov, dec = NOW, NOW.plus(1)
    over = [plan_of("2000.00", 6, -4), FRIDGE, LAPTOP]
    partly = plan_facts(over, "4200.00", {nov: Decimal("1000.00")})
    assert partly.over_months[0].state is PreparedState.PARTLY_PREPARED
    assert fallback_text(partly).split("\n")[0].endswith(" แต่กันชน 4,200 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด")
    every = plan_facts(over, "2700.00", {nov: Decimal("1500.00"), dec: Decimal("1500.00")})
    assert every.all_prepared
    assert fallback_text(every).split("\n")[0].endswith(" และเตรียมเงินจากกันชนครบทุกเดือนที่เกินงบแล้ว")
    assert check(fallback_text(partly), allowed_of(partly)) is None
    assert check(fallback_text(every), allowed_of(every)) is None


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        ("3500.00", "3,500 บาท"),
        ("4130.12", "4,130.12 บาท"),
        ("4130.10", "4,130.10 บาท"),
        ("0.00", "0 บาท"),
        ("0.05", "0.05 บาท"),
        ("1234567.50", "1,234,567.50 บาท"),
        ("9999999999.00", "9,999,999,999 บาท"),
    ],
)
def test_AI_31_whole_baht_without_satang_and_satang_only_when_there_are_some(
    amount: str, shown: str
) -> None:
    assert baht(Decimal(amount)) == shown


def test_AI_31_the_model_gets_the_amounts_as_the_card_shows_them() -> None:
    data = model_input(CONSOLIDATE)
    assert data["this_month"]["total"] == "7,500 บาท"
    assert data["consolidation"]["monthly_reduction"] == "4,130.12 บาท"
    assert ".00 บาท" not in facts_text(CONSOLIDATE)


# --- AI-10 to AI-14: the model's text, checked -------------------------------------------


def test_AI_10_grounded_model_text_is_shown_as_ai() -> None:
    writer = FakeWriter(text=f"  {MON_AI}\r\n")
    result = ask(MON, writer)
    assert (result.text, result.source, result.reason) == (MON_AI, "ai", Reason.OK)
    assert writer.calls == [(PROMPT, facts_text(MON))]


@pytest.mark.parametrize(
    ("text", "why"),
    [
        (MON_AI.replace("3,500.00", "3,600.00"), Check.NUMBER_NOT_IN_INPUT),  # AI-11
        (MON_AI + " เหลือ 1,500.00 บาท", Check.NUMBER_NOT_IN_INPUT),  # AI-12: computed
        (MON_AI.replace("พ.ย. 2569", "ธ.ค. 2569"), Check.MONTH_NOT_IN_INPUT),  # AI-12
        (MON_AI.replace(" และ", " \u2014 และ"), Check.DASH),  # AI-13
        (MON_AI + " ลองโปะหนี้ก้อนเล็กก่อน", Check.BANNED_PHRASE),  # AI-14: L69
        (MON_AI + " ยังผ่อนเพิ่มได้", Check.BANNED_PHRASE),  # AI-14: more debt
        (MON_AI + " ถ้ารวมหนี้ ธนาคารจะพิจารณา", Check.CONSOLIDATION_NOT_OFFERED),  # AI-14
    ],
)
def test_AI_11_to_14_refused_model_text_gives_the_fallback(text: str, why: Check) -> None:
    result = ask(MON, FakeWriter(text=text))
    assert (result.text, result.source, result.reason) == (
        fallback_text(MON),
        "fallback",
        Reason.GROUNDING_FAILED,
    )
    assert result.failure is not None
    assert result.failure.check is why
    assert result.rejected == text


def test_AI_14_consolidation_as_an_option_passes_only_when_offered() -> None:
    reduction = summary.baht(CONSOLIDATE.monthly_reduction or Decimal(0))
    text = (
        "เดือน พ.ย. 2569 ค่างวดรวม 7,500.00 บาท เกินงบ 2,500.00 บาท\n"
        f"ถ้าสนใจรวมหนี้ ค่างวดจะลดลงเดือนละ {reduction} ธนาคารจะติดต่อกลับเพื่อพิจารณา"
    )
    assert ask(CONSOLIDATE, FakeWriter(text=text)).reason is Reason.OK
    assert ask(OVER, FakeWriter(text=text)).reason is Reason.GROUNDING_FAILED


# --- AI-15 to AI-17: no key, timeout, API error -----------------------------------------


def test_AI_15_no_key_gives_the_fallback_without_asking() -> None:
    result = ask(MON, None)
    assert (result.text, result.source, result.reason) == (
        fallback_text(MON),
        "fallback",
        Reason.NO_KEY,
    )


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (WriterTimeoutError(), Reason.TIMEOUT),
        (WriterError("RateLimitError"), Reason.API_ERROR),
        (RuntimeError("a writer bug"), Reason.API_ERROR),
    ],
)
def test_AI_16_17_timeout_and_api_errors_give_the_fallback_once(
    error: Exception, reason: Reason
) -> None:
    writer = FakeWriter(error=error)
    result = ask(OVER, writer)
    assert (result.text, result.source, result.reason) == (fallback_text(OVER), "fallback", reason)
    assert len(writer.calls) == 1  # no retries


# --- AI-18: the cache --------------------------------------------------------------------


def test_AI_18_the_same_numbers_never_ask_twice() -> None:
    cache, writer = SummaryCache(), FakeWriter(text=MON_AI)
    first = ask(MON, writer, cache)
    again = ask(replace(MON), writer, cache)  # equal facts, a new object
    assert first == again
    assert first.source == "ai"
    assert len(writer.calls) == 1


def test_AI_18_other_numbers_another_user_or_another_model_ask_again() -> None:
    cache, writer = SummaryCache(), FakeWriter(text=MON_AI)
    ask(MON, writer, cache)
    # Another user with exactly the same numbers has an answer of their own (B167).
    summarize(MON, user_id="user_b", writer=writer, cache=cache)
    assert len(writer.calls) == 2
    ask(MON, writer, cache)  # and the first user's answer is still there
    assert len(writer.calls) == 2
    ask(replace(MON, buffer_balance=Decimal("2700.01")), writer, cache)
    assert len(writer.calls) == 3
    other = FakeWriter(text=MON_AI, model="another-model")
    ask(MON, other, cache)
    assert len(other.calls) == 1


class Clock:
    """Monotonic nanoseconds that move only when a test moves them."""

    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now


SECOND = 1_000_000_000


def test_AI_18_a_timeout_is_cached_too_so_a_reload_does_not_wait_again() -> None:
    clock = Clock()
    cache, writer = SummaryCache(clock), FakeWriter(error=WriterTimeoutError())
    assert ask(OVER, writer, cache).reason is Reason.TIMEOUT
    clock.now = RETRY_AFTER_NS - 1  # within the 2 minutes
    assert ask(OVER, writer, cache).reason is Reason.TIMEOUT
    assert len(writer.calls) == 1


@pytest.mark.parametrize(
    ("error", "reason"),
    [(WriterTimeoutError(), Reason.TIMEOUT), (WriterError("APIConnectionError"), Reason.API_ERROR)],
)
def test_AI_18_after_a_timeout_or_api_error_the_model_is_asked_again_after_2_minutes(
    error: Exception, reason: Reason
) -> None:
    assert RETRY_AFTER_NS == 120 * SECOND
    clock = Clock()
    cache, writer = SummaryCache(clock), FakeWriter(text=MON_AI, error=error)
    assert ask(MON, writer, cache).reason is reason
    clock.now = 60 * SECOND  # a reload within the 2 minutes: the cached fallback
    assert ask(MON, writer, cache).reason is reason
    assert len(writer.calls) == 1
    # That reload did not move the 2 minutes on: at 120 s from the call, ask again.
    writer.error = None
    clock.now = RETRY_AFTER_NS
    result = ask(MON, writer, cache)
    assert (result.source, result.reason) == ("ai", Reason.OK)
    assert len(writer.calls) == 2


def test_AI_18_an_ai_answer_stays_until_the_numbers_change() -> None:
    clock = Clock()
    cache, writer = SummaryCache(clock), FakeWriter(text=MON_AI)
    assert ask(MON, writer, cache).reason is Reason.OK
    clock.now = 30 * 24 * 3600 * SECOND  # a month later, the same numbers
    assert ask(MON, writer, cache).reason is Reason.OK
    assert len(writer.calls) == 1
    ask(replace(MON, buffer_balance=Decimal("2700.01")), writer, cache)
    assert len(writer.calls) == 2


def test_AI_18_a_refused_text_stays_until_the_numbers_change() -> None:
    """The same facts would most likely get the same words: asking again costs a call
    for the same fallback (Session 19, open question)."""
    clock = Clock()
    cache, writer = SummaryCache(clock), FakeWriter(text=MON_AI + " โปะหนี้")
    assert ask(MON, writer, cache).reason is Reason.GROUNDING_FAILED
    clock.now = 3600 * SECOND
    assert ask(MON, writer, cache).reason is Reason.GROUNDING_FAILED
    assert len(writer.calls) == 1


def test_AI_18_no_key_is_not_cached() -> None:
    cache = SummaryCache()
    assert ask(MON, None, cache).reason is Reason.NO_KEY
    writer = FakeWriter(text=MON_AI)
    assert ask(MON, writer, cache).reason is Reason.OK
    assert len(writer.calls) == 1


def test_AI_18_the_cache_is_read_and_written_under_the_users_lock() -> None:
    """So two reloads at once never both miss and both ask the model."""

    class Watched(SummaryCache):
        def __init__(self) -> None:
            super().__init__()
            self.held: list[tuple[str, bool]] = []

        def get(self, user_id: str, key: str) -> summary.Summary | None:
            self.held.append(("get", self.lock(user_id).locked()))
            return super().get(user_id, key)

        def put(self, user_id: str, key: str, value: summary.Summary) -> None:
            self.held.append(("put", self.lock(user_id).locked()))
            super().put(user_id, key, value)

    cache = Watched()
    ask(MON, FakeWriter(text=MON_AI), cache)
    assert cache.held == [("get", True), ("put", True)]


def test_AI_18_the_users_lock_is_held_while_the_model_is_asked() -> None:
    cache = SummaryCache()
    seen: list[tuple[bool, bool]] = []
    writer = FakeWriter(
        text=MON_AI,
        during=lambda: seen.append((cache.lock(USER).locked(), cache.lock("user_b").locked())),
    )
    ask(MON, writer, cache)
    assert seen == [(True, False)]  # a second reload waits, then reads the cache
    assert cache.lock(USER) is cache.lock(USER)
    assert not cache.lock(USER).locked()


def test_AI_18_the_app_shares_one_cache_across_requests() -> None:
    assert summary.get_summary_cache() is summary.get_summary_cache() is summary.CACHE


def test_AI_26_the_prompt_version_and_the_model_are_in_the_cache_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = cache_key(MON, "fake-model")
    assert key == cache_key(replace(MON), "fake-model")
    assert key != cache_key(MON, "another-model")
    monkeypatch.setattr(summary, "PROMPT_VERSION", "summary_v3")
    assert key != cache_key(MON, "fake-model")


# --- AI-26: the prompt file ---------------------------------------------------------------


def test_AI_26_the_prompt_is_a_versioned_file_with_the_rules() -> None:
    assert PROMPT_FILE.name == "summary_v2.md"
    assert summary.PROMPT_VERSION == "summary_v2"
    for rule in ("ธปท. แนะนำ", "กำหนด", "เกณฑ์", "รวมหนี้", "ประมาณ", "อาจ", "at most 3", "Thai"):
        assert rule in PROMPT
    for dash in ("\u2014", "\u2013"):
        assert dash not in PROMPT  # its Thai examples follow rule 10 too
    # Its example lines are in the app's own words: given their own numbers and months,
    # each one passes every rule of the check.
    examples = PROMPT.split("never copy them):\n")[1].strip().splitlines()
    assert len(examples) == 3
    assert examples[-1] == STEP_BUFFER
    assert ".00" not in "\n".join(examples)
    # One story: two months over later, the buffer covers them, this month in budget.
    found = extract("\n".join(examples))
    story = Allowed(
        numbers=frozenset(found.numbers),
        counts=frozenset(found.numbers),
        months=frozenset(Month((m.year - 543) * 12 + m.month - 1) for m in found.months if m.year),
        over_by=frozenset(),
        reductions=frozenset(),
        consolidation_offered=False,
        over_now=False,
        any_over=True,
        above_one_third=False,
    )
    for line in examples:
        assert check(line, story) is None, (line, check(line, story))


def test_AI_31_the_prompt_quotes_the_templates_own_sentences() -> None:
    """The model and the fallback word the third of income, the bank's option and the
    next step the same way."""
    for sentence in (ONE_THIRD_NOTE, STEP_CONSOLIDATION, STEP_BUFFER, STEP_MONTHS):
        assert f'"{sentence}"' in PROMPT
    assert (
        '"ถ้ารวมหนี้ ค่างวดจะลดลงเดือนละ <monthly_reduction> ถ้าสนใจ ธนาคารจะติดต่อกลับเพื่อพิจารณา"' in PROMPT
    )


# --- AI-21: only numbers and months reach the model ---------------------------------------

EXAMPLES = 1500  # summed into the progress log's Hypothesis count

AMOUNTS = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("9999999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@st.composite
def any_facts(draw: st.DrawFn) -> Facts:
    """Facts as the plan gives them: this month is over budget only when it is the
    first of the months over budget."""
    month = Month(draw(st.integers(min_value=2000 * 12, max_value=2100 * 12)))
    n = draw(st.integers(min_value=0, max_value=15))
    over_now = n > 0 and draw(st.booleans())
    start = 0 if over_now else 1
    budget, gap = draw(AMOUNTS), draw(AMOUNTS)
    total = budget + gap + Decimal("0.01") if over_now else max(budget - gap, Decimal("0.00"))
    over = tuple(
        OverMonth(
            month.plus(start + i),
            draw(AMOUNTS),
            draw(AMOUNTS),
            draw(st.sampled_from(PreparedState)),
            draw(AMOUNTS),
            draw(AMOUNTS),
        )
        for i in range(min(n, summary.MAX_OVER_MONTHS))
    )
    truncated = n > 0 and draw(st.booleans())
    offered = draw(st.booleans())
    return Facts(
        month=month,
        total=total,
        budget=budget,
        income=draw(AMOUNTS),
        verdict=draw(st.sampled_from(Verdict)),
        over_months=over,
        over_month_count=None if truncated else n,
        last_over_month=None if truncated or n == 0 else month.plus(start + n - 1),
        back_in_budget=None
        if n == 0
        else draw(st.none() | st.integers(0, 5).map(lambda k: month.plus(start + n + k))),
        buffer_balance=draw(AMOUNTS),
        buffer_covered=draw(st.booleans()),
        all_prepared=n > 0 and draw(st.booleans()),
        still_short=draw(AMOUNTS),
        consolidation_offered=offered,
        monthly_reduction=draw(st.none() | AMOUNTS.filter(lambda d: d > 0)) if offered else None,
    )


@settings(max_examples=EXAMPLES, deadline=None)
@given(facts=any_facts())
def test_AI_20_the_fallback_always_passes_the_check(facts: Facts) -> None:
    text = fallback_text(facts)
    assert check(text, allowed_of(facts)) is None, check(text, allowed_of(facts))
    lines = text.split("\n")
    assert len(lines) == 3
    assert all(line.strip() for line in lines)
    assert "\u2014" not in text


@settings(max_examples=EXAMPLES, deadline=None)
@given(facts=any_facts())
def test_AI_31_the_fallback_follows_the_tone_rules(facts: Facts) -> None:
    lead, detail, step = fallback_text(facts).split("\n")
    # What matters most first: the months over budget, or that there are none.
    assert lead.startswith("มี" if facts.over_months else "ค่างวดทุกเดือนอยู่ในงบ")
    assert ("1 ใน 3" in lead) is (facts.verdict is Verdict.RED)
    assert "1 ใน 3" not in detail + step  # said once, and only when RED
    # Never two sentences opening with "เดือน" or "ค่างวดรวม".
    for opening in ("เดือน", "ค่างวดรวม"):
        assert sum(line.startswith(opening) for line in (lead, detail, step)) <= 1
    # One next step on a screen, with no number.
    expected = (
        STEP_CONSOLIDATION
        if facts.consolidation_offered
        else STEP_BUFFER
        if facts.over_months
        else STEP_MONTHS
    )
    assert step == expected
    assert re.search(r"\d", step) is None
    # Whole baht without ".00", and no hedge on an exact amount.
    assert re.search(r"\.00(?!\d)", lead + detail) is None
    for hedge in ("ประมาณ", "อาจ", "เกือบ"):
        assert hedge not in lead + detail


@settings(max_examples=EXAMPLES, deadline=None)
@given(facts=any_facts())
def test_AI_21_the_model_gets_exactly_the_allowed_numbers_and_months(facts: Facts) -> None:
    allowed = allowed_of(facts)
    sent = extract(facts_text(facts))
    years = {Decimal(m.year + 543) for m in allowed.months}
    assert set(sent.numbers) <= allowed.numbers | allowed.counts | years
    assert allowed.numbers | allowed.counts <= set(sent.numbers)
    assert allowed.over_by | allowed.reductions <= allowed.numbers
    assert {(m.month, m.year) for m in sent.months} == {
        (m.month, m.year + 543) for m in allowed.months
    }
    assert sent.malformed == []
    assert sent.stray == []


def test_AI_21_the_model_input_holds_numbers_months_and_flags_only() -> None:
    for facts in (MON, OVER, CONSOLIDATE):
        data = model_input(facts)
        assert set(data) == {
            "this_month",
            "income",
            "verdict",
            "months_over_budget",
            "back_in_budget_month",
            "buffer",
            "consolidation",
        }
        for value in _leaves(data):
            assert isinstance(value, bool | int | None) or (
                isinstance(value, str)
                and (
                    value.endswith(" บาท")
                    or extract(value).months
                    or value in {v.value for v in (*Verdict, *PreparedState)}
                )
            ), value


def _leaves(value: object) -> list[object]:
    if isinstance(value, dict):
        return [leaf for v in value.values() for leaf in _leaves(v)]
    if isinstance(value, list):
        return [leaf for v in value for leaf in _leaves(v)]
    return [value]


# --- Logs ------------------------------------------------------------------------------------


def test_AI_22_the_log_says_the_reason_and_never_the_prompt_or_the_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    ask(MON, FakeWriter(text=MON_AI + " โปะหนี้"))
    assert "source=fallback reason=grounding_failed check=banned_phrase" in caplog.text
    for secret in ("2,700", "3,500", "โปะ", "facts", PROMPT[:40]):
        assert secret not in caplog.text
