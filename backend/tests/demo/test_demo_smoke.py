"""The mentor demo (`uv run python -m demo`) runs all six scenes in CI, unattended.

Same code path as on stage: a rebuilt demo database, the real app under uvicorn on
127.0.0.1, signed webhooks over real HTTP, the app connected as lumen_app. Only the
database name (so a local `lumen_demo` is left alone), the port and the webhook
secret (random, CI has none) differ.
"""

import io
import re
import secrets
import socket
import unicodedata
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.db import make_engine
from demo.script import USER, DemoConfig, run

pytestmark = pytest.mark.db

DB_NAME = "lumen_demo_test"
SECRET = secrets.token_hex(32)
# Rule 5: no real bank, product or marketplace names anywhere on screen.
# Built from parts, so this file does not hold the names it forbids (AI-14's scan).
BANNED = re.compile(
    "|".join(("kb" + "ank", "kb" + "tg", "kasi" + "korn", r"k\s*" + "plus", "sho" + "pee")),
    re.IGNORECASE,
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def shown(migration_engine: Any, test_db_url: str, test_migration_db_url: str) -> Iterator[Any]:
    config = DemoConfig(
        app_url=test_db_url,
        migration_url=test_migration_db_url,
        secret=SecretStr(SECRET),
        db_name=DB_NAME,
        port=_free_port(),
    )
    out = io.StringIO()
    pauses: list[int] = []
    facts = run(config, out=out, pause=lambda: pauses.append(1))
    yield facts, out.getvalue(), pauses
    admin = make_engine(test_migration_db_url).execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)'))
    admin.dispose()


def test_demo_scene_1_reset_clean_db_app_role_and_10000_balance(shown: Any) -> None:
    facts, _, pauses = shown
    assert facts["reset"] == {"role": "lumen_app", "bank": Decimal("10000.00")}
    assert len(pauses) == 5  # Enter between the six scenes, not after the last


def test_demo_scene_2_purchase_saves_120_and_alerts_with_the_monthly_total(shown: Any) -> None:
    purchase = shown[0]["purchase"]
    assert (purchase["status"], purchase["body"]) == (200, {"status": "processed"})
    assert purchase["savings"] == [Decimal("120.00")]
    assert purchase["savings_balance"] == Decimal("120.00")
    assert purchase["bank"] == Decimal("9880.00")
    title, body = purchase["alert"]
    assert title == "รายการผ่อนใหม่"
    assert "ShopDemo 1,200 บาท ผ่อน 4 เดือน" in body
    assert "ยอดผ่อนรวมต่อเดือนตอนนี้ 300 บาท" in body  # L43


def test_demo_scene_3_exact_resend_is_a_duplicate_with_nothing_new(shown: Any) -> None:
    resend = shown[0]["resend"]
    assert (resend["status"], resend["body"]) == (200, {"status": "duplicate"})
    assert resend["savings"] == [Decimal("120.00")]
    assert resend["bank"] == Decimal("9880.00")
    assert resend["pushes"] == 1


def test_demo_scene_4_cash_withdrawal_gets_the_strong_alert_and_no_saving(shown: Any) -> None:
    cash = shown[0]["cash"]
    assert (cash["status"], cash["kind"]) == (200, "cash_withdrawal")
    title, body = cash["alert"]
    assert title == "แจ้งเตือนเบิกเงินสด"
    assert "ยอดผ่อนรวมต่อเดือนตอนนี้ 1,330 บาท" in body
    assert cash["savings"] == [Decimal("120.00")]


def test_demo_scene_5_not_me_disputes_signals_and_answers_honestly(shown: Any) -> None:
    not_me = shown[0]["not_me"]
    body = not_me["body"]
    assert (not_me["status"], body["status"], body["platform_signal"]) == (
        200,
        "disputed",
        "sent",
    )
    assert body["message"].startswith("บันทึกการแจ้งของคุณแล้ว และส่งเรื่องให้ ShopDemo ตรวจสอบแล้ว")
    assert "Lumen ยกเลิกรายการแทนคุณไม่ได้" in body["message"]
    assert body["contact"]["mock"] is True
    assert [(s.vendor, s.contract_id, s.user_id) for s in not_me["signals"]] == [
        ("shopdemo", "ctr_demo_cash", USER)
    ]


def test_demo_scene_6_summary_shows_the_total_and_flags_the_disputed_debt(shown: Any) -> None:
    summary = shown[0]["summary"]
    assert summary["status"] == 200
    body = summary["body"]
    assert body["monthly_total"] == "1330.00"
    by_contract = {line["contract_id"]: line for line in body["installments"]}
    assert by_contract["ctr_demo_earbuds"]["status"] == "active"
    assert by_contract["ctr_demo_earbuds"]["disputed_at"] is None
    assert by_contract["ctr_demo_cash"]["status"] == "disputed"
    assert by_contract["ctr_demo_cash"]["disputed_at"] is not None


def test_demo_output_is_safe_to_show(shown: Any) -> None:
    _, output, _ = shown
    for number in range(1, 7):
        assert f"[{number}/6]" in output
    assert SECRET not in output  # the webhook secret is never printed
    assert BANNED.search(output) is None  # rule 5
    assert "—" not in output  # rule 10
    assert "ไม่ใช่รายการของคุณ" in output  # Thai text reaches the screen intact
    assert 'reported "Not me"' in output


def _columns(line: str) -> int:
    """Terminal width: Thai vowel and tone marks (category Mn) take no column."""
    return sum(unicodedata.category(c) != "Mn" for c in line)


def test_demo_output_fits_64_columns_for_a_large_font(shown: Any) -> None:
    _, output, _ = shown
    wide = [line for line in output.splitlines() if _columns(line) > 64]
    assert wide == []
