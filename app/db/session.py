"""Synchronous engine and session factories with explicit transaction ownership."""

import sqlite3

from sqlalchemy import URL, create_engine, event, make_url
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool

SQLITE_BUSY_TIMEOUT_MS = 5000
SUPPORTED_DRIVERS = {
    "sqlite",
    "sqlite+pysqlite",
    "postgresql",
    "postgresql+psycopg",
    "postgresql+psycopg2",
}


def create_db_engine(database_url: str | URL) -> Engine:
    """Build a lazy engine; its owner must dispose it during application shutdown."""
    try:
        url = make_url(database_url)
    except ArgumentError:
        raise ValueError("DATABASE_URL must be a valid SQLAlchemy connection URL") from None
    if url.drivername not in SUPPORTED_DRIVERS:
        raise ValueError(
            "DATABASE_URL must use a supported synchronous SQLite or PostgreSQL driver"
        )

    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True, hide_parameters=True)

    in_memory = url.database in (None, "", ":memory:")
    connect_args = {"check_same_thread": False, "timeout": SQLITE_BUSY_TIMEOUT_MS / 1000}
    if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        connect_args["autocommit"] = sqlite3.LEGACY_TRANSACTION_CONTROL
    options = {"poolclass": StaticPool} if in_memory else {}
    engine = create_engine(
        url, connect_args=connect_args, pool_pre_ping=True, hide_parameters=True, **options
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: sqlite3.Connection, _record: ConnectionPoolEntry) -> None:
        connection.isolation_level = None
        cursor = connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys=ON")
            mode = cursor.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if not in_memory and mode.lower() != "wal":
                raise RuntimeError("SQLite could not enable WAL for the database file")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def begin_sqlite(connection: Connection) -> None:
        statement = (
            "BEGIN IMMEDIATE"
            if connection.get_execution_options().get("write_transaction")
            else "BEGIN"
        )
        connection.exec_driver_sql(statement)

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create independent sessions; services explicitly commit or roll back each transaction."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
