"""KD-04, KD-05: the KidNee demo data (`python -m demo.kidnee`) on its own test
database, `lumen_kidnee_test`, rebuilt by Alembic. Same code path as the command:
reset, then seed through the app's services as lumen_app. "Today" is fixed at
2026-11-10. KD-05 (Session 17): each persona tells its one story."""

import contextlib
import itertools
import json
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
from app.buffer import service as buffer_service
from app.buffer.schemas import MoveIn
from app.config import get_settings
from app.db import Base, make_engine
from app.ledger import reconcile
from app.models import Installment, Notification, SavingsTransaction
from app.providers import get_bank_provider
from app.providers.mock_bank import MockBankAccountProvider
from app.providers.mock_push import MockPushProvider
from app.savings.service import move_key
from demo import kidnee as kidnee_cli
from demo.kidnee import (
    KIDNEE_DB_NAME,
    PERSONAS,
    KidneeConfig,
    ai_check,
    build,
    main_balances,
    model_config_lines,
    open_bank,
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


@pytest.fixture
def fresh_bank() -> Iterator[None]:
    """build() opens the process's one bank; each test gets a new one, and leaves none."""
    get_bank_provider.cache_clear()
    yield
    get_bank_provider.cache_clear()


def test_KD_04_the_served_api_reads_the_kidnee_database(
    kidnee: Engine, first_seed: Any, config: KidneeConfig, fresh_bank: None
) -> None:
    served = build(config, kidnee, dist=None)
    api = served.routes[0].app  # type: ignore[attr-defined]
    # Checked before any request, so a broken override never reaches another database.
    # Only the session: the bank is the process's one instance, which every path uses,
    # the webhook processor included (round 2 F2, Session 21).
    [override] = [api.dependency_overrides[k] for k in api.dependency_overrides]
    with contextlib.closing(override()) as sessions:
        assert next(sessions).get_bind().url.database == DB_NAME
    with TestClient(served) as client:
        response = client.get("/api/debts/summary", headers={"X-Demo-User": "demo-mon"})
    assert (response.status_code, response.json()["monthly_total"]) == (200, "3500.00")


def test_KD_04_the_served_main_account_opens_at_what_the_seed_left(
    fresh_bank: None, kidnee: Engine, first_seed: Any, config: KidneeConfig
) -> None:
    # The seed ran in another process, whose in-memory bank is gone. Served, each
    # persona's main account opens at its opening balance (10,000.00; demo-over
    # 10,700.00) minus the savings its rows list, so the balance on บัญชีหลัก agrees
    # with the movements under it (review F2, Session 21).
    served = build(config, kidnee, dist=None)
    with TestClient(served) as client:
        bodies = {
            user: client.get("/api/bank/main-account", headers={"X-Demo-User": user}).json()
            for user in PERSONAS
        }
    assert {user: body["balance"] for user, body in bodies.items()} == {
        "demo-mon": "7300.00",  # 10,000.00 - 1,200.00 - 1,500.00
        "demo-over": "5000.00",  # 10,700.00 - 5,700.00
        "demo-consolidate": "8500.00",  # - 1,500.00
    }
    openings = {"demo-mon": "10000.00", "demo-over": "10700.00", "demo-consolidate": "10000.00"}
    for user, body in bodies.items():
        listed = sum(Decimal(m["amount"]) for m in body["movements"])
        assert Decimal(body["balance"]) == Decimal(openings[user]) - listed
    # The one bank every path uses (a webhook's auto-save too) holds the opened balance.
    assert get_bank_provider().get_balance("demo-over") == Decimal("5000.00")


def test_KD_04_a_move_in_the_rows_is_not_credited_again_on_its_retry(kidnee: Engine) -> None:
    # A move commits its row before the bank credit. If serve restarts in between, the
    # opened balance already counts it, so the retry (same client_request_id, DUPLICATE)
    # must not credit it again (round 2 F1).
    bank = MockBankAccountProvider()
    with Session(kidnee) as session:
        session.add(
            SavingsTransaction(
                user_id="demo-mon",
                type="withdrawal",
                amount=Decimal("700.00"),
                client_request_id="kd-retry",
            )
        )
        session.flush()
        open_bank(session, bank)
        session.rollback()
    assert bank.get_balance("demo-mon") == Decimal("8000.00")  # 10,000 - 2,700 + 700
    bank.transfer_from_savings(
        "demo-mon", Decimal("700.00"), idempotency_key=move_key("demo-mon", "kd-retry")
    )
    assert bank.get_balance("demo-mon") == Decimal("8000.00")


def test_KD_04_savings_above_the_opening_balance_keep_the_default_and_never_stop_serve(
    kidnee: Engine, capsys: pytest.CaptureFixture[str]
) -> None:
    # Rows from serves before Session 21 (each opened at 10,000.00) can add up to more.
    bank = MockBankAccountProvider()
    with Session(kidnee) as session:
        session.add_all(
            SavingsTransaction(
                user_id="kd-old", type="leftover_save", amount=Decimal("6000.00"), payday_month=m
            )
            for m in (date(2026, 9, 1), date(2026, 10, 1))
        )
        session.flush()
        open_bank(session, bank)
        session.rollback()
    assert bank.get_balance("kd-old") == Decimal("10000.00")
    assert bank.get_balance("demo-mon") == Decimal("7300.00")
    assert (
        "kd-old: savings exceed the opening balance; run reset to refresh"
        in capsys.readouterr().out
    )


def test_KD_04_a_move_to_main_adds_back_and_a_leftover_takes_out(kidnee: Engine) -> None:
    with Session(kidnee) as session:
        session.add_all(
            [
                SavingsTransaction(
                    user_id="demo-mon",
                    type="withdrawal",
                    amount=Decimal("700.00"),
                    client_request_id="kd-move",
                ),
                SavingsTransaction(
                    user_id="demo-mon",
                    type="leftover_save",
                    amount=Decimal("100.00"),
                    payday_month=date(2026, 10, 1),
                ),
            ]
        )
        session.flush()
        opened = main_balances(session)
        session.rollback()  # the module's data stays as seeded
    # 10,000.00 - 2,700.00 saved + 700.00 moved back - 100.00 leftover
    assert opened["demo-mon"] == Decimal("7900.00")


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


def test_KD_05_over_ends_able_to_pay_this_month_after_using_the_buffer(
    kidnee: Engine, first_seed: Any
) -> None:
    # The demo's last scene: ใช้กันชน moves this month's shortfall back to บัญชีหลัก,
    # which then holds exactly this month's total, not less (5,000.00 + 1,500.00).
    this_month = shortfalls(kidnee, "demo-over").months[0]
    total = plan(kidnee, "demo-over").rows[0].total
    move = {"client_request_id": "kd-05-over", "amount": str(this_month.shortfall)}
    with Session(kidnee) as session:
        before = main_balances(session)["demo-over"]
        moved = buffer_service.move_to_main(
            session,
            user_id="demo-over",
            request=MoveIn.model_validate_json(json.dumps(move | {"for_month": "2026-11"})),
        )
        session.flush()
        after = main_balances(session)["demo-over"]
        session.rollback()  # the module's data stays as seeded
    assert moved is not None
    assert moved.outcome is buffer_service.Outcome.CREATED
    assert (before, this_month.shortfall, after, total) == (
        Decimal("5000.00"),
        Decimal("1500.00"),
        Decimal("6500.00"),
        Decimal("6500.00"),
    )


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


# ---- Session 23 review F1: serve opens the bank once, so it needs the seed first ----


def _no_server(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record build and uvicorn.run instead of starting anything."""
    calls: list[str] = []
    monkeypatch.setattr(kidnee_cli, "build", lambda *_a, **_k: calls.append("build"))
    monkeypatch.setattr(
        kidnee_cli.uvicorn, "run", lambda *_a, **k: calls.append(f"run {k['host']}")
    )
    return calls


def test_KD_04_serve_refuses_to_start_before_the_personas_are_seeded(
    config: KidneeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The bank opens from the rows only in build: a seed after it would leave
    # demo-over at 10,000.00 with 5,700.00 of savings in its movements.
    calls = _no_server(monkeypatch)
    monkeypatch.setattr(kidnee_cli, "personas_present", lambda _engine: ["demo-mon"])
    with pytest.raises(
        SystemExit, match=r"Not seeded yet: demo-over, demo-consolidate\. Run .* seed first"
    ):
        kidnee_cli.serve(config)
    assert calls == []


def test_KD_04_serve_starts_once_every_persona_is_seeded(
    config: KidneeConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _no_server(monkeypatch)
    monkeypatch.setattr(kidnee_cli, "personas_present", lambda _engine: sorted(PERSONAS))
    kidnee_cli.serve(config)
    assert calls == ["build", "run 127.0.0.1"]


@pytest.mark.parametrize("argv", [["seed"], ["reset", "--yes"]])
def test_KD_04_seed_and_reset_say_to_restart_a_running_serve(
    argv: list[str],
    config: KidneeConfig,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    done: list[str] = []
    monkeypatch.setattr(KidneeConfig, "from_env", classmethod(lambda _cls: config))
    monkeypatch.setattr(kidnee_cli, "create_if_missing", lambda _c: done.append("create"))
    monkeypatch.setattr(kidnee_cli, "migrate", lambda _c: done.append("migrate"))
    monkeypatch.setattr(kidnee_cli, "reset_database", lambda _c, _n: done.append("reset"))
    monkeypatch.setattr(kidnee_cli, "seed_database", lambda _c, day: {"demo-mon": ["seeded"]})
    kidnee_cli.main(argv)
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == kidnee_cli.RESTART_SERVE
    assert "stop it and start it again" in out
    assert done == (["reset"] if argv[0] == "reset" else ["create", "migrate"])
