from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import db
from app.config import get_settings

pytestmark = pytest.mark.db


def _clear_caches() -> None:
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()


@pytest.fixture
def app_db_on_test_url(monkeypatch: pytest.MonkeyPatch, test_db_url: str) -> Iterator[None]:
    monkeypatch.setenv("DATABASE_URL", test_db_url)
    _clear_caches()
    yield
    db.get_engine().dispose()
    _clear_caches()


@pytest.mark.usefixtures("app_db_on_test_url")
def test_get_session_yields_working_session() -> None:
    gen = db.get_session()
    session = next(gen)
    assert isinstance(session, Session)
    assert session.execute(text("SELECT current_database()")).scalar_one().endswith("_test")
    gen.close()


def test_get_engine_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        db, "get_settings", lambda: get_settings().model_copy(update={"database_url": None})
    )
    db.get_engine.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
            db.get_engine()
    finally:
        db.get_engine.cache_clear()
