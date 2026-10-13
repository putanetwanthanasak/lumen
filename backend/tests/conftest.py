"""Shared fixtures for DB tests.

The schema comes from Alembic (``upgrade head`` once per session), never create_all.
Each test gets a Session inside an outer transaction that is always rolled back.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
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


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = get_settings().test_database_url
    if url is None:
        pytest.fail("TEST_DATABASE_URL must be set; deselect DB tests with -m 'not db'")
    raw = url.get_secret_value()
    # Destructive tests (downgrade base) must never touch a non-test database.
    if not (make_url(raw).database or "").endswith("_test"):
        pytest.fail("Refusing to run: TEST_DATABASE_URL database name must end in '_test'")
    return raw


@pytest.fixture(scope="session")
def engine(test_db_url: str) -> Iterator[Engine]:
    eng = make_engine(test_db_url)
    with eng.begin() as conn:
        command.upgrade(alembic_config(conn), "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
