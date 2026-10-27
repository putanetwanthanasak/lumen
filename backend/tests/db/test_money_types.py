"""Money is Numeric(12,2) and rates Numeric(7,6), always read back as Decimal."""

from decimal import Decimal

import pytest
from sqlalchemy import Float, Numeric, select, text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Installment, UserSettings
from tests.db.factories import installment, profile, user_settings

pytestmark = pytest.mark.db

RATE_COLUMNS = {("installments", "monthly_rate")}


def _numeric_columns() -> list[tuple[str, str, Numeric[Decimal]]]:
    cols = []
    for table in Base.metadata.tables.values():
        for col in table.columns:
            assert not isinstance(col.type, Float), f"{table.name}.{col.name} is a float"
            if isinstance(col.type, Numeric):
                cols.append((table.name, col.name, col.type))
    return cols


def test_money_columns_are_numeric_12_2_and_rates_7_6() -> None:
    cols = _numeric_columns()
    assert len(cols) == 17  # installments 8, user_settings 3, savings 1, balances 1,
    # payday_runs 4
    for table, name, typ in cols:
        expected = (7, 6) if (table, name) in RATE_COLUMNS else (12, 2)
        assert (typ.precision, typ.scale) == expected, f"{table}.{name}"
        assert typ.asdecimal is True, f"{table}.{name}"


def test_money_and_rate_roundtrip_as_decimal(db_session: Session) -> None:
    row = installment(principal=Decimal("1234.56"), monthly_rate=Decimal("0.020833"))
    db_session.add(row)
    db_session.flush()
    db_session.expire_all()

    loaded = db_session.scalars(select(Installment).where(Installment.id == row.id)).one()
    assert type(loaded.principal) is Decimal
    assert loaded.principal == Decimal("1234.56")
    assert type(loaded.monthly_rate) is Decimal
    assert loaded.monthly_rate == Decimal("0.020833")


def test_raw_driver_returns_decimal(db_session: Session) -> None:
    db_session.add(installment(monthly_rate=Decimal("0.035"), fee_total=Decimal("75.50")))
    db_session.flush()
    rate, fee = db_session.execute(
        text("SELECT monthly_rate, fee_total FROM installments WHERE contract_id = :cid"),
        {"cid": "c-1"},
    ).one()
    assert type(rate) is Decimal
    assert rate == Decimal("0.035000")
    assert type(fee) is Decimal
    assert fee == Decimal("75.50")


def test_server_default_money_is_decimal(db_session: Session) -> None:
    row = installment()
    del row.fee_total, row.paid_amount  # let the server defaults apply
    db_session.add(row)
    db_session.flush()
    db_session.expire_all()
    loaded = db_session.get_one(Installment, row.id)
    assert type(loaded.fee_total) is Decimal
    assert type(loaded.paid_amount) is Decimal


def test_nullable_money_roundtrips_as_decimal(db_session: Session) -> None:
    db_session.add(user_settings(**profile(fixed="12.50")))
    db_session.flush()
    db_session.expire_all()
    row = db_session.get_one(UserSettings, "user-1")
    for value in (row.monthly_installment_budget, row.income, row.saving_fixed_amount):
        assert type(value) is Decimal
    assert row.saving_fixed_amount == Decimal("12.50")


def test_money_overflow_rejected(db_session: Session) -> None:
    db_session.add(installment(principal=Decimal("10000000000.00")))  # 11 integer digits
    with pytest.raises(DataError):
        db_session.flush()


def test_L3_postgres_rounds_extra_decimals_on_insert(db_session: Session) -> None:
    # Documents a hazard, not a feature: Numeric(12,2) rounds 123.455 to 123.46 with
    # no error. This is why app.money rejects a third decimal place before any insert.
    db_session.add(installment(principal=Decimal("123.455")))
    db_session.flush()
    stored = db_session.execute(
        text("SELECT principal FROM installments WHERE contract_id = :cid"), {"cid": "c-1"}
    ).scalar_one()
    assert stored == Decimal("123.46")
