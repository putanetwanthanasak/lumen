"""Database engine and session handling. Nothing connects at import time."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    if url is None:
        raise RuntimeError("DATABASE_URL is not set")
    return make_engine(url.get_secret_value())


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with get_sessionmaker()() as session:
        yield session
