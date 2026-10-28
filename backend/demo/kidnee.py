"""The KidNee screens' demo data and one-server run (Session 15A).

Its own database, `lumen_kidnee`; your `lumen` is never touched. Months are relative
to today, so the story reads the same on any date. Every write goes through the
app's own services (settings, then POST /installments' record), so each persona
gets the savings, alerts and audit rows a real user would.

    cd backend
    uv run python -m demo.kidnee reset --yes   # drop, migrate and seed lumen_kidnee
    uv run python -m demo.kidnee seed          # migrate and seed; safe to run again
    uv run python -m demo.kidnee serve         # http://127.0.0.1:8000 (build frontend first)

Personas (X-Demo-User). All three have income 20,000.00, payday 25, budget 5,000.00,
saving 10% with consent, and leftover saving on:
- demo-mint (มิ้นท์): in budget, 3,500.00 a month;
- demo-over: over budget this month and next (6,500.00), then back within it;
- demo-consolidate: 9 months over budget from this month; consolidation is ELIGIBLE.
"""

import argparse
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import uvicorn
from sqlalchemy import Engine, make_url, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.affordability.months import Month
from app.clock import today
from app.config import get_settings
from app.db import get_session, make_engine
from app.installments.schemas import ManualEntryIn
from app.installments.service import Outcome, record
from app.main import create_app
from app.models import UserSettings
from app.providers import get_bank_provider
from app.providers.base import BankAccountProvider
from app.serve import create_serving_app
from app.user_settings import service as user_settings
from app.user_settings.schemas import SettingsIn
from demo.script import migrate, reset_database

DB_NAME = "lumen_kidnee"
# Only these names may be created, dropped or seeded: the demo's, and the test's.
KIDNEE_DB_NAME = re.compile(r"lumen_kidnee(_test)?")
HOST = "127.0.0.1"  # L60 1: no end-user auth, so never on the network
PORT = 8000

SETTINGS = {
    "income": "20000.00",
    "payday": 25,
    "monthly_installment_budget": "5000.00",
    "saving_rule": {"mode": "percent", "percent": 10},
    "auto_save_enabled": True,
    "auto_save_consent": True,
    "leftover_saving_enabled": True,
}


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    price: str
    months: int
    monthly: str
    offset: int  # first due month, relative to this month


def earbuds(offset: int) -> Item:
    return Item("earbuds", "หูฟังไร้สาย", "12000.00", 6, "2000.00", offset)


FRIDGE = Item("fridge", "ตู้เย็น", "15000.00", 10, "1500.00", -1)
LAPTOP = Item("laptop", "โน้ตบุ๊ก", "30000.00", 10, "3000.00", 0)
MOTORBIKE = Item("motorbike", "มอเตอร์ไซค์", "48000.00", 12, "4000.00", 0)

PERSONAS: dict[str, list[Item]] = {
    "demo-mint": [earbuds(-3), FRIDGE],
    # Earbuds end next month, so only this month and next are over budget: 2 months,
    # not the 3 in a row that L70 (a) needs.
    "demo-over": [earbuds(-4), FRIDGE, LAPTOP],
    "demo-consolidate": [earbuds(-3), FRIDGE, MOTORBIKE],
}


@dataclass(frozen=True)
class KidneeConfig:
    app_url: str  # lumen_app; its database name is replaced by db_name
    migration_url: str  # the schema owner, for create, migrate and reset
    db_name: str = DB_NAME

    @classmethod
    def from_env(cls) -> KidneeConfig:
        s = get_settings()
        if s.database_url is None or s.migration_database_url is None:
            raise SystemExit("Set DATABASE_URL and MIGRATION_DATABASE_URL in .env")
        return cls(s.database_url.get_secret_value(), s.migration_database_url.get_secret_value())

    def url(self, raw: str) -> str:
        return make_url(raw).set(database=self.db_name).render_as_string(hide_password=False)


def _allowed(config: KidneeConfig) -> None:
    if KIDNEE_DB_NAME.fullmatch(config.db_name) is None:
        raise SystemExit(f"Refusing to use {config.db_name!r}: not the KidNee demo database")


