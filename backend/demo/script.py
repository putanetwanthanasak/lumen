"""The 5-minute mentor demo: six scenes over real, signed HTTP.

The real app runs under uvicorn on 127.0.0.1 (L60 1), in a thread of this process,
against its own database (`lumen_demo`, rebuilt by Alembic) and as the `lumen_app`
role (S2). Webhooks are signed like a platform signs them, with the secret from env;
the secret is never printed. Running in-process lets the demo show the mock bank,
the pushes and the platform signals, which live in memory.

    cd backend && uv run python -m demo          # Enter between scenes
"""

import json
import os
import re
import sys
import textwrap
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, TextIO

import httpx
import uvicorn
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, make_url, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db import get_session, make_engine
from app.main import app
from app.models import Notification, SavingMode, SavingsTransaction, UserBalance, UserSettings
from app.notifications.copy import format_baht
from app.providers import get_bank_provider, get_platform_provider, get_push_provider
from app.providers.mock_platform import MockPlatformProvider
from app.providers.mock_push import MockPushProvider
from app.webhooks.signature import get_vendor_secrets, sign

BACKEND_DIR = Path(__file__).resolve().parents[1]
VENDOR = "shopdemo"
USER = "demo_user"
DEMO_DB = "lumen_demo"
# Only these names may be dropped and recreated: the demo's, and the smoke test's.
DEMO_DB_NAME = re.compile(r"lumen_demo(_test)?")
SCENES = 6
WIDTH = 60  # Thai lines wrap at spaces; with the indent, no line passes 64 columns


@dataclass(frozen=True)
class DemoConfig:
    app_url: str  # lumen_app; its database name is replaced by db_name
    migration_url: str  # the superuser, for the reset only
    secret: SecretStr
    db_name: str = DEMO_DB
    port: int = 8765

    @classmethod
    def from_env(cls) -> DemoConfig:
        s = get_settings()
        app_url, migration_url = s.database_url, s.migration_database_url
        secret = s.webhook_secret_shopdemo
        if app_url is None or migration_url is None or secret is None:
            raise SystemExit(
                "Set DATABASE_URL, MIGRATION_DATABASE_URL and WEBHOOK_SECRET_SHOPDEMO in .env"
            )
        return cls(
            app_url=app_url.get_secret_value(),
            migration_url=migration_url.get_secret_value(),
            secret=secret,
        )

    def url(self, raw: str) -> str:
        return make_url(raw).set(database=self.db_name).render_as_string(hide_password=False)


# --- output ------------------------------------------------------------------------------


@dataclass
class Screen:
    out: TextIO
    color: bool

    def _style(self, code: str, line: str) -> str:
        return f"\033[{code}m{line}\033[0m" if self.color else line

    def scene(self, number: int, title: str) -> None:
        self.out.write("\n" + self._style("1;36", f"[{number}/{SCENES}] {title}") + "\n")

    def say(self, line: str = "") -> None:
        self.out.write(f"  {line}\n")

    def text(self, body: str) -> None:
        for line in textwrap.wrap(body, WIDTH):
            self.say("   " + line)

    def ok(self, line: str) -> None:
        self.say(self._style("32", "✓ ") + line)

    def alert(self, title: str, body: str, *, strong: bool = False) -> None:
        mark = self._style("1;31", "!! ") if strong else "   "
        self.say(mark + self._style("1", title))
        self.text(body)


# --- the demo ----------------------------------------------------------------------------


@dataclass
class Demo:
    config: DemoConfig
    screen: Screen
    engine: Engine
    client: httpx.Client
    push: MockPushProvider = field(default_factory=MockPushProvider)
    platform: MockPlatformProvider = field(default_factory=MockPlatformProvider)
    facts: dict[str, Any] = field(default_factory=dict)
    sent: dict[str, tuple[bytes, dict[str, str]]] = field(default_factory=dict)

    def post_webhook(self, name: str, data: dict[str, Any]) -> httpx.Response:
        """Sign and send like the platform: HMAC-SHA256 over "timestamp.body"."""
        body = json.dumps(data, ensure_ascii=False).encode()
        timestamp = str(int(time.time()))
        headers = {
            "Content-Type": "application/json",
            "X-Vendor-Id": VENDOR,
            "X-Timestamp": timestamp,
            "X-Signature": sign(self.config.secret.get_secret_value(), timestamp, body),
        }
        self.sent[name] = (body, headers)
        return self.client.post("/webhooks/bnpl", content=body, headers=headers)

    def resend(self, name: str) -> httpx.Response:
        """The exact same bytes and headers again, as a platform retry would send."""
        body, headers = self.sent[name]
        return self.client.post("/webhooks/bnpl", content=body, headers=headers)

    def as_user(self) -> dict[str, str]:
        return {"X-Demo-User": USER}

    def session(self) -> Session:
        return Session(self.engine)

    def savings(self) -> tuple[list[Decimal], Decimal]:
        with self.session() as s:
            rows = list(s.scalars(select(SavingsTransaction.amount)))
            balance = s.scalar(select(UserBalance.savings_balance)) or Decimal("0.00")
        return rows, balance

    def alerts(self) -> list[Notification]:
        with self.session() as s:
            return list(s.scalars(select(Notification).order_by(Notification.created_at)))

    def bank(self) -> Decimal:
        return get_bank_provider().get_balance(USER)


