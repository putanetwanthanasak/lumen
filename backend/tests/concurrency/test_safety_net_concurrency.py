"""RE-07 under concurrency (review R3): the 500.00 safety net holds when two different
purchases for the same user arrive at the same instant.

Bank 600.00, two purchases of 800.00, each would save 80.00. Alone, either passes
(600 - 80 = 520 >= 500). Together they must not: after the first transfer the bank is
520.00 and the second fails the check (520 - 80 = 440 < 500). Without a per-user lock
both read 600.00 and the bank ends at 440.00.

Demo:  cd backend && uv run pytest -m concurrency -v
"""

from collections import Counter
from decimal import Decimal

import pytest
from psycopg.errors import LockNotAvailable
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.ledger.reconcile import check_user_invariants
from app.models import Installment, SavingsTransaction, UserBalance
from app.providers.mock_bank import MockBankAccountProvider
from tests.concurrency.conftest import Race
from tests.processing.conftest import created, run

pytestmark = [pytest.mark.db, pytest.mark.concurrency]

PROTECTED_MIN = Decimal("500.00")


@pytest.mark.parametrize("has_balance_row", [True, False], ids=["saved_before", "first_saving"])
def test_RE_07_safety_net_holds_for_concurrent_purchases_of_one_user(
    race: Race, has_balance_row: bool
) -> None:
    race.bank.set_balance(race.user, Decimal("600.00"))
    if has_balance_row:
        # The R3 case. With no row yet, the second INSERT ... ON CONFLICT waits on the
        # first one's uncommitted index entry, which hides a missing lock.
        with race.session() as s, s.begin():
            s.add(UserBalance(user_id=race.user))
    events = [
        created(race.id(f"evt_{i}"), race.id(f"c_{i}"), "800.00", user=race.user) for i in (1, 2)
    ]

    responses = race.fire(events)

    # Both purchases are recorded; only the saving is skipped (advisory, rule 6).
    assert Counter((r.status_code, r.json()["status"]) for r in responses) == {
        (200, "processed"): 2
    }
    with race.session() as s:
        user = race.user
        assert len(s.scalars(select(Installment.id).where(Installment.user_id == user)).all()) == 2
        amounts = s.scalars(
            select(SavingsTransaction.amount).where(SavingsTransaction.user_id == user)
        ).all()
        assert amounts == [Decimal("80.00")]
        row = s.execute(select(UserBalance).where(UserBalance.user_id == user)).scalar_one()
        assert (row.savings_balance, row.version) == (Decimal("80.00"), 1)
        assert check_user_invariants(s, user) == []
    final = race.bank.get_balance(race.user)
    assert final >= PROTECTED_MIN
    assert final == Decimal("520.00")


class LockProbingBank(MockBankAccountProvider):
    """Before answering get_balance, tries to lock the user's balance row from another
    connection and records whether that was refused."""

    def __init__(self, race: Race) -> None:
        super().__init__()
        self.race = race
        self.locked_at_read: list[bool] = []

    def get_balance(self, user_id: str) -> Decimal:
        with self.race.session() as other:
            try:
                other.execute(
                    select(UserBalance.user_id)
                    .where(UserBalance.user_id == user_id)
                    .with_for_update(nowait=True)
                )
                self.locked_at_read.append(False)
            except OperationalError as exc:
                self.locked_at_read.append(isinstance(exc.orig, LockNotAvailable))
        return super().get_balance(user_id)


def test_R3_balance_row_locked_before_bank_balance_is_read(race: Race) -> None:
    """Deterministic companion to the race above, which catches a missing lock in only
    some runs: the safety-net read must happen while this user's row is locked. The
    row exists (saved before); _credit's UPDATE locks it too, but only after the read."""
    with race.session() as s, s.begin():
        s.add(UserBalance(user_id=race.user))
    bank = LockProbingBank(race)
    with race.session() as session:
        run(session, created(race.id("evt_1"), race.id("c_1"), user=race.user), bank)
        session.rollback()
    assert bank.locked_at_read == [True]
