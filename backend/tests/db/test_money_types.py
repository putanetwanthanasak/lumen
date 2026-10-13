"""Money is Numeric(12,2) and rates Numeric(7,6), always read back as Decimal."""

from decimal import Decimal

import pytest
from sqlalchemy import Float, Numeric, select, text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Installment, UserSettings
from tests.db.factories import installment, user_settings

pytestmark = pytest.mark.db

RATE_COLUMNS = {("installments", "monthly_rate"), ("user_settings", "save_rate")}


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
    assert len(cols) == 12  # installments 7, user_settings 3, savings 1, balances 1
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
    db_session.add(user_settings(save_rate=Decimal("0.035"), per_item_cap=Decimal("75.50")))
    db_session.flush()
    rate, cap = db_session.execute(
        text("SELECT save_rate, per_item_cap FROM user_settings WHERE user_id = :uid"),
        {"uid": "user-1"},
    ).one()
    assert type(rate) is Decimal
    assert rate == Decimal("0.035000")
    assert type(cap) is Decimal
    assert cap == Decimal("75.50")


def test_server_default_money_is_decimal(db_session: Session) -> None:
    db_session.add(user_settings())
    db_session.flush()
    db_session.expire_all()
    row = db_session.get_one(UserSettings, "user-1")
    assert type(row.per_item_cap) is Decimal
    assert type(row.save_rate) is Decimal


def test_money_overflow_rejected(db_session: Session) -> None:
    db_session.add(installment(principal=Decimal("10000000000.00")))  # 11 integer digits
    with pytest.raises(DataError):
        db_session.flush()
