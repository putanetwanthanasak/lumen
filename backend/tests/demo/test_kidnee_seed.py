"""KD-04, KD-05: the KidNee demo data (`python -m demo.kidnee`) on its own test
database, `lumen_kidnee_test`, rebuilt by Alembic. Same code path as the command:
reset, then seed through the app's services as lumen_app. "Today" is fixed at
2026-11-10. KD-05 (Session 17): each persona tells its one story."""

import contextlib
import itertools
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.assistant import service as assistant
from app.config import get_settings
from app.db import Base, make_engine
from app.ledger import reconcile
from app.models import Installment, Notification, SavingsTransaction
from app.providers.mock_bank import MockBankAccountProvider
from app.providers.mock_push import MockPushProvider
from demo.kidnee import (
    KIDNEE_DB_NAME,
    PERSONAS,
    KidneeConfig,
    ai_check,
    build,
    model_config_lines,
    seconds,
    seed,
)
from demo.script import reset_database
from tests.ai.fakes import FakeWriter

pytestmark = pytest.mark.db

DB_NAME = "lumen_kidnee_test"
DAY = date(2026, 11, 10)


@pytest.fixture(scope="module")
def config(test_db_url: str, test_migration_db_url: str) -> KidneeConfig:
    return KidneeConfig(test_db_url, test_migration_db_url, db_name=DB_NAME)


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
        return seed(session, day=DAY, bank=MockBankAccountProvider(), push=MockPushProvider())


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
        "demo-mon": [
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
            "earbuds: created, saved 240.00",
            "fridge: created, saved 300.00",
            "motorbike: created, saved 960.00",
        ],
    }
    with Session(kidnee) as session:
        for user in PERSONAS:
            reconcile.assert_user_invariants(session, user)
        # One alert per recorded installment (L58), as POST /installments stores it.
        assert session.scalar(select(func.count()).select_from(Notification)) == 8
        # Delivered as POST /installments does after commit (review F4): none left pending.
        statuses = set(session.scalars(select(Notification.delivery_status)))
        assert statuses == {"pushed"}
        assert session.scalar(select(func.sum(SavingsTransaction.amount))) == Decimal(
            "9900.00"
        )  # 10%: 2 x 1,200 + 2 x 1,500 + 3,000; 2%: 240 + 300 + 960


def test_KD_04_mon_is_in_budget_every_month(kidnee: Engine, first_seed: Any) -> None:
    result = plan(kidnee, "demo-mon")
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
        again = seed(session, day=DAY, bank=MockBankAccountProvider(), push=MockPushProvider())
    assert again["demo-mon"] == [
        "settings kept",
        "earbuds: duplicate, saved 1200.00",
        "fridge: duplicate, saved 1500.00",
    ]
    assert counts(kidnee) == before


def test_KD_04_a_seed_in_another_month_never_overwrites(kidnee: Engine, first_seed: Any) -> None:
    before = counts(kidnee)
    with Session(kidnee) as session:
        later = seed(
            session, day=date(2026, 12, 1), bank=MockBankAccountProvider(), push=MockPushProvider()
        )
    assert later["demo-mon"][1] == "earbuds: seeded in another month, run reset to refresh"
    # Only the audit rows of the refused requests are new (as POST /installments' 409).
    after = counts(kidnee)
    assert {k: v for k, v in after.items() if v != before[k]} == {
        "audit_log": before["audit_log"] + 8  # one per installment (8)
    }


def test_KD_04_the_served_api_reads_the_kidnee_database(
    kidnee: Engine, first_seed: Any, config: KidneeConfig
) -> None:
    served = build(config, kidnee, dist=None)
    api = served.routes[0].app  # type: ignore[attr-defined]
    # Checked before any request, so a broken override never reaches another database.
    [override] = [api.dependency_overrides[k] for k in api.dependency_overrides]
    with contextlib.closing(override()) as sessions:
        assert next(sessions).get_bind().url.database == DB_NAME
    with TestClient(served) as client:
        response = client.get("/api/debts/summary", headers={"X-Demo-User": "demo-mon"})
    assert (response.status_code, response.json()["monthly_total"]) == (200, "3500.00")


# --- KD-05: one story per persona (Session 17) ---------------------------------------------


def shortfalls(kidnee: Engine, user: str) -> Any:
    with Session(kidnee) as session:
        return assistant.buffer_shortfalls(session, user, today=DAY)


def test_KD_05_mon_is_in_budget_with_a_modest_buffer(kidnee: Engine, first_seed: Any) -> None:
    result = shortfalls(kidnee, "demo-mon")
    assert (result.months, result.buffer.shortfall, result.buffer.balance) == (
        [],
        Decimal("0.00"),
        Decimal("2700.00"),
    )


