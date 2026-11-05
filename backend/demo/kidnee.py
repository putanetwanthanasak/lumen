"""The KidNee screens' demo data and one-server run (Session 15A).

Its own database, `lumen_kidnee`; your `lumen` is never touched. Months are relative
to today, so the story reads the same on any date. Every write goes through the
app's own services (settings, then POST /installments' record), so each persona
gets the savings, alerts and audit rows a real user would.

    cd backend
    uv run python -m demo.kidnee reset --yes   # drop, migrate and seed lumen_kidnee
    uv run python -m demo.kidnee seed          # migrate and seed; safe to run again
    uv run python -m demo.kidnee serve         # http://127.0.0.1:8000 (build frontend first)
    uv run python -m demo.kidnee ai-check      # the real model once per persona (needs a key)

Personas (X-Demo-User). All three have income 20,000.00, payday 25, budget 5,000.00,
auto-save with consent, and leftover saving on. The buffer is what their real
auto-saves gave:
- demo-mon (ม่อน): in budget, 3,500.00 a month; saves 10%, a modest buffer (2,700.00);
- demo-over: over budget this month and next (6,500.00), then back within it; saves
  10%, so the buffer (5,700.00) clearly covers the 3,000.00 over budget;
- demo-consolidate: 9 months over budget from this month, consolidation is ELIGIBLE;
  saves 2%, so the small buffer (1,500.00) covers little of the 10,500.00 over budget.

Platform names are fictional ("ShopDemo", "RideDemo"), never a real app's; one item
is left unnamed, as a user may leave it.
"""

import argparse
import json
import re
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import uvicorn
from sqlalchemy import Engine, case, func, make_url, select, text
from sqlalchemy.orm import Session, sessionmaker
from starlette.applications import Starlette

from app.affordability.months import Month
from app.affordability.service import SettingsRequiredError
from app.ai.provider import DEFAULT_MODEL, Writer, summary_writer
from app.assistant import summary
from app.clock import today
from app.config import Settings, get_settings
from app.db import get_session, make_engine
from app.installments.schemas import ManualEntryIn
from app.installments.service import Outcome, record
from app.main import create_app
from app.models import SavingsTransaction, SavingsType, UserSettings
from app.notifications import service as notifications
from app.providers import get_bank_provider, get_push_provider
from app.providers.base import BankAccountProvider, PushProvider
from app.providers.mock_bank import DEFAULT_OPENING_BALANCE, MockBankAccountProvider
from app.savings import service as savings
from app.serve import FRONTEND_DIST, create_serving_app
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
    # saving_rule: per persona, below.
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
    platform: str | None  # fictional only; None: not named


def earbuds(offset: int) -> Item:
    return Item("earbuds", "หูฟังไร้สาย", "12000.00", 6, "2000.00", offset, "ShopDemo")


FRIDGE = Item("fridge", "ตู้เย็น", "15000.00", 10, "1500.00", -1, None)
LAPTOP = Item("laptop", "โน้ตบุ๊ก", "30000.00", 10, "3000.00", 0, "ShopDemo")
MOTORBIKE = Item("motorbike", "มอเตอร์ไซค์", "48000.00", 12, "4000.00", 0, "RideDemo")


@dataclass(frozen=True)
class Persona:
    items: list[Item]
    saving_percent: int = 10


PERSONAS: dict[str, Persona] = {
    "demo-mon": Persona([earbuds(-3), FRIDGE]),
    # Earbuds end next month, so only this month and next are over budget: 2 months,
    # not the 3 in a row that L70 (a) needs.
    "demo-over": Persona([earbuds(-4), FRIDGE, LAPTOP]),
    # 2%: 240.00 + 300.00 + 960.00, a buffer far below the months over budget.
    "demo-consolidate": Persona([earbuds(-3), FRIDGE, MOTORBIKE], saving_percent=2),
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
        "platform_name": item.platform,
    }
    return ManualEntryIn.model_validate_json(json.dumps(body))


