"""Independent synchronous database and bounded local transaction retries."""

import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import DateTime, create_engine, event, make_url
from sqlalchemy.engine import Connection, Dialect, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator

T = TypeVar("T")


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires an aware datetime")
        value = value.astimezone(UTC)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def create_db_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername not in {
        "sqlite",
        "sqlite+pysqlite",
        "postgresql",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
        raise ValueError("BANK_DATABASE_URL requires synchronous SQLite or PostgreSQL")
    if url.get_backend_name() != "sqlite":
        return create_engine(url, pool_pre_ping=True, hide_parameters=True)
    memory = url.database in (None, "", ":memory:")
    args = {"check_same_thread": False, "timeout": 5}
    if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        args["autocommit"] = sqlite3.LEGACY_TRANSACTION_CONTROL
    engine = create_engine(
        url,
        connect_args=args,
        hide_parameters=True,
        **({"poolclass": StaticPool} if memory else {}),
    )

    @event.listens_for(engine, "connect")
    def configure(connection: sqlite3.Connection, _record: object) -> None:
        connection.isolation_level = None
        with_cursor = connection.cursor()
        try:
            with_cursor.execute("PRAGMA foreign_keys=ON")
            with_cursor.execute("PRAGMA busy_timeout=5000")
            with_cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            with_cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection: Connection) -> None:
        immediate = connection.get_execution_options().get("bank_write", False)
        connection.exec_driver_sql("BEGIN IMMEDIATE" if immediate else "BEGIN")

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False, autoflush=False)


def run_write(factory: sessionmaker[Session], operation: Callable[[Session], T]) -> T:
    """Retry only local transactions, never a network operation."""
    for attempt in range(4):
        try:
            with factory.begin() as session:
                session.connection(execution_options={"bank_write": True})
                return operation(session)
        except OperationalError as exc:
            code = getattr(exc.orig, "sqlite_errorcode", 0)
            state = getattr(exc.orig, "sqlstate", None)
            retryable = (code and code & 0xFF in (5, 6)) or state in ("40001", "40P01")
            if not retryable or attempt == 3:
                raise
            time.sleep(0.02 * 2**attempt)
    raise RuntimeError("Transaction retries exhausted")
