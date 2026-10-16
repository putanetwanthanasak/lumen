import pytest
from sqlalchemy import make_url, text

from app.config import get_settings
from app.db import make_engine

EXPECTED_DB = "lumen_test"


@pytest.mark.db
def test_connects_to_real_test_database() -> None:
    # Fail (not skip) when unset, so CI can never pass without a real DB.
    url = get_settings().test_database_url
    assert url is not None, "TEST_DATABASE_URL must be set; deselect with -m 'not db'"
    engine = make_engine(url.get_secret_value())
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar_one() == 1
            assert conn.execute(text("SELECT current_database()")).scalar_one() == EXPECTED_DB
    finally:
        engine.dispose()


@pytest.mark.db
def test_R7_engine_pins_read_committed_whatever_the_server_default(test_db_url: str) -> None:
    # The connection asks the server for SERIALIZABLE by default; make_engine must
    # still run every transaction at READ COMMITTED, which _credit's retry relies on.
    url = make_url(test_db_url).update_query_dict(
        {"options": "-c default_transaction_isolation=serializable"}
    )
    engine = make_engine(url.render_as_string(hide_password=False))
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SHOW transaction_isolation")).scalar_one() == "read committed"
    finally:
        engine.dispose()
