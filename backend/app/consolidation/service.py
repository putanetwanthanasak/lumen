"""Consolidation requests (L70, L71, L72), in the caller's single transaction.

Order, so that a double submit is decided once however it arrives:
1. A request already stored under (user, client_request_id) gets its first answer
   again (the same payoffs) or a conflict (other payoffs, audited, as L55).
2. A per-user advisory lock serialises every request of this user. Then the lock of
   each counted contract (ledger.lock_contract, which the webhook processor and
   "Not me" take first too), then the counted rows FOR UPDATE. So the eligibility
   below is current, and no other request or platform event can change those rows
   before commit: a platform event waits instead of writing over `consolidated`
   (review F3). The contract locks come before the row locks, in the same order as
   the webhook path takes them, so the two cannot deadlock.
3. The lookup again: a request that was waiting behind the lock finds the one that
   just committed.
4. Eligibility now (L70), from the payoff plan itself, and the payoffs must name
   exactly the counted installments. Otherwise 409, audited, nothing stored, so the
   same id may be used again once eligible (Session 14, open question 9).
5. The bank decides (L71). Declined: the request row and the audit, nothing else.
   Approved (L72): the loan, the paid-off installments marked consolidated, one
   payout row per installment, the alert, the audit, and reconcile. The request
   row's UNIQUE (user_id, client_request_id) is the second idempotency layer.

The caller commits, then pays the platforms (pay_out): money moves only after the
ledger rows are committed, and a repeat calls pay_out again under the same keys, so
a payout that failed after the commit is completed by the client's retry (as the
buffer move, Session 13 review round 2 F1).
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.affordability.months import Month
from app.affordability.service import require_profile
from app.assistant import service as assistant
from app.assistant.plan import Reason, amortised_payment, remaining_for_payoff
from app.audit import service as audit
from app.config import Settings
from app.consolidation.schemas import ConsolidationRequestIn
from app.debts.service import OWED_STATUSES, still_owed
from app.ledger import reconcile
from app.ledger.service import lock_contract
from app.models import (
    CONSOLIDATION_VENDOR,
    MANUAL_VENDOR,
    Actor,
    ConsolidationPayout,
    ConsolidationRequest,
    ConsolidationStatus,
    Installment,
    InstallmentKind,
    InstallmentStatus,
)
from app.money import MONEY_MAX
from app.notifications import service as notifications
from app.providers.base import Application, ConsolidationBankProvider, Payoff

logger = logging.getLogger(__name__)

PAYOFFS_DO_NOT_MATCH_PLAN = "PAYOFFS_DO_NOT_MATCH_PLAN"
# Who a manual entry's payout goes to when the user did not name its app (Session 14,
# open question 16; L72): "manual" is not a platform anyone could be paid at.
UNNAMED_PLATFORM = "unnamed_platform"
# A name the user typed that is one of the app's own vendors, or blank, names no app
# (review R2-F2): a payout never goes to "manual" (L72).
NOT_A_PLATFORM = frozenset({MANUAL_VENDOR, CONSOLIDATION_VENDOR, UNNAMED_PLATFORM, ""})
LOAN_NAME = "สินเชื่อรวมหนี้"
MONTHLY_RATE = Decimal("0.000001")  # Numeric(7,6): the loan row's rate, for display


@dataclass(frozen=True)
class Decided:
    request: ConsolidationRequest
    loan: Installment | None
    payouts: list[ConsolidationPayout]
    created: bool  # False for a repeat of a request already decided
    notification_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Conflict:
    """The same client_request_id with other payoffs."""


@dataclass(frozen=True)
class NotEligible:
    reason: str  # a plan Reason, or PAYOFFS_DO_NOT_MATCH_PLAN


def recipient(row: Installment) -> str:
    """The platform a payout for this installment goes to: for a manual entry, the
    app the user named (platform_name, Session 17), else an unnamed one (L72)."""
    if row.vendor == MANUAL_VENDOR:
        name = (row.platform_name or "").strip()
        return UNNAMED_PLATFORM if name.lower() in NOT_A_PLATFORM else name
    return row.vendor


def request_key(user_id: str, body: ConsolidationRequestIn) -> str:
    """The bank's reference for one application: the same on every submit of it, and
    different when the payoffs differ. An attempt that reached the bank but failed
    before the commit stores nothing, so its retry may name other payoffs under the
    same id, and must get a decision on those (round 2 review F1)."""
    canonical = json.dumps(
        ["consolidation", user_id, body.client_request_id, body.stored_payoffs()],
        separators=(",", ":"),
    )
    return "consolidation-" + hashlib.sha256(canonical.encode()).hexdigest()


def payout_key(user_id: str, client_request_id: str, installment_id: uuid.UUID) -> str:
    """S1 for one payout: from (user, request, installment), never from a row id,
    which a rolled-back attempt would not keep."""
    canonical = json.dumps(
        ["consolidation_payout", user_id, client_request_id, str(installment_id)],
        separators=(",", ":"),
    )
    return "payout-" + hashlib.sha256(canonical.encode()).hexdigest()


def submit(
    session: Session,
    *,
    user_id: str,
    body: ConsolidationRequestIn,
    today: date,
    settings: Settings,
    bank: ConsolidationBankProvider,
) -> Decided | Conflict | NotEligible:
    """Raises affordability.service.SettingsRequiredError without an income and
    budget, and reconcile.InvariantViolationError after rolling back."""
    earlier = _find(session, user_id, body.client_request_id)
    if earlier is not None:
        return _resubmitted(session, user_id=user_id, body=body, earlier=earlier)
    _lock_user(session, user_id)
    _lock_contracts(session, user_id)
    counted = _lock_counted(session, user_id)
    earlier = _find(session, user_id, body.client_request_id)
    if earlier is not None:
        return _resubmitted(session, user_id=user_id, body=body, earlier=earlier)

    profile = require_profile(session, user_id)
    plan = assistant.plan(session, user_id, today=today, settings=settings)
    reason = plan.consolidation.reason.value if not plan.consolidation.eligible else None
    # Open question 5: exactly the counted installments with something left to pay
    # off. A row that has ended but is still in the L43 set is not named (review F4).
    now = Month.of(today)
    required = {r.id for r in counted if remaining_for_payoff(assistant.debt_of(r), now) > 0}
    if reason is None and {p.installment_id for p in body.payoffs} != required:
        reason = PAYOFFS_DO_NOT_MATCH_PLAN
    rate = settings.consolidation_example_annual_rate
    term = settings.consolidation_example_term_months
    # L70 (b) again, on the amounts this request asks for: the plan checked its own
    # estimate, and the loan is built from these.
    requested = sum((p.payoff_amount for p in body.payoffs), Decimal("0.00"))
    requested_payment = amortised_payment(requested, rate, term)
    if reason is None and requested_payment * term > MONEY_MAX:
        reason = Reason.ESTIMATE_TOO_LARGE.value
    if reason is None and requested_payment > plan.budget:
        reason = Reason.PAYMENT_ABOVE_BUDGET.value
    if reason is None and requested_payment * 3 > profile.income:
        reason = Reason.PAYMENT_ABOVE_ONE_THIRD_OF_INCOME.value
    if reason is not None:
        _audit(session, user_id, "consolidation_not_eligible", body, {"reason": reason})
        return NotEligible(reason)

    rows = {r.id: r for r in counted}
    application = Application(
        user_id=user_id,
        reference=request_key(user_id, body),
        payoffs=tuple(
            Payoff(
                p.installment_id,
                recipient(rows[p.installment_id]),
                rows[p.installment_id].contract_id,
                p.payoff_amount,
            )
            for p in body.payoffs
        ),
        annual_rate=rate,
        term_months=term,
    )
    decision = bank.decide(application)
    if decision.approved and {p.installment_id for p in decision.payoffs} != required:
        # The bank approved other installments than were asked: never build a loan on it.
        raise RuntimeError("the bank decided on other installments than were requested")
    approved = decision.payoffs if decision.approved else application.payoffs
    principal = sum((p.amount for p in approved), Decimal("0.00"))
    payment = amortised_payment(principal, rate, term)
    request_id = uuid.uuid4()
    loan: Installment | None = None
    if decision.approved:
        loan = create_loan(
            session,
            user_id=user_id,
            request_id=request_id,
            first_month=Month.of(today).plus(1),
            principal=principal,
            payment=payment,
            rate=rate,
            term=term,
        )
        _mark_consolidated(session, user_id, [p.installment_id for p in approved])
    request = _store_request(
        session,
        request_id=request_id,
        user_id=user_id,
        body=body,
        approved=decision.approved,
        principal=principal,
        rate=rate,
        term=term,
        payment=payment,
        decision_reference=decision.reference,
        loan_id=None if loan is None else loan.id,
    )
    payouts: list[ConsolidationPayout] = []
    notification_id = None
    if loan is not None:
        payouts = _store_payouts(session, request, approved)
        notification_id = notifications.notify_consolidation_loan(
            session,
            user_id=user_id,
            installment_id=loan.id,
            payment=payment,
            term=term,
            total_cost=request.total_cost,
        )
    _audit(
        session,
        user_id,
        "consolidation_approved" if decision.approved else "consolidation_declined",
        body,
        {
            "request_id": str(request_id),
            "decision_reference": decision.reference,
            "principal": str(principal),
            "loan_installment_id": None if loan is None else str(loan.id),
        },
    )
    try:
        reconcile.assert_user_invariants(session, user_id)
    except reconcile.InvariantViolationError as exc:
        session.rollback()
        logger.error("reconcile failed, consolidation rolled back: %s", exc)
        raise
    return Decided(request, loan, payouts, created=True, notification_id=notification_id)


def pay_out(bank: ConsolidationBankProvider, payouts: list[ConsolidationPayout]) -> None:
    """Pay each platform for a committed approval, under the payout's own key, so a
    repeat pays nothing more if the first call got through."""
    for payout in payouts:
        bank.pay_out(
            vendor=payout.vendor,
            contract_id=payout.contract_id,
            amount=payout.amount,
            idempotency_key=payout.idempotency_key,
        )


def create_loan(
    session: Session,
    *,
    user_id: str,
    request_id: uuid.UUID,
    first_month: Month,
    principal: Decimal,
    payment: Decimal,
    rate: Decimal,
    term: int,
) -> Installment:
    """The consolidation_loan in the Ledger (L72). It never saves: no auto-save is
    called, and the kind is in NEVER_SAVE_KINDS (INV-5) should anything try."""
    loan = Installment(
        user_id=user_id,
        vendor=CONSOLIDATION_VENDOR,
        contract_id=str(request_id),
        kind=InstallmentKind.CONSOLIDATION_LOAN,
        item_name=LOAN_NAME,
        principal=principal,
        months=term,
        monthly_amount=payment,
        fee_total=payment * term - principal,
        first_due_date=first_month.first_day(),
        min_payment=payment,
        late_fee_per_period=None,  # the bank's late fee is unknown, never a made-up 0
        monthly_rate=(rate / 12).quantize(MONTHLY_RATE),
    )
    session.add(loan)
    session.flush()
    return loan


def _lock_user(session: Session, user_id: str) -> None:
    key = func.hashtextextended(f"consolidation:{user_id}", 0)
    session.execute(select(func.pg_advisory_xact_lock(key)))


def _lock_contracts(session: Session, user_id: str) -> None:
    """Each counted contract's lock, in a fixed order. A row counted only after this
    read is not locked by contract, but it is not in the payoffs the user could have
    named, so the request is refused as not matching."""
    contracts = session.execute(
        select(Installment.vendor, Installment.contract_id)
        .where(Installment.user_id == user_id, Installment.status.in_(OWED_STATUSES))
        .order_by(Installment.vendor, Installment.contract_id)
    ).all()
    for vendor, contract_id in contracts:
        lock_contract(session, vendor=vendor, contract_id=contract_id)


def _lock_counted(session: Session, user_id: str) -> list[Installment]:
    """The counted installments (the L43 owed set), locked in id order until commit."""
    rows = session.execute(
        select(Installment)
        .where(Installment.user_id == user_id, Installment.status.in_(OWED_STATUSES))
        .order_by(Installment.id)
        .with_for_update()
    ).scalars()
    return [row for row in rows if still_owed(row)]


def _mark_consolidated(session: Session, user_id: str, ids: list[uuid.UUID]) -> None:
    """L72: each paid-off installment keeps its row and history; only its status
    changes. Every one must still be owed: the rows are locked, so a mismatch is a bug."""
    changed = session.execute(
        update(Installment)
        .where(
            Installment.id.in_(ids),
            Installment.user_id == user_id,
            Installment.status.in_(OWED_STATUSES),
        )
        .values(status=InstallmentStatus.CONSOLIDATED)
        .returning(Installment.id)
        .execution_options(synchronize_session="fetch")
    ).scalars()
    if set(changed) != set(ids):
        raise RuntimeError("a paid-off installment changed under the consolidation lock")


def _store_request(
    session: Session,
    *,
    request_id: uuid.UUID,
    user_id: str,
    body: ConsolidationRequestIn,
    approved: bool,
    principal: Decimal,
    rate: Decimal,
    term: int,
    payment: Decimal,
    decision_reference: str,
    loan_id: uuid.UUID | None,
) -> ConsolidationRequest:
    stored = session.execute(
        pg_insert(ConsolidationRequest)
        .values(
            id=request_id,
            user_id=user_id,
            client_request_id=body.client_request_id,
            status=ConsolidationStatus.APPROVED if approved else ConsolidationStatus.DECLINED,
            payoffs=body.stored_payoffs(),
            principal=principal,
            annual_rate=rate,
            term_months=term,
            monthly_payment=payment,
            total_cost=payment * term,
            decision_reference=decision_reference,
            loan_installment_id=loan_id,
        )
        .on_conflict_do_nothing(
            index_elements=[ConsolidationRequest.user_id, ConsolidationRequest.client_request_id]
        )
        .returning(ConsolidationRequest.id)
    ).scalar_one_or_none()
    if stored is None:
        # Unreachable under the user lock; the caller's transaction rolls back
        # whatever this attempt wrote, and the client's retry finds the first one.
        raise RuntimeError("consolidation request decided concurrently")
    return session.get_one(ConsolidationRequest, stored)


def _store_payouts(
    session: Session, request: ConsolidationRequest, payoffs: tuple[Payoff, ...]
) -> list[ConsolidationPayout]:
    rows = [
        ConsolidationPayout(
            request_id=request.id,
            user_id=request.user_id,
            installment_id=p.installment_id,
            vendor=p.vendor,
            contract_id=p.contract_id,
            amount=p.amount,
            idempotency_key=payout_key(
                request.user_id, request.client_request_id, p.installment_id
            ),
        )
        for p in payoffs
    ]
    session.add_all(rows)
    session.flush()
    return rows


def _find(session: Session, user_id: str, client_request_id: str) -> ConsolidationRequest | None:
    return session.execute(
        select(ConsolidationRequest).where(
            ConsolidationRequest.user_id == user_id,
            ConsolidationRequest.client_request_id == client_request_id,
        )
    ).scalar_one_or_none()


def _resubmitted(
    session: Session, *, user_id: str, body: ConsolidationRequestIn, earlier: ConsolidationRequest
) -> Decided | Conflict:
    """The same payoffs get the first decision again and nothing is written; other
    payoffs under the same id are a conflict (as L55), audited."""
    if earlier.payoffs != body.stored_payoffs():
        _audit(
            session,
            user_id,
            "client_request_id_reused",
            body,
            {"request_id": str(earlier.id)},
        )
        return Conflict()
    loan = (
        None
        if earlier.loan_installment_id is None
        else session.get_one(Installment, earlier.loan_installment_id)
    )
    payouts = list(
        session.execute(
            select(ConsolidationPayout)
            .where(ConsolidationPayout.request_id == earlier.id)
            .order_by(ConsolidationPayout.installment_id)
        ).scalars()
    )
    return Decided(earlier, loan, payouts, created=False)


def _audit(
    session: Session,
    user_id: str,
    action: str,
    body: ConsolidationRequestIn,
    detail: dict[str, str | None],
) -> None:
    audit.record(
        session,
        actor=Actor.USER,
        action=action,
        user_id=user_id,
        ref_type="consolidation_request",
        ref_id=body.client_request_id,
        detail={"client_request_id": body.client_request_id} | detail,
    )
