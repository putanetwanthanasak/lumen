"""AI-10, AI-11 to AI-14 (through the service), AI-15 to AI-18, AI-20, AI-21 and AI-26:
Home's summary (app.assistant.summary) over the plan's own numbers, with a fake model.
Pure: no database. The three stories are the KidNee personas' (demo.kidnee), with
"today" in November 2026."""

import logging
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
    PROMPT,
    PROMPT_FILE,
    Facts,
    OverMonth,
    Reason,
    SummaryCache,
    allowed_of,
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


def test_AI_20_each_story_has_its_own_fallback_in_the_apps_words() -> None:
    assert fallback_text(MON) == (
        "เดือน พ.ย. 2569 ค่างวดรวม 3,500.00 บาท อยู่ในงบ 5,000.00 บาท\n"
        "ทุกเดือนอยู่ในงบ\n"
        "กันชนตอนนี้ 2,700.00 บาท"
    )
    assert fallback_text(OVER) == (
        "เดือน พ.ย. 2569 ค่างวดรวม 6,500.00 บาท เกินงบ 1,500.00 บาท\n"
        "มี 2 เดือนที่ค่างวดเกินงบ ตั้งแต่ พ.ย. 2569 ถึง ธ.ค. 2569 กลับมาอยู่ในงบเดือน ม.ค. 2570\n"
        "กันชน 5,700.00 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด\n"
        "ตอนนี้ยังไม่ควรผ่อนเพิ่ม"
    )
    assert CONSOLIDATE.verdict is Verdict.RED  # 7,500.00 x 3 > 20,000.00 (L65)
    assert CONSOLIDATE.monthly_reduction is not None
    assert fallback_text(CONSOLIDATE) == (
        "เดือน พ.ย. 2569 ค่างวดรวม 7,500.00 บาท เกินงบ 2,500.00 บาท\n"
        "มี 9 เดือนที่ค่างวดเกินงบ ตั้งแต่ พ.ย. 2569 ถึง ก.ค. 2570 กลับมาอยู่ในงบเดือน ส.ค. 2570 "
        "บางเดือนค่างวดรวมเกิน 1 ใน 3 ของรายได้ ซึ่ง ธปท. แนะนำว่าไม่ควรเกิน\n"
        "กันชน 1,500.00 บาท ยังขาดอีก 9,000.00 บาท\n"
        f"ถ้ารวมหนี้ ค่างวดอาจลดลงเดือนละ {summary.baht(CONSOLIDATE.monthly_reduction)} "
        "ถ้าสนใจ ธนาคารจะติดต่อกลับเพื่อพิจารณา"
    )


def test_AI_20_one_month_over_budget_is_named() -> None:
    one = plan_facts([EARBUDS, FRIDGE, plan_of("2000.00", 1, 1)], "2700.00")
    assert fallback_text(one).split("\n")[1:3] == [
        "มี 1 เดือนที่ค่างวดเกินงบ คือ ธ.ค. 2569 กลับมาอยู่ในงบเดือน ม.ค. 2570",
        "กันชน 2,700.00 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด",
    ]
    assert check(fallback_text(one), allowed_of(one)) is None


def test_AI_20_prepared_months_are_said_as_the_buffer_screen_says_them() -> None:
    nov, dec = NOW, NOW.plus(1)
    over = [plan_of("2000.00", 6, -4), FRIDGE, LAPTOP]
    partly = plan_facts(over, "4200.00", {nov: Decimal("1000.00")})
    assert partly.over_months[0].state is PreparedState.PARTLY_PREPARED
    assert fallback_text(partly).split("\n")[2] == "กันชน 4,200.00 บาท พอจ่ายส่วนที่เกินได้ทั้งหมด"
    every = plan_facts(over, "2700.00", {nov: Decimal("1500.00"), dec: Decimal("1500.00")})
    assert every.all_prepared
    assert fallback_text(every).split("\n")[2] == "เตรียมเงินจากกันชนครบทุกเดือนที่เกินงบแล้ว"
    assert check(fallback_text(partly), allowed_of(partly)) is None
    assert check(fallback_text(every), allowed_of(every)) is None


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
        f"ถ้าสนใจรวมหนี้ ค่างวดอาจลดลงเดือนละ {reduction} ธนาคารจะติดต่อกลับเพื่อพิจารณา"
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


def test_AI_18_a_timeout_is_cached_too_so_a_reload_does_not_wait_again() -> None:
    cache, writer = SummaryCache(), FakeWriter(error=WriterTimeoutError())
    assert ask(OVER, writer, cache).reason is Reason.TIMEOUT
    assert ask(OVER, writer, cache).reason is Reason.TIMEOUT
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
    monkeypatch.setattr(summary, "PROMPT_VERSION", "summary_v2")
    assert key != cache_key(MON, "fake-model")


# --- AI-26: the prompt file ---------------------------------------------------------------


def test_AI_26_the_prompt_is_a_versioned_file_with_the_rules() -> None:
    assert PROMPT_FILE.name == "summary_v1.md"
    assert summary.PROMPT_VERSION == "summary_v1"
    for rule in ("ธปท. แนะนำ", "กำหนด", "รวมหนี้", "ธนาคารจะติดต่อกลับเพื่อพิจารณา", "Thai"):
        assert rule in PROMPT
    for dash in ("\u2014", "\u2013"):
        assert dash not in PROMPT  # its Thai examples follow rule 10 too
    # Its example lines are in the app's own words: given their own numbers and months,
    # each one passes every rule of the check.
    examples = PROMPT.split("never copy them):\n")[1].strip().splitlines()
    assert len(examples) == 4
    # One story: this month in budget, two later months over, the buffer covers them.
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
    assert 3 <= len(lines) <= 4
    assert all(line.strip() for line in lines)
    assert "\u2014" not in text


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