def seed(
    session: Session, *, day: date, bank: BankAccountProvider, push: PushProvider
) -> dict[str, list[str]]:
    """Each persona's settings and installments, one commit per write, then the alert
    delivered, as POST /installments does it. Returns what happened per persona, for
    the console and the tests."""
    now = Month.of(day)
    report: dict[str, list[str]] = {}
    for user, persona in PERSONAS.items():
        rule = {"mode": "percent", "percent": persona.saving_percent}
        settings = SettingsIn.model_validate_json(json.dumps(SETTINGS | {"saving_rule": rule}))
        lines = []
        created = user_settings.create(session, user, settings) is not None
        session.commit()
        lines.append("settings created" if created else "settings kept")
        for item in persona.items:
            result = record(session, user_id=user, entry=entry(user, item, now), bank=bank)
            session.commit()
            if result.notification_id is not None:
                notifications.deliver(session, result.notification_id, push)
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
            return seed(session, day=day, bank=get_bank_provider(), push=get_push_provider())
    finally:
        engine.dispose()


def personas_present(engine: Engine) -> list[str]:
    with Session(engine) as session:
        return sorted(
            session.scalars(select(UserSettings.user_id).where(UserSettings.user_id.in_(PERSONAS)))
        )


def main_balances(session: Session) -> dict[str, Decimal]:
    """Each user's main account as its savings rows left it: the opening balance, less
    every auto-save and leftover saving, plus every move back to main (Session 21).

    The seed runs in its own process, and the mock bank lives in memory, so without
    this the served bank opens every persona at 10,000.00 while บัญชีหลัก lists their
    savings under it (review F2). Decimal only; the SUM is over Numeric(12,2)."""
    signed = case(
        (SavingsTransaction.type == SavingsType.WITHDRAWAL, SavingsTransaction.amount),
        else_=-SavingsTransaction.amount,
    )
    rows = session.execute(
        select(SavingsTransaction.user_id, func.sum(signed)).group_by(SavingsTransaction.user_id)
    ).all()
    return {user: DEFAULT_OPENING_BALANCE + net for user, net in rows}


def open_bank(session: Session, bank: MockBankAccountProvider) -> None:
    """Open the serving process's bank at main_balances, and mark every move to main in
    the rows as credited: a move commits before its credit, so after a restart its
    retry must not be credited again (round 2 F1). A balance below zero can only come
    from rows written before this existed (each serve opened at 10,000.00): that user
    keeps the default opening balance, and the console says to reset."""
    for user, balance in sorted(main_balances(session).items()):
        if balance < 0:
            print(f"{user}: savings exceed the opening balance; run reset to refresh")
            continue
        bank.set_balance(user, balance)
    moves = session.execute(
        select(
            SavingsTransaction.user_id,
            SavingsTransaction.client_request_id,
            SavingsTransaction.amount,
        ).where(SavingsTransaction.type == SavingsType.WITHDRAWAL)
    ).all()
    for user, request_id, amount in moves:
        bank.mark_credited(user, amount, idempotency_key=savings.move_key(user, request_id))


def build(config: KidneeConfig, engine: Engine, dist: Path | None = FRONTEND_DIST) -> Starlette:
    """The serving app: the API with every session on `engine` (lumen_kidnee, never
    the DATABASE_URL database), the demo payday endpoint on, the bank opened from the
    savings rows (open_bank), plus the build."""
    _allowed(config)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def kidnee_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    api = create_app(get_settings().model_copy(update={"demo_endpoints_enabled": True}))
    api.dependency_overrides[get_session] = kidnee_session
    # The process's one bank, which every path uses (the webhook processor reads it
    # directly), opened from the rows (round 2 F2). Only the mock keeps state to open.
    bank = get_bank_provider()
    if isinstance(bank, MockBankAccountProvider):
        with Session(engine) as session:
            open_bank(session, bank)
    return create_serving_app(api, dist)


# serve reads the main account balances only when it starts (open_bank).
RESTART_SERVE = (
    "If serve is running, stop it and start it again: it reads the balances only when it starts."
)


