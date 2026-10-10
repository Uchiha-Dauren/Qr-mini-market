"""Exercise real SQLite transactions and UTC storage in a temporary database."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest
from sqlalchemy import URL, ForeignKey, MetaData, delete, func, inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.db.base import Base
from app.db.session import create_db_engine, create_session_factory
from app.db.types import UTCDateTime


class DatabaseTestBase(Base):
    __abstract__ = True
    metadata = MetaData(naming_convention=Base.metadata.naming_convention)


class Parent(DatabaseTestBase):
    __tablename__ = "test_parents"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Child(DatabaseTestBase):
    __tablename__ = "test_children"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("test_parents.id", ondelete="RESTRICT"))


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    url = URL.create("sqlite+pysqlite", database=str(tmp_path / "test.db"))
    engine = create_db_engine(url)
    try:
        DatabaseTestBase.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def test_pragmas_on_two_physical_connections(engine: Engine) -> None:
    with engine.connect() as first, engine.connect() as second:
        assert first.connection.driver_connection is not second.connection.driver_connection
        for connection in (first, second):
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == "wal"


def test_foreign_key_rejects_unknown_parent(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(Child(parent_id=999))


def test_restrict_prevents_deleting_parent(sessions: sessionmaker[Session]) -> None:
    with sessions.begin() as session:
        session.add(Parent(id=1))
        session.flush()
        session.add(Child(parent_id=1))
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.execute(delete(Parent).where(Parent.id == 1))
    with sessions() as session:
        assert session.get(Parent, 1) is not None


def test_rollback_reverts_all_changes(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError, match="Abort transaction"), sessions.begin() as session:
        session.add(Parent(id=1))
        session.flush()
        session.add(Child(parent_id=1))
        session.flush()
        raise RuntimeError("Abort transaction")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Parent)) == 0
        assert session.scalar(select(func.count()).select_from(Child)) == 0


def test_close_without_commit_discards_changes(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        session.add(Parent(id=1))
        session.flush()
    with sessions() as session:
        assert session.get(Parent, 1) is None


def test_outer_rollback_includes_released_savepoint(sessions: sessionmaker[Session]) -> None:
    with pytest.raises(RuntimeError, match="Abort outer transaction"), sessions.begin() as session:
        with session.begin_nested():
            session.add(Parent(id=1))
        raise RuntimeError("Abort outer transaction")
    with sessions() as session:
        assert session.get(Parent, 1) is None


def test_ddl_is_transactional(engine: Engine) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.execute(text("CREATE TABLE rollback_probe (id INTEGER PRIMARY KEY)"))
        transaction.rollback()
    assert not inspect(engine).has_table("rollback_probe")


@pytest.mark.parametrize(
    "value",
    [
        None,
        datetime(2026, 1, 1, 1, 2, 3, 123456, tzinfo=timezone(timedelta(hours=5))),
        datetime(2026, 1, 1, 23, 59, 59, tzinfo=timezone(timedelta(hours=-7))),
        datetime(2026, 10, 10, tzinfo=UTC),
    ],
)
def test_datetime_roundtrip_uses_utc(
    sessions: sessionmaker[Session], value: datetime | None
) -> None:
    with sessions.begin() as session:
        session.add(Parent(id=1, occurred_at=value))
    with sessions() as session:
        actual = session.scalar(select(Parent.occurred_at).where(Parent.id == 1))
        if value is None:
            assert actual is None
        else:
            assert actual == value.astimezone(UTC)
            assert actual.tzinfo is UTC
            raw = session.execute(
                text("SELECT occurred_at FROM test_parents WHERE id = :id"), {"id": 1}
            )
            stored = datetime.fromisoformat(raw.scalar_one())
            assert stored.tzinfo is None
            assert stored == value.astimezone(UTC).replace(tzinfo=None)


class MissingOffset(tzinfo):
    def utcoffset(self, value: datetime | None) -> None:
        return None


@pytest.mark.parametrize(
    "value", [datetime(2026, 1, 1), datetime(2026, 1, 1, tzinfo=MissingOffset())]
)
def test_datetime_without_offset_is_rejected(
    sessions: sessionmaker[Session], value: datetime
) -> None:
    with pytest.raises(StatementError, match="timezone-aware"), sessions.begin() as session:
        session.add(Parent(occurred_at=value))


def test_postgresql_datetime_conversion_without_server() -> None:
    dialect = postgresql.dialect()
    column_type = UTCDateTime()
    local = datetime(2026, 1, 1, 1, tzinfo=timezone(timedelta(hours=5)))
    expected = datetime(2025, 12, 31, 20, tzinfo=UTC)
    assert column_type.process_bind_param(local, dialect) == expected
    assert column_type.process_result_value(local, dialect) == expected
    assert column_type.process_bind_param(None, dialect) is None
    assert column_type.process_result_value(None, dialect) is None
    assert str(column_type.compile(dialect=dialect)) == "TIMESTAMP WITH TIME ZONE"


@pytest.mark.parametrize(
    "url", ["not-a-url", "mysql://localhost/shop", "sqlite+aiosqlite:///shop.db"]
)
def test_invalid_or_unsupported_database_url_is_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL"):
        create_db_engine(url)


def test_memory_database_can_be_used_sequentially() -> None:
    engine = create_db_engine("sqlite:///:memory:")
    try:
        DatabaseTestBase.metadata.create_all(engine)
        sessions = create_session_factory(engine)
        with sessions.begin() as session:
            session.add(Parent(id=1))
        with sessions() as session:
            assert session.get(Parent, 1) is not None
    finally:
        engine.dispose()