def test_KD_05_over_is_over_this_month_and_its_buffer_clearly_covers_it(
    kidnee: Engine, first_seed: Any
) -> None:
    result = shortfalls(kidnee, "demo-over")
    assert str(result.months[0].month) == "2026-11"  # over budget this month
    buffer = result.buffer
    assert (buffer.shortfall, buffer.balance, buffer.covered) == (
        Decimal("3000.00"),
        Decimal("5700.00"),
        True,
    )
    assert buffer.balance >= 2 * buffer.shortfall - Decimal("300.00")  # clearly, not just


def test_KD_05_consolidate_has_a_long_run_and_a_small_buffer(
    kidnee: Engine, first_seed: Any
) -> None:
    result = shortfalls(kidnee, "demo-consolidate")
    assert len(result.months) == 9
    buffer = result.buffer
    assert (buffer.shortfall, buffer.balance, buffer.covered, buffer.still_short) == (
        Decimal("10500.00"),  # 3 x 2,500 + 6 x 500
        Decimal("1500.00"),
        False,
        Decimal("9000.00"),
    )
    estimate = plan(kidnee, "demo-consolidate").consolidation.estimate
    assert estimate is not None
    assert estimate.monthly_reduction > 0


def test_KD_05_platform_names_are_fictional_and_one_item_is_unnamed(
    kidnee: Engine, first_seed: Any
) -> None:
    with Session(kidnee) as session:
        names = dict(
            session.execute(
                select(Installment.item_name, Installment.platform_name).distinct()
            ).all()  # not dict(result): a Result has .keys()
        )
    assert names == {
        "หูฟังไร้สาย": "ShopDemo",
        "ตู้เย็น": None,
        "โน้ตบุ๊ก": "ShopDemo",
        "มอเตอร์ไซค์": "RideDemo",
    }


# --- AI-25: python -m demo.kidnee ai-check, with a fake model ----------------------------


def test_AI_25_ai_check_asks_once_per_persona_and_prints_source_reason_and_text(
    kidnee: Engine, first_seed: dict[str, list[str]]
) -> None:
    writer = FakeWriter(text="ค่อย ๆ ดูแลค่างวดไปด้วยกัน\nกันชนช่วยได้")
    ticks = itertools.count(0, 1_250_000_000)  # each persona: 1.25 s between two reads
    report = ai_check(kidnee, day=DAY, writer=writer, clock=lambda: next(ticks))
    assert list(report) == list(PERSONAS)
    assert len(writer.calls) == 3  # one call per persona, never cached across them
    for lines in report.values():
        assert lines == [
            "source: ai",
            "reason: ok",
            "seconds: 1.3",  # the call and the check, to a tenth (to compare models)
            "text:",
            "  ค่อย ๆ ดูแลค่างวดไปด้วยกัน",
            "  กันชนช่วยได้",
        ]


def test_AI_25_ai_check_shows_why_the_check_refused_the_model_text(
    kidnee: Engine, first_seed: dict[str, list[str]]
) -> None:
    report = ai_check(kidnee, day=DAY, writer=FakeWriter(text="ค่างวดรวม 123.45 บาท"))
    lines = report["demo-mon"]
    assert lines[:2] == ["source: fallback", "reason: grounding_failed"]
    assert lines[3:5] == ["text:", "  ค่างวดทุกเดือนอยู่ในงบ เดือนนี้รวม 3,500 บาท จากงบ 5,000 บาท"]
    assert lines[-3:] == [
        "check: number_not_in_input (123.45)",
        "model text (refused):",
        "  ค่างวดรวม 123.45 บาท",
    ]


@pytest.mark.parametrize(
    ("nanoseconds", "shown"),
    [
        (0, "0.0"),
        (49_999_999, "0.0"),
        (50_000_000, "0.1"),
        (1_850_000_000, "1.9"),
        (12_345_000_000, "12.3"),
    ],
)
def test_AI_25_seconds_to_a_tenth_without_floats(nanoseconds: int, shown: str) -> None:
    assert seconds(nanoseconds) == shown


def test_AI_25_ai_check_without_a_key_says_so_and_never_prints_a_key(
    kidnee: Engine, first_seed: dict[str, list[str]]
) -> None:
    report = ai_check(kidnee, day=DAY, writer=None)
    assert {lines[1] for lines in report.values()} == {"reason: no_key"}
    unset = get_settings().model_copy(update={"llm_api_key": None, "llm_model_planner": None})
    assert model_config_lines(unset)[:2] == [
        "LLM_API_KEY: not set",
        "LLM_MODEL_PLANNER: claude-haiku-5-5 (default)",
    ]
    key = "sk-test-NOT-A-REAL-KEY"
    with_key = get_settings().model_copy(update={"llm_api_key": SecretStr(key)})
    lines = model_config_lines(with_key)
    assert lines[0] == "LLM_API_KEY: set"
    assert all(key not in line for line in lines)
