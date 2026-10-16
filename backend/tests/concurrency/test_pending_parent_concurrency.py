"""OR-01 under concurrency: payments racing their own created event.

A payment that finds no installment is stored as pending_parent and replayed when the
created event commits (04 step 5f). Without a per-contract lock, the created
transaction can look for pending events before a racing payment has committed its
pending row, and the payment then waits forever. ledger.lock_contract serialises them.

Demo:  cd backend && uv run pytest -m concurrency -v
"""

from collections import Counter
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ledger.reconcile import check_user_invariants
from app.models import Installment, WebhookEvent
from tests.concurrency.conftest import Race
from tests.processing.conftest import created
from tests.webhooks.payloads import payload

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

PAYMENTS = 5


def test_OR_01_payments_racing_their_created_event_are_all_applied(race: Race) -> None:
    contract = race.id("c_1")
    events = [created(race.id("evt_c"), contract, "1000.00", user=race.user)] + [
        payload(
            "installment_payment_collected",
            event_id=race.id(f"evt_p{n}"),
            user_ref=race.user,
            contract_id=contract,
            amount="100.00",
            installment_no=n,
        )
        for n in range(1, PAYMENTS + 1)
    ]

    responses = race.fire(events)

    # Each payment is applied live (200) or stored and replayed (202), never lost.
    assert responses[0].status_code == 200
    assert {r.status_code for r in responses[1:]} <= {200, 202}
    with race.session() as s:
        paid = s.execute(
            select(Installment.paid_amount).where(Installment.contract_id == contract)
        ).scalar_one()
        assert paid == Decimal("100.00") * PAYMENTS
        statuses = s.scalars(
            select(WebhookEvent.status).where(WebhookEvent.user_id == race.user)
        ).all()
        assert Counter(statuses) == {"processed": PAYMENTS + 1}
        assert check_user_invariants(s, race.user) == []
