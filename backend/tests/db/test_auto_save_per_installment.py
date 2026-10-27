"""ID-05 at the savings layer: one installment gets at most one auto_save.

INV-3 (unique per event_id) alone does not cover a platform that resends the same
contract under a new event_id. The installment UNIQUE (vendor, contract_id) blocks
the second installment row, but only this index blocks a second saving for it.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from tests.db.factories import add_auto_save_parents, add_event, add_installment, savings_tx
from tests.db.test_constraints import assert_accepted, assert_rejected

pytestmark = pytest.mark.db


def test_ID_05_auto_save_unique_per_installment(db_session: Session) -> None:
    inst = add_auto_save_parents(db_session, "evt-1", "c-1")
    add_event(db_session, "evt-2")  # same contract resent under a new event_id
    assert_accepted(db_session, savings_tx(source_event_id="evt-1", installment_id=inst))
    assert_rejected(
        db_session,
        savings_tx(source_event_id="evt-2", installment_id=inst, amount=Decimal("10.00")),
        "uq_savings_transactions_auto_save_installment_id",
    )


def test_auto_save_requires_installment(db_session: Session) -> None:
    add_event(db_session, "evt-1")
    assert_rejected(
        db_session,
        savings_tx(source_event_id="evt-1", installment_id=None),
        "ck_savings_transactions_auto_save_has_installment",
    )


def test_auto_save_installment_must_exist(db_session: Session) -> None:
    add_event(db_session, "evt-1")
    assert_rejected(
        db_session,
        savings_tx(source_event_id="evt-1", installment_id=uuid.uuid4()),
        "fk_savings_transactions_installment_id_installments",
    )


def test_withdrawals_need_no_installment(db_session: Session) -> None:
    add_installment(db_session)
    for n in range(2):
        assert_accepted(
            db_session,
            savings_tx(
                type="withdrawal",
                source_vendor=None,
                source_event_id=None,
                installment_id=None,
                client_request_id=f"move-{n}",
            ),
        )
