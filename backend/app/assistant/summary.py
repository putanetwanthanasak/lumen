"""Home's "ผู้ช่วย KidNee สรุปให้ฟัง" card (Session 18): a short Thai summary that the
model words from numbers the code already computed (04 section 14).

AI only words things: it never computes, decides, writes the Ledger or moves money.
The facts are the payoff plan's and the buffer shortfalls' (assistant.plan), the same
numbers the screens show. Only numbers and months go to the model: no item or
platform name, nothing the user typed (privacy, and no prompt-injection surface).

Every answer passes the grounding check (ai.grounding) or is replaced by the fallback
template, built from the same facts. No key, a timeout or any API error also give the
template, so the card always has text. Answers are cached per user, keyed by a hash
of the facts, the prompt version and the model, so a reload never asks again until
the numbers change.
"""

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.affordability.months import Month, MonthTotal, Verdict, verdict
from app.affordability.service import require_profile
from app.ai.grounding import Allowed, Failure, check
from app.ai.provider import Writer, WriterTimeoutError
from app.assistant.plan import (
    ZERO,
    Plan,
    PreparedState,
    Shortfalls,
    build,
    shortfalls,
)
from app.assistant.service import debts
from app.buffer.service import balance, prepared_by_month
from app.config import Settings
from app.notifications.copy import thai_month

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).resolve().parents[1] / "ai" / "prompts" / "summary_v1.md"
PROMPT_VERSION = PROMPT_FILE.stem  # in the cache key: a new prompt asks again
PROMPT = PROMPT_FILE.read_text(encoding="utf-8")
MAX_OVER_MONTHS = 12  # months over budget sent in detail; the count covers them all


class Reason(StrEnum):
    OK = "ok"
    NO_KEY = "no_key"
    TIMEOUT = "timeout"
    API_ERROR = "api_error"
    GROUNDING_FAILED = "grounding_failed"


@dataclass(frozen=True)
class OverMonth:
    month: Month
    total: Decimal
    over_by: Decimal  # total - budget; a buffer move never changes it
    state: PreparedState
    prepared: Decimal  # moved from the buffer for this month
    remaining_gap: Decimal  # max(0, over_by - prepared)


@dataclass(frozen=True)
class Facts:
    month: Month  # this month
    total: Decimal  # this month's total (L65), Home's hero
    budget: Decimal
    income: Decimal
    verdict: Verdict  # L65 over every month from this one on
    over_months: tuple[OverMonth, ...]  # the first MAX_OVER_MONTHS over budget
    over_month_count: int | None  # None when the rows stop at the 600-month cap
    last_over_month: Month | None  # None when none is over, or the rows stop at the cap
    back_in_budget: Month | None
    buffer_balance: Decimal
    buffer_covered: bool  # the buffer covers every gap still open
    all_prepared: bool  # buffer money moved for every month over budget (no gap left)
    still_short: Decimal
    consolidation_offered: bool  # L70 eligible
    monthly_reduction: Decimal | None  # only when offered and above 0.00


def facts_of(plan: Plan, gaps: Shortfalls, *, income: Decimal) -> Facts:
    """Pure: the summary's facts from the plan and the shortfalls of one read."""
    this = plan.rows[0]  # the rows always start at the current month
    estimate = plan.consolidation.estimate
    reduction = None if estimate is None else estimate.monthly_reduction
    return Facts(
        month=this.month,
        total=this.total,
        budget=plan.budget,
        income=income,
        verdict=verdict(
            [MonthTotal(r.month, r.total) for r in plan.rows], income=income, budget=plan.budget
        ),
        over_months=tuple(
            OverMonth(m.month, m.total, m.shortfall, m.state, m.prepared, m.remaining_gap)
            for m in gaps.months[:MAX_OVER_MONTHS]
        ),
        over_month_count=None if gaps.months_truncated else len(gaps.months),
        last_over_month=None if gaps.months_truncated or not gaps.months else gaps.months[-1].month,
        back_in_budget=plan.back_in_budget_month,
        buffer_balance=gaps.buffer.balance,
        buffer_covered=gaps.buffer.covered,
        all_prepared=bool(gaps.months) and gaps.buffer.remaining_gap == ZERO,
        still_short=gaps.buffer.still_short,
        consolidation_offered=plan.consolidation.eligible,
        monthly_reduction=reduction if reduction is not None and reduction > ZERO else None,
    )


def load_facts(session: Session, user_id: str, *, today: date, settings: Settings) -> Facts:
    """One read for the plan and the shortfalls, so the two never disagree. Raises
    affordability.service.SettingsRequiredError without an income and budget."""
    profile = require_profile(session, user_id)
    now = Month.of(today)
    prepared = prepared_by_month(session, user_id, since=now)  # before balance (R2-F1)
    owed = debts(session, user_id)
    buffer = balance(session, user_id)
    plan = build(
        owed,
        now=now,
        income=profile.income,
        budget=profile.budget,
        buffer_balance=buffer,
        annual_rate=settings.consolidation_example_annual_rate,
        term=settings.consolidation_example_term_months,
        prepared=prepared,
    )
    gaps = shortfalls(
        [d.schedule for d in owed],
        now=now,
        budget=profile.budget,
        balance=buffer,
        prepared=prepared,
    )
    return facts_of(plan, gaps, income=profile.income)


