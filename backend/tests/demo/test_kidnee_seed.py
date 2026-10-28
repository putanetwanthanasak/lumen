"""KD-04: the KidNee demo data (`python -m demo.kidnee`) on its own test database,
`lumen_kidnee_test`, rebuilt by Alembic. Same code path as the command: reset, then
seed through the app's services as lumen_app. "Today" is fixed at 2026-11-10."""

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.assistant import service as assistant
from app.config import get_settings
from app.db import Base, make_engine
from app.ledger import reconcile
from app.models import Notification, SavingsTransaction
from app.providers.mock_bank import MockBankAccountProvider
from demo.kidnee import KIDNEE_DB_NAME, PERSONAS, KidneeConfig, seed
from demo.script import reset_database

pytestmark = pytest.mark.db

DB_NAME = "lumen_kidnee_test"
DAY = date(2026, 11, 10)


@pytest.fixture(scope="module")
def kidnee(migration_engine: Any, test_db_url: str, test_migration_db_url: str) -> Iterator[Engine]:
    config = KidneeConfig(test_db_url, test_migration_db_url, db_name=DB_NAME)
    reset_database(config, KIDNEE_DB_NAME)
    engine = make_engine(config.url(test_db_url))
    yield engine
    engine.dispose()
    admin = make_engine(test_migration_db_url).execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)'))
    admin.dispose()


@pytest.fixture(scope="module")
def first_seed(kidnee: Engine) -> dict[str, list[str]]:
    with Session(kidnee) as session:
        return seed(session, day=DAY, bank=MockBankAccountProvider())


def plan(kidnee: Engine, user: str) -> Any:
    with Session(kidnee) as session:
        return assistant.plan(session, user, today=DAY, settings=get_settings())


def counts(kidnee: Engine) -> dict[str, int]:
    with Session(kidnee) as session:
        return {
            t.name: session.execute(select(func.count()).select_from(t)).scalar_one()
            for t in Base.metadata.sorted_tables
        }


def test_KD_04_seed_records_every_persona_with_its_savings(
    kidnee: Engine, first_seed: dict[str, list[str]]
) -> None:
    assert first_seed == {
        "demo-mint": [
            "settings created",
            "earbuds: created, saved 1200.00",
            "fridge: created, saved 1500.00",
        ],
        "demo-over": [
            "settings created",
            "earbuds: created, saved 1200.00",
            "fridge: created, saved 1500.00",
            "laptop: created, saved 3000.00",
        ],
        "demo-consolidate": [
            "settings created",
            "earbuds: created, saved 1200.00",
            "fridge: created, saved 1500.00",
            "motorbike: created, saved 4800.00",
        ],
    }
    with Session(kidnee) as session:
        for user in PERSONAS:
            reconcile.assert_user_invariants(session, user)
        # One alert per recorded installment (L58), as POST /installments stores it.
        assert session.scalar(select(func.count()).select_from(Notification)) == 8
        assert session.scalar(select(func.sum(SavingsTransaction.amount))) == Decimal(
            "15900.00"
        )  # 3 x 1,200 + 3 x 1,500 + 3,000 + 4,800


def test_KD_04_mint_is_in_budget_every_month(kidnee: Engine, first_seed: Any) -> None:
    result = plan(kidnee, "demo-mint")
    assert [str(r.total) for r in result.rows[:3]] == ["3500.00", "3500.00", "3500.00"]
    assert not any(r.over_budget for r in result.rows)
    assert result.consolidation.reason == "NOT_NEEDED"
    assert result.buffer.balance == Decimal("2700.00")


def test_KD_04_over_persona_is_over_budget_now_but_not_eligible(
    kidnee: Engine, first_seed: Any
) -> None:
    result = plan(kidnee, "demo-over")
    assert [(str(r.month), str(r.total), r.over_budget) for r in result.rows[:3]] == [
        ("2026-11", "6500.00", True),
        ("2026-12", "6500.00", True),
        ("2027-01", "4500.00", False),
    ]
    assert str(result.pause_until) == "2027-01"
    assert result.consolidation.reason == "NOT_NEEDED"  # 2 months, not 3 in a row
    assert result.buffer.shortfall == Decimal("3000.00")


def test_KD_04_consolidate_persona_is_eligible(kidnee: Engine, first_seed: Any) -> None:
    result = plan(kidnee, "demo-consolidate")
    over = [str(r.month) for r in result.rows if r.over_budget]
    assert over == [f"2026-{m}" for m in ("11", "12")] + [f"2027-0{m}" for m in range(1, 8)]
    assert result.consolidation.reason == "ELIGIBLE"


def test_KD_04_a_second_seed_changes_nothing(kidnee: Engine, first_seed: Any) -> None:
    before = counts(kidnee)
    with Session(kidnee) as session:
        again = seed(session, day=DAY, bank=MockBankAccountProvider())
    assert again["demo-mint"] == [
        "settings kept",
        "earbuds: duplicate, saved 1200.00",
        "fridge: duplicate, saved 1500.00",
    ]
    assert counts(kidnee) == before


def test_KD_04_a_seed_in_another_month_never_overwrites(kidnee: Engine, first_seed: Any) -> None:
    before = counts(kidnee)
    with Session(kidnee) as session:
        later = seed(session, day=date(2026, 12, 1), bank=MockBankAccountProvider())
    assert later["demo-mint"][1] == "earbuds: seeded in another month, run reset to refresh"
    # Only the audit rows of the refused requests are new (as POST /installments' 409).
    after = counts(kidnee)
    assert {k: v for k, v in after.items() if v != before[k]} == {
        "audit_log": before["audit_log"] + 8  # one per installment (8)
    }
