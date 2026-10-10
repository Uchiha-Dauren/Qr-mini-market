"""Run synchronous migrations with the application's engine configuration."""

from logging.config import fileConfig
from pathlib import Path
from typing import Literal

from alembic import context
from alembic.autogenerate.api import AutogenContext
from sqlalchemy import make_url
from sqlalchemy.engine import Connection

import app.models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import create_db_engine
from app.db.types import UTCDateTime

config = context.config
if config.config_file_name is not None and Path(config.config_file_name).is_file():
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def render_item(kind: str, item: object, _autogen_context: AutogenContext) -> str | Literal[False]:
    """Snapshot the physical type without importing mutable application code in revisions."""
    if kind == "type" and isinstance(item, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    """Emit SQL without opening a database connection."""
    connection = config.attributes.get("connection")
    url = connection.engine.url if connection is not None else make_url(get_settings().database_url)
    is_sqlite = url.get_backend_name() == "sqlite"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
        compare_type=True,
        render_item=render_item,
        transactional_ddl=True if is_sqlite else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def migrate_connection(connection: Connection) -> None:
    """Run migrations while preserving ownership of a supplied connection."""
    is_sqlite = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=is_sqlite,
        compare_type=True,
        render_item=render_item,
        # The shared engine factory fixes SQLite's legacy DDL transaction behavior.
        transactional_ddl=True if is_sqlite else None,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Use a caller-owned connection or create and clean up an engine."""
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate_connection(connection)
        return

    engine = create_db_engine(get_settings().database_url)
    try:
        with engine.connect() as connection:
            migrate_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