def contract(contract_id: str, kind: str, item: str, **money: str | int) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "kind": kind,
        "item_name": item,
        "first_due_date": "2026-11-05",
        "overdue_days": 0,
        "late_fee_per_period": "50.00",
        **money,
    }


def created(event_type: str, event_id: str, terms: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "event_id": event_id,
        "occurred_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_ref": USER,
        "contract": terms,
    }


PURCHASE = created(
    "installment_created",
    "evt_demo_purchase",
    contract(
        "ctr_demo_earbuds",
        "purchase",
        "Wireless earbuds",
        principal="1200.00",
        months=4,
        monthly_amount="300.00",
        fee_total="0.00",
        min_payment="300.00",
        monthly_rate="0.000000",
    ),
)
CASH = created(
    "cash_withdrawal_created",
    "evt_demo_cash",
    contract(
        "ctr_demo_cash",
        "cash_withdrawal",
        "Cash withdrawal",
        principal="3000.00",
        months=3,
        monthly_amount="1030.00",
        fee_total="90.00",
        min_payment="1030.00",
        monthly_rate="0.010000",
    ),
)


def baht(amount: Decimal) -> str:
    return f"{format_baht(amount)} THB"


def answer(response: httpx.Response) -> str:
    body = response.json()
    return f"{response.status_code} {body.get('status') or body.get('detail')}"


def scene_reset(demo: Demo) -> None:
    demo.screen.scene(1, "Reset: a clean demo database and one user")
    with demo.session() as s:
        role = s.scalar(text("SELECT current_user"))
        s.add(
            UserSettings(
                user_id=USER,
                auto_save_enabled=True,
                consent_at=datetime.now(UTC),
                income=Decimal("30000.00"),
                payday=25,
                monthly_installment_budget=Decimal("9000.00"),
                saving_mode=SavingMode.PERCENT,
                saving_percent=10,  # L63: the user's own rule
            )
        )
        s.commit()
    demo.screen.ok(f"Database {demo.config.db_name}: rebuilt by Alembic, empty")
    demo.screen.ok(f"App connects as {role} (no superuser, no DELETE)")
    demo.screen.ok(f"User {USER}: auto-save 10% per purchase, consent given")
    demo.screen.ok(f"Mock bank balance: {baht(demo.bank())}")
    demo.facts["reset"] = {"role": role, "bank": demo.bank()}


def scene_purchase(demo: Demo) -> None:
    demo.screen.scene(2, "ShopDemo purchase: 1,200 THB over 4 months")
    response = demo.post_webhook("purchase", PURCHASE)
    demo.screen.say(f"POST /webhooks/bnpl (signed) -> {answer(response)}")
    rows, balance = demo.savings()
    demo.screen.ok("Installment: Wireless earbuds, 300 THB x 4 months")
    demo.screen.ok(f"Auto-save: {baht(rows[0])} (10%)  |  bank now {baht(demo.bank())}")
    pushed = demo.push.delivered[-1]
    demo.screen.say("Alert pushed to the phone:")
    demo.screen.alert(pushed.title, pushed.body)
    demo.facts["purchase"] = {
        "status": response.status_code,
        "body": response.json(),
        "savings": rows,
        "savings_balance": balance,
        "bank": demo.bank(),
        "alert": (pushed.title, pushed.body),
    }


def scene_resend(demo: Demo) -> None:
    demo.screen.scene(3, "The platform resends the exact same webhook")
    response = demo.resend("purchase")
    rows, _ = demo.savings()
    pushes = len(demo.push.delivered)
    demo.screen.say(f"POST /webhooks/bnpl (same bytes) -> {answer(response)}")
    demo.screen.ok(f"Savings rows: {len(rows)}  |  bank still {baht(demo.bank())}")
    demo.screen.ok(f"Alerts pushed: {pushes} (no second alert)")
    demo.facts["resend"] = {
        "status": response.status_code,
        "body": response.json(),
        "savings": rows,
        "bank": demo.bank(),
        "pushes": pushes,
    }


def scene_cash(demo: Demo) -> None:
    demo.screen.scene(4, "A 3,000 THB cash withdrawal the user did not make")
    response = demo.post_webhook("cash", CASH)
    demo.screen.say(f"POST /webhooks/bnpl (signed) -> {answer(response)}")
    alert = demo.alerts()[-1]
    pushed = demo.push.delivered[-1]
    demo.screen.say("Strong alert pushed:")
    demo.screen.alert(pushed.title, pushed.body, strong=True)
    rows, _ = demo.savings()
    demo.screen.ok(f"Cash never triggers a saving: savings rows still {len(rows)}")
    demo.facts["cash"] = {
        "status": response.status_code,
        "kind": alert.kind,
        "alert": (pushed.title, pushed.body),
        "savings": rows,
    }


