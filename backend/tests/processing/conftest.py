"""Helpers for service-level processing tests: real Postgres, rolled back per test.

Events go through parse_event and process_event, the same calls the router makes,
with a fresh in-memory bank per test.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import SavingsTransaction, UserBalance, UserSettings
from app.providers.mock_bank import MockBankAccountProvider
from app.schemas import parse_event
from app.webhooks.processor import Outcome, process_event
from tests.webhooks.payloads import encode, payload

VENDOR = "shopdemo"
USER = "user_a"  # the user_ref in tests.webhooks.payloads
CONSENT_AT = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def bank() -> MockBankAccountProvider:
    return MockBankAccountProvider()


def opt_in(
    session: Session, user: str = USER, *, enabled: bool = True, consent: bool = True
) -> None:
    session.add(
        UserSettings(
            user_id=user, auto_save_enabled=enabled, consent_at=CONSENT_AT if consent else None
        )
    )
    session.flush()


def created(
    event_id: str,
    contract_id: str,
    principal: str = "800.00",
    *,
    event_type: str = "installment_created",
    user: str = USER,
    **contract: Any,
) -> dict[str, Any]:
    """A valid *_created payload; kind follows event_type."""
    data = payload(event_type, event_id=event_id, user_ref=user)
    data["contract"] |= {"contract_id": contract_id, "principal": principal} | contract
    return data


def run(
    session: Session, data: dict[str, Any], bank: MockBankAccountProvider, vendor: str = VENDOR
) -> Outcome:
    body = encode(data)
    return process_event(session, vendor=vendor, event=parse_event(body), payload=data, bank=bank)


def auto_saves(session: Session, user: str = USER) -> list[SavingsTransaction]:
    return list(
        session.execute(
            select(SavingsTransaction).where(SavingsTransaction.user_id == user)
        ).scalars()
    )


def balance(session: Session, user: str = USER) -> tuple[Decimal, int] | None:
    row = session.execute(
        select(UserBalance.savings_balance, UserBalance.version).where(UserBalance.user_id == user)
    ).one_or_none()
    return None if row is None else (row[0], row[1])


def count(session: Session, model: type[Base]) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()
