"""Shared fixtures for DB tests.

The schema comes from Alembic (``upgrade head`` once per session), never create_all.
Each test gets a Session inside an outer transaction that is always rolled back.

S2: two roles, as in production. ``engine`` / ``db_session`` connect as the app role
(TEST_DATABASE_URL, lumen_app), so every test proves the app works with its grants.
``migration_engine`` / ``owner_session`` connect as the schema owner
(TEST_MIGRATION_DATABASE_URL): migrations, clean-up, and tests that must drop a
guard to show the next layer catches the bad state.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import make_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(connection: Connection) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["connection"] = connection
    cfg.attributes["configure_logger"] = False
    return cfg


def _test_url(name: str, url: SecretStr | None) -> str:
    if url is None:
        pytest.fail(f"{name} must be set; deselect DB tests with -m 'not db'")
    raw = url.get_secret_value()
    # Destructive tests (downgrade base) must never touch a non-test database.
    if not (make_url(raw).database or "").endswith("_test"):
        pytest.fail(f"Refusing to run: {name} database name must end in '_test'")
    return raw


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return _test_url("TEST_DATABASE_URL", get_settings().test_database_url)


@pytest.fixture(scope="session")
def test_migration_db_url(test_db_url: str) -> str:
    raw = _test_url("TEST_MIGRATION_DATABASE_URL", get_settings().test_migration_database_url)
    if make_url(raw).database != make_url(test_db_url).database:
        pytest.fail("TEST_MIGRATION_DATABASE_URL and TEST_DATABASE_URL name different databases")
    return raw


@pytest.fixture(scope="session")
def migration_engine(test_migration_db_url: str) -> Iterator[Engine]:
    eng = make_engine(test_migration_db_url)
    with eng.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def engine(migration_engine: Engine, test_db_url: str) -> Iterator[Engine]:
    eng = make_engine(test_db_url)
    yield eng
    eng.dispose()


def _rolled_back_session(eng: Engine) -> Iterator[Session]:
    with eng.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    yield from _rolled_back_session(engine)


@pytest.fixture
def owner_session(migration_engine: Engine) -> Iterator[Session]:
    yield from _rolled_back_session(migration_engine)