def create_if_missing(config: KidneeConfig) -> None:
    _allowed(config)
    admin = make_engine(config.migration_url).execution_options(isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            found = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": config.db_name}
            ).first()
            if found is None:
                # DDL cannot bind an identifier; the name is whitelisted and quoted.
                name = conn.dialect.identifier_preparer.quote_identifier(config.db_name)
                conn.execute(text(f"CREATE DATABASE {name}"))
    finally:
        admin.dispose()


def entry(user: str, item: Item, now: Month) -> ManualEntryIn:
    """The body POST /installments would get; fixed request ids make a re-run a
    duplicate, never a second installment."""
    body = {
        "client_request_id": f"seed-{user}-{item.key}",
        "kind": "purchase",
        "item_price": item.price,
        "months": item.months,
        "monthly_amount": item.monthly,
        "first_due_month": str(now.plus(item.offset)),
        "item_name": item.name,
    }
    return ManualEntryIn.model_validate_json(json.dumps(body))


def seed(session: Session, *, day: date, bank: BankAccountProvider) -> dict[str, list[str]]:
    """Each persona's settings and installments, one commit per write, as the API
    does it. Returns what happened per persona, for the console and the tests."""
    now = Month.of(day)
    settings = SettingsIn.model_validate_json(json.dumps(SETTINGS))
    report: dict[str, list[str]] = {}
    for user, items in PERSONAS.items():
        lines = []
        created = user_settings.create(session, user, settings) is not None
        session.commit()
        lines.append("settings created" if created else "settings kept")
        for item in items:
            result = record(session, user_id=user, entry=entry(user, item, now), bank=bank)
            session.commit()
            if result.outcome is Outcome.CONFLICT:
                # Seeded in another month: the dates differ. Never overwrite; say so.
                lines.append(f"{item.key}: seeded in another month, run reset to refresh")
            else:
                lines.append(f"{item.key}: {result.outcome.value}, saved {result.saved_amount}")
        report[user] = lines
    return report


def seed_database(config: KidneeConfig, *, day: date) -> dict[str, list[str]]:
    engine = make_engine(config.url(config.app_url))
    try:
        with Session(engine) as session:
            return seed(session, day=day, bank=get_bank_provider())
    finally:
        engine.dispose()


def personas_present(engine: Engine) -> list[str]:
    with Session(engine) as session:
        return sorted(
            session.scalars(select(UserSettings.user_id).where(UserSettings.user_id.in_(PERSONAS)))
        )


def serve(config: KidneeConfig, *, port: int = PORT) -> None:
    """The screens and the API on 127.0.0.1 only, against lumen_kidnee, with the
    demo payday endpoint on for the Demo panel."""
    _allowed(config)
    engine = make_engine(config.url(config.app_url))
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def kidnee_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    api = create_app(get_settings().model_copy(update={"demo_endpoints_enabled": True}))
    api.dependency_overrides[get_session] = kidnee_session
    missing = [u for u in PERSONAS if u not in personas_present(engine)]
    if missing:
        print(f"Not seeded yet: {', '.join(missing)}. Run: python -m demo.kidnee seed")
    print(f"KidNee on http://{HOST}:{port} (API at /api). Ctrl+C stops it.")
    try:
        uvicorn.run(create_serving_app(api), host="127.0.0.1", port=port, log_level="warning")
    finally:
        engine.dispose()


def _print(report: dict[str, list[str]]) -> None:
    for user, lines in report.items():
        print(f"{user}:")
        for line in lines:
            print(f"  {line}")


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Thai names on any terminal locale
    parser = argparse.ArgumentParser(prog="python -m demo.kidnee")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help=f"migrate {DB_NAME} and add the personas")
    reset = commands.add_parser("reset", help=f"drop {DB_NAME}, migrate it and seed it")
    reset.add_argument("--yes", action="store_true", help=f"really drop {DB_NAME}")
    run = commands.add_parser("serve", help=f"screens and API on {HOST}")
    run.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args(argv)

    if args.command == "reset" and not args.yes:
        raise SystemExit(f"reset drops {DB_NAME}; run it again with --yes")
    config = KidneeConfig.from_env()
    if args.command == "serve":
        serve(config, port=args.port)
        return
    if args.command == "reset":
        reset_database(config, KIDNEE_DB_NAME)
    else:
        create_if_missing(config)
        migrate(config)
    _print(seed_database(config, day=today()))


if __name__ == "__main__":
    main()