# --- What the model sees, and what it may say ----------------------------------------


def baht(amount: Decimal) -> str:
    """3500.00 -> "3,500.00 บาท", as the screens show money. Decimal only."""
    return f"{amount:,.2f} บาท"


def _over(m: OverMonth) -> dict[str, Any]:
    out: dict[str, Any] = {
        "month": thai_month(m.month),
        "total": baht(m.total),
        "over_by": baht(m.over_by),
        "buffer_prepared": m.state.value,
    }
    if m.state is not PreparedState.NOT_PREPARED:
        out["prepared"] = baht(m.prepared)
    if m.state is PreparedState.PARTLY_PREPARED:
        out["still_to_prepare"] = baht(m.remaining_gap)
    return out


def model_input(facts: Facts) -> dict[str, Any]:
    """The facts as the model gets them, formatted as the screens show them. Every
    value here, and nothing else, is in allowed_of (AI-21)."""
    this: dict[str, Any] = {
        "month": thai_month(facts.month),
        "total": baht(facts.total),
        "budget": baht(facts.budget),
        "within_budget": facts.total <= facts.budget,
    }
    if facts.total > facts.budget:
        this["over_by"] = baht(facts.total - facts.budget)
    over: dict[str, Any] = {"months": [_over(m) for m in facts.over_months]}
    if facts.over_month_count is not None:
        over["count"] = facts.over_month_count
    if facts.last_over_month is not None:
        over["last_month_over_budget"] = thai_month(facts.last_over_month)
    buffer: dict[str, Any] = {
        "balance": baht(facts.buffer_balance),
        "covers_all_months_over_budget": facts.buffer_covered,
        "prepared_for_every_month_over_budget": facts.all_prepared,
    }
    if not facts.buffer_covered:
        buffer["still_short"] = baht(facts.still_short)
    consolidation: dict[str, Any] = {"offered": facts.consolidation_offered}
    if facts.monthly_reduction is not None:
        consolidation["monthly_reduction"] = baht(facts.monthly_reduction)
    return {
        "this_month": this,
        "income": baht(facts.income),
        "verdict": facts.verdict.value,
        "months_over_budget": over,
        "back_in_budget_month": None
        if facts.back_in_budget is None
        else thai_month(facts.back_in_budget),
        "buffer": buffer,
        "consolidation": consolidation,
    }


def allowed_of(facts: Facts) -> Allowed:
    """Every number and month model_input sends, for the grounding check."""
    amounts = [facts.total, facts.budget, facts.income, facts.buffer_balance]
    over_by = [m.over_by for m in facts.over_months]
    if facts.total > facts.budget:
        over_by.append(facts.total - facts.budget)
    amounts += over_by
    for m in facts.over_months:
        amounts.append(m.total)
        if m.state is not PreparedState.NOT_PREPARED:
            amounts.append(m.prepared)
        if m.state is PreparedState.PARTLY_PREPARED:
            amounts.append(m.remaining_gap)
    if not facts.buffer_covered:
        amounts.append(facts.still_short)
    reductions = [] if facts.monthly_reduction is None else [facts.monthly_reduction]
    amounts += reductions
    counts = [] if facts.over_month_count is None else [Decimal(facts.over_month_count)]
    months = {facts.month, *(m.month for m in facts.over_months)}
    for month in (facts.last_over_month, facts.back_in_budget):
        if month is not None:
            months.add(month)
    return Allowed(
        numbers=frozenset(amounts),
        counts=frozenset(counts),
        months=frozenset(months),
        over_by=frozenset(over_by),
        reductions=frozenset(reductions),
        consolidation_offered=facts.consolidation_offered,
        over_now=facts.total > facts.budget,
        any_over=bool(facts.over_months),
        above_one_third=facts.verdict is Verdict.RED,
    )


def facts_text(facts: Facts) -> str:
    """The user message: the facts as JSON, sorted so the same facts give the same
    bytes (the cache key)."""
    data = json.dumps(model_input(facts), ensure_ascii=False, sort_keys=True, indent=1)
    return f"<facts>\n{data}\n</facts>"


# --- The fallback: the same facts in fixed words -------------------------------------

ONE_THIRD_NOTE = "บางเดือนค่างวดรวมเกิน 1 ใน 3 ของรายได้ ซึ่ง ธปท. แนะนำว่าไม่ควรเกิน"


