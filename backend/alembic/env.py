"""Alembic environment. The DB URL comes from env (DATABASE_URL), never alembic.ini.

Tests pass an open connection via ``config.attributes["connection"]``.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import get_settings
from app.db import Base, make_engine

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    raise RuntimeError("Offline (--sql) migrations are not supported; run against a database.")


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    url = get_settings().database_url
    if url is None:
        raise RuntimeError("DATABASE_URL is not set")
    engine = make_engine(url.get_secret_value())
    try:
        with engine.connect() as conn:
            _configure(conn)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
