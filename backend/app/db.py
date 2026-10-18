"""Database engine and session handling. Nothing connects at import time."""

from collections.abc import Generator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, MetaData, create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

# Deterministic constraint names: migrations, tests, and reviews all refer to these.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str, **pool: Any) -> Engine:
    # R7: _credit's retry loop needs READ COMMITTED (a losing UPDATE must see the
    # winner's row, not raise a serialization error), so it does not depend on the
    # server's default_transaction_isolation. S12: hide_parameters keeps user refs and
    # alert text out of DB error messages, and so out of the logs.
    return create_engine(
        url,
        pool_pre_ping=True,
        isolation_level="READ COMMITTED",
        hide_parameters=True,
        **pool,
    )


def describe_db_error(exc: BaseException) -> str:
    """S12: what a log may say about an error. For a DB error that is its class,
    SQLSTATE and constraint, never its text: Postgres's DETAIL quotes the failing
    row ("Failing row contains (...)"), user ref and alert body included, which
    hide_parameters does not cover."""
    if not isinstance(exc, DBAPIError):
        return type(exc).__name__
    diag = getattr(exc.orig, "diag", None)
    sqlstate = getattr(diag, "sqlstate", None)
    constraint = getattr(diag, "constraint_name", None)
    return f"{type(exc).__name__} sqlstate={sqlstate} constraint={constraint}"


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if url is None:
        raise RuntimeError("DATABASE_URL is not set")
    return make_engine(url.get_secret_value())


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Generator[Session]:
    """FastAPI dependency: one session per request."""
    with get_sessionmaker()() as session:
        yield session