def serve(config: KidneeConfig, *, port: int = PORT) -> None:
    """The screens and the API on 127.0.0.1 only, against lumen_kidnee.

    It refuses to start until every persona has its settings row (seed writes it first):
    the served bank opens from the rows once, at startup (open_bank), so a seed after
    that would leave each main account balance out of step with its movements (Session
    23 review F1). It checks the settings only: a seed stopped halfway leaves them with
    some installments missing, and running seed again, which is idempotent, finishes it
    (PR 2 review F1)."""
    _allowed(config)
    engine = make_engine(config.url(config.app_url))
    try:
        missing = [u for u in PERSONAS if u not in personas_present(engine)]
        if missing:
            raise SystemExit(
                f"Not seeded yet: {', '.join(missing)}. "
                "Run python -m demo.kidnee seed first, then serve."
            )
        served = build(config, engine)
        print(f"KidNee on http://{HOST}:{port} (API at /api). Ctrl+C stops it.")
        uvicorn.run(served, host="127.0.0.1", port=port, log_level="warning")
    finally:
        engine.dispose()


def seconds(nanoseconds: int) -> str:
    """Elapsed time to a tenth of a second, without floats: 1_850_000_000 -> "1.9"."""
    exact = Decimal(nanoseconds) / Decimal(1_000_000_000)
    return str(exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def ai_check(
    engine: Engine,
    *,
    day: date,
    writer: Writer | None,
    clock: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, list[str]]:
    """Home's AI summary for each persona, one model call each (a fresh cache), as
    GET /assistant/summary makes it: source, reason, the seconds it took (the call and
    the check) and the text. When the check refused the model's text, also why and that
    text, to tune the prompt. Never the key."""
    report: dict[str, list[str]] = {}
    for user in PERSONAS:
        try:
            with Session(engine) as session:
                facts = summary.load_facts(session, user, today=day, settings=get_settings())
        except SettingsRequiredError:
            report[user] = ["not seeded: run python -m demo.kidnee seed"]
            continue
        start = clock()
        result = summary.summarize(facts, user_id=user, writer=writer, cache=summary.SummaryCache())
        lines = [
            f"source: {result.source}",
            f"reason: {result.reason.value}",
            f"seconds: {seconds(clock() - start)}",
            "text:",
        ]
        lines += [f"  {line}" for line in result.text.split("\n")]
        if result.failure is not None and result.rejected is not None:
            lines.append(f"check: {result.failure.check.value} ({result.failure.token})")
            lines.append("model text (refused):")
            lines += [f"  {line}" for line in result.rejected.split("\n")]
        report[user] = lines
    return report


def model_config_lines(settings: Settings) -> list[str]:
    """Which env names the summary reads, and whether the key is set: never its value."""
    key = settings.llm_api_key
    is_set = key is not None and key.get_secret_value().strip() != ""
    model = (settings.llm_model_planner or "").strip() or f"{DEFAULT_MODEL} (default)"
    provider = (settings.llm_provider or "").strip().lower()
    return [
        f"LLM_API_KEY: {'set' if is_set else 'not set'}",
        f"LLM_MODEL_PLANNER: {model}",
        f"LLM_PROVIDER: {settings.llm_provider or '(empty)'}"
        + ("" if provider == "anthropic" else ": set it to anthropic, or no model is called"),
    ]


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
    commands.add_parser("ai-check", help=f"the AI summary per persona on {DB_NAME} (real model)")
    args = parser.parse_args(argv)

    if args.command == "reset" and not args.yes:
        raise SystemExit(f"reset drops {DB_NAME}; run it again with --yes")
    config = KidneeConfig.from_env()
    if args.command == "serve":
        serve(config, port=args.port)
        return
    if args.command == "ai-check":
        _allowed(config)
        settings = get_settings()
        print("\n".join(model_config_lines(settings)))
        engine = make_engine(config.url(config.app_url))
        try:
            _print(ai_check(engine, day=today(), writer=summary_writer(settings)))
        finally:
            engine.dispose()
        return
    if args.command == "reset":
        reset_database(config, KIDNEE_DB_NAME)
    else:
        create_if_missing(config)
        migrate(config)
    _print(seed_database(config, day=today()))
    print(RESTART_SERVE)


if __name__ == "__main__":
    main()