def scene_not_me(demo: Demo) -> None:
    demo.screen.scene(5, '"Not me" on the cash withdrawal')
    summary = demo.client.get("/debts/summary", headers=demo.as_user()).json()
    cash_id = next(i["id"] for i in summary["installments"] if i["contract_id"] == "ctr_demo_cash")
    response = demo.client.post(f"/debts/{cash_id}/not-me", headers=demo.as_user())
    body = response.json()
    demo.screen.say(f"POST /debts/<id>/not-me -> {response.status_code}")
    demo.screen.ok(f"Status: {body['status']}  |  platform signal: {body['platform_signal']}")
    for signal in demo.platform.signals:
        demo.screen.ok(f"ShopDemo received a report for contract {signal.contract_id}")
    demo.screen.say("Message to the user:")
    demo.screen.text(body["message"])
    contact = body["contact"]
    mock = "mock data, not a real channel" if contact["mock"] else "contact"
    demo.screen.say(f"{contact['vendor']} contact ({mock}):")
    demo.screen.say(f"   {contact['phone']}  {contact['url']}")
    demo.facts["not_me"] = {
        "status": response.status_code,
        "body": body,
        "signals": demo.platform.signals,
    }


def scene_summary(demo: Demo) -> None:
    demo.screen.scene(6, "GET /debts/summary")
    response = demo.client.get("/debts/summary", headers=demo.as_user())
    body = response.json()
    demo.screen.ok(f"Monthly total: {baht(Decimal(body['monthly_total']))}")
    for line in body["installments"]:
        demo.screen.say(
            f"   {line['item_name']:<17} {baht(Decimal(line['monthly_amount'])):>10}/month"
            f"  {line['status']}"
        )
        if line["disputed_at"]:
            demo.screen.say('      ^ the user reported "Not me"')
    demo.screen.say("A disputed debt still counts until ShopDemo cancels it.")
    demo.facts["summary"] = {"status": response.status_code, "body": body}


SCENE_LIST: list[Callable[[Demo], None]] = [
    scene_reset,
    scene_purchase,
    scene_resend,
    scene_cash,
    scene_not_me,
    scene_summary,
]


# --- set-up ------------------------------------------------------------------------------


def reset_database(config: DemoConfig) -> None:
    """Drop and recreate the demo database as the superuser, then migrate it."""
    if DEMO_DB_NAME.fullmatch(config.db_name) is None:
        raise SystemExit(f"Refusing to reset {config.db_name!r}: not a demo database")
    admin = make_engine(config.migration_url).execution_options(isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            # DDL cannot bind an identifier; the name is whitelisted above and quoted.
            name = conn.dialect.identifier_preparer.quote_identifier(config.db_name)
            conn.execute(text(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)"))
            conn.execute(text(f"CREATE DATABASE {name}"))
    finally:
        admin.dispose()
    owner = make_engine(config.url(config.migration_url))
    try:
        with owner.begin() as conn:
            cfg = Config(str(BACKEND_DIR / "alembic.ini"))
            cfg.attributes["connection"] = conn
            cfg.attributes["configure_logger"] = False
            command.upgrade(cfg, "head")
    finally:
        owner.dispose()


@contextmanager
def running_app(port: int) -> Iterator[httpx.Client]:
    """The real app under uvicorn on 127.0.0.1 only (L60 1), stopped on exit."""
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            if time.monotonic() > deadline or not thread.is_alive():
                raise SystemExit(f"uvicorn did not start on 127.0.0.1:{port}")
            time.sleep(0.05)
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            yield client
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def run(
    config: DemoConfig,
    *,
    out: TextIO,
    pause: Callable[[], None] | None = None,
    color: bool = False,
) -> dict[str, Any]:
    """Run all six scenes; `pause` runs between scenes. Returns what each scene saw."""
    reset_database(config)
    get_bank_provider.cache_clear()  # a fresh mock bank: every user opens at 10,000
    engine = make_engine(config.url(config.app_url))
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def demo_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    push, platform = MockPushProvider(), MockPlatformProvider()
    app.dependency_overrides.update(
        {
            get_session: demo_session,
            get_vendor_secrets: lambda: {VENDOR: config.secret},
            get_push_provider: lambda: push,
            get_platform_provider: lambda: platform,
        }
    )
    try:
        with running_app(config.port) as client:
            demo = Demo(config, Screen(out, color), engine, client, push, platform)
            for number, scene in enumerate(SCENE_LIST, start=1):
                scene(demo)
                if pause is not None and number < SCENES:
                    pause()
            out.write("\n")
            return demo.facts
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Thai text on any terminal locale
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ

    def wait() -> None:
        input("\n  [Enter] next scene ")

    run(DemoConfig.from_env(), out=sys.stdout, pause=wait, color=color)