def _months_line(facts: Facts) -> str:
    if not facts.over_months:
        line = "ทุกเดือนอยู่ในงบ"
    else:
        first, last = facts.over_months[0].month, facts.last_over_month
        if facts.over_month_count is None or last is None:
            line = f"มีเดือนที่ค่างวดเกินงบตั้งแต่ {thai_month(first)}"
        elif facts.over_month_count == 1:
            line = f"มี 1 เดือนที่ค่างวดเกินงบ คือ {thai_month(first)}"
        else:
            span = f"ตั้งแต่ {thai_month(first)} ถึง {thai_month(last)}"
            line = f"มี {facts.over_month_count} เดือนที่ค่างวดเกินงบ {span}"
        if facts.back_in_budget is not None:
            line += f" กลับมาอยู่ในงบเดือน {thai_month(facts.back_in_budget)}"
    return f"{line} {ONE_THIRD_NOTE}" if facts.verdict is Verdict.RED else line


def _buffer_line(facts: Facts) -> str:
    if not facts.over_months:
        return f"กันชนตอนนี้ {baht(facts.buffer_balance)}"
    if facts.all_prepared:
        return "เตรียมเงินจากกันชนครบทุกเดือนที่เกินงบแล้ว"
    if facts.buffer_covered:
        return f"กันชน {baht(facts.buffer_balance)} พอจ่ายส่วนที่เกินได้ทั้งหมด"
    return f"กันชน {baht(facts.buffer_balance)} ยังขาดอีก {baht(facts.still_short)}"


def fallback_text(facts: Facts) -> str:
    """The deterministic summary: at most 4 lines, every number from the facts, so it
    always passes the grounding check (AI-20)."""
    over = facts.total > facts.budget
    this = f"เดือน {thai_month(facts.month)} ค่างวดรวม {baht(facts.total)} " + (
        f"เกินงบ {baht(facts.total - facts.budget)}" if over else f"อยู่ในงบ {baht(facts.budget)}"
    )
    lines = [this, _months_line(facts), _buffer_line(facts)]
    if facts.consolidation_offered:
        lines.append(
            "รวมหนี้เป็นทางเลือกหนึ่ง"
            if facts.monthly_reduction is None
            else f"ถ้ารวมหนี้ ค่างวดอาจลดลงเดือนละ {baht(facts.monthly_reduction)}"
        )
        lines[-1] += " ถ้าสนใจ ธนาคารจะติดต่อกลับเพื่อพิจารณา"
    elif over:
        lines.append("ตอนนี้ยังไม่ควรผ่อนเพิ่ม")
    return "\n".join(lines)


# --- Asking, checking and caching ----------------------------------------------------


@dataclass(frozen=True)
class Summary:
    text: str
    source: Literal["ai", "fallback"]
    reason: Reason
    # For `python -m demo.kidnee ai-check` only: the model's text the check refused,
    # and why. Never sent to the client, never logged.
    rejected: str | None = None
    failure: Failure | None = None


class SummaryCache:
    """In memory, per user: the last answer and the key it was for. One lock per user,
    so two reloads at once ask the model once (AI-18)."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._entries: dict[str, tuple[str, Summary]] = {}

    def lock(self, user_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(user_id, threading.Lock())

    def get(self, user_id: str, key: str) -> Summary | None:
        entry = self._entries.get(user_id)
        return entry[1] if entry is not None and entry[0] == key else None

    def put(self, user_id: str, key: str, summary: Summary) -> None:
        self._entries[user_id] = (key, summary)


CACHE = SummaryCache()


def get_summary_cache() -> SummaryCache:
    """FastAPI dependency; the tests give each test its own cache."""
    return CACHE


def cache_key(facts: Facts, model: str) -> str:
    raw = json.dumps([PROMPT_VERSION, model, facts_text(facts)], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _fallback(facts: Facts, reason: Reason, **why: Any) -> Summary:
    return Summary(fallback_text(facts), "fallback", reason, **why)


def _ask(facts: Facts, writer: Writer) -> Summary:
    try:
        text = writer.write(system=PROMPT, facts=facts_text(facts))
    except WriterTimeoutError:
        return _fallback(facts, Reason.TIMEOUT)
    except Exception:  # WriterError, or anything else the writer raised: no answer
        return _fallback(facts, Reason.API_ERROR)
    text = text.replace("\r\n", "\n").strip()
    failure = check(text, allowed_of(facts))
    if failure is not None:
        return _fallback(facts, Reason.GROUNDING_FAILED, rejected=text, failure=failure)
    return Summary(text, "ai", Reason.OK)


def summarize(facts: Facts, *, user_id: str, writer: Writer | None, cache: SummaryCache) -> Summary:
    """The card's text. Without a writer (no key) the model is never asked. Otherwise
    one call per user and facts; every outcome of a call is cached, so a timeout is
    not waited for again on each reload (no retries)."""
    if writer is None:
        result = _fallback(facts, Reason.NO_KEY)
    else:
        key = cache_key(facts, writer.model)
        with cache.lock(user_id):
            hit = cache.get(user_id, key)
            result = hit if hit is not None else _ask(facts, writer)
            cache.put(user_id, key, result)
    # The reason and the check's name only: never the prompt, the reply or the key.
    logger.info(
        "assistant summary: source=%s reason=%s%s",
        result.source,
        result.reason.value,
        "" if result.failure is None else f" check={result.failure.check.value}",
    )
    return result
