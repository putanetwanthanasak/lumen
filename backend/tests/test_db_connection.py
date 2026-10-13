import pytest
from sqlalchemy import text

from app.config import get_settings
from app.db import make_engine

EXPECTED_DB = "buffer_test"


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
