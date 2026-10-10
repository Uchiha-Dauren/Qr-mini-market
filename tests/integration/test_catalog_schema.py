"""Verify migrated tables, persisted models, and database-level constraints."""

from collections.abc import Iterator
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import URL, CheckConstraint, inspect, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from app.core.barcodes import generate_internal_ean13
from app.core.enums import ProductUnit
from app.db.base import Base
from app.db.session import create_db_engine, create_session_factory
from app.models import Category, Product
from app.models.catalog import MAX_PRICE_MINOR, MAX_QUANTITY

ROOT = Path(__file__).resolve().parents[2]


def migration_config(connection: Connection) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_db_engine(URL.create("sqlite", database=str(tmp_path / "catalog.db")))
    try:
        with engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def populated(engine: Engine) -> tuple[int, int, int]:
    with create_session_factory(engine).begin() as session:
        root = Category(name="Еда", slug="food")
        session.add(root)
        session.flush()
        child = Category(name="Молочные продукты", slug="dairy", parent_id=root.id)
        session.add(child)
        session.flush()
        product = Product(
            name="  МОЛОКО  ",
            barcode=generate_internal_ean13(1),
            category_id=child.id,
            unit=ProductUnit.PIECE,
            price_minor=125000,
            stock_quantity=10,
            reserved_quantity=2,
            min_stock_quantity=1,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            updated_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        session.add(product)
        session.flush()
        return root.id, child.id, product.id


def test_migration_matches_models_and_has_required_indexes(engine: Engine) -> None:
    schema = inspect(engine)
    assert set(schema.get_table_names()) == {"alembic_version", *Base.metadata.tables}
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "compare_server_default": True}
        )
        assert compare_metadata(context, Base.metadata) == []
    for table in Base.metadata.sorted_tables:
        expected = {item.name for item in table.constraints if isinstance(item, CheckConstraint)}
        assert {item["name"] for item in schema.get_check_constraints(table.name)} == expected
        assert all(
            fk["options"]["ondelete"] == "RESTRICT" for fk in schema.get_foreign_keys(table.name)
        )
    indexes = {item["name"]: item for item in schema.get_indexes("products")}
    assert indexes["ix_products_barcode"]["unique"]
    assert indexes["ix_products_category_id"]["column_names"] == ["category_id"]
    assert indexes["ix_products_name_normalized"]["column_names"] == ["name_normalized"]


def test_uuid_normalization_timestamps_and_soft_deactivation(
    engine: Engine, populated: tuple[int, int, int]
) -> None:
    sessions = create_session_factory(engine)
    with sessions.begin() as session:
        product = session.get(Product, populated[2])
        assert isinstance(product.public_id, UUID)
        assert product.public_id.version == 4
        assert isinstance(session.get(Category, populated[0]).public_id, UUID)
        assert product.name == "МОЛОКО"
        assert product.name_normalized == "молоко"
        assert product.unit is ProductUnit.PIECE
        assert product.created_at.tzinfo is UTC
        product.name = "КеФиР"
        product.is_active = False
    with sessions() as session:
        product = session.get(Product, populated[2])
        assert product.name_normalized == "кефир"
        assert product.updated_at > product.created_at
        assert product.updated_at.tzinfo is UTC
        assert product.is_active is False
        assert session.scalar(select(Product).where(Product.name_normalized == "КЕФИР".casefold()))


def test_casefold_expansion_and_numeric_boundaries(
    engine: Engine, populated: tuple[int, int, int]
) -> None:
    with create_session_factory(engine).begin() as session:
        product = session.get(Product, populated[2])
        product.name = "ß" * 200
        product.price_minor = MAX_PRICE_MINOR
        product.stock_quantity = MAX_QUANTITY
        product.reserved_quantity = MAX_QUANTITY
        product.min_stock_quantity = MAX_QUANTITY
    with create_session_factory(engine)() as session:
        product = session.get(Product, populated[2])
        assert product.name_normalized == "ss" * 200
        assert product.price_minor == MAX_PRICE_MINOR
        assert type(product.price_minor) is int
        assert product.stock_quantity == MAX_QUANTITY


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("price_minor", -1),
        ("price_minor", "1.5"),
        ("price_minor", "invalid"),
        ("stock_quantity", -1),
        ("stock_quantity", "2.5"),
        ("stock_quantity", MAX_QUANTITY + 1),
        ("stock_quantity", 1),
        ("reserved_quantity", -1),
        ("reserved_quantity", 11),
        ("reserved_quantity", "1.5"),
        ("min_stock_quantity", -1),
        ("min_stock_quantity", "1.5"),
        ("min_stock_quantity", MAX_QUANTITY + 1),
        ("unit", "LITRE"),
        ("is_active", 2),
        ("category_id", 99999),
        ("name", ""),
        ("name", "x" * 201),
        ("barcode", "123"),
        ("description", "x" * 2001),
    ],
)
def test_database_rejects_invalid_product_values(
    engine: Engine, populated: tuple[int, int, int], column: str, value: object
) -> None:
    # Column names are test-owned constants; values always use bound parameters.
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(f"UPDATE products SET {column} = :value"), {"value": value})


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("parent_id", 99999),
        ("name", ""),
        ("slug", "x" * 101),
        ("sort_order", "0.5"),
        ("sort_order", MAX_QUANTITY + 1),
        ("is_active", 2),
    ],
)
def test_database_rejects_invalid_category_values(
    engine: Engine, populated: tuple[int, int, int], column: str, value: object
) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text(f"UPDATE categories SET {column} = :value"), {"value": value})


def test_category_cannot_parent_itself(engine: Engine, populated: tuple[int, int, int]) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(text("UPDATE categories SET parent_id = id"))


@pytest.mark.parametrize(
    "kind", ["parent", "product_category", "slug", "category_uuid", "barcode", "product_uuid"]
)
def test_restrict_and_uniqueness(
    engine: Engine, populated: tuple[int, int, int], kind: str
) -> None:
    root_id, child_id, product_id = populated
    sessions = create_session_factory(engine)
    with pytest.raises(IntegrityError), sessions.begin() as session:
        if kind in ("parent", "product_category"):
            session.delete(session.get(Category, root_id if kind == "parent" else child_id))
        elif kind in ("slug", "category_uuid"):
            original = session.get(Category, root_id)
            new = Category(name="Другая", slug="food" if kind == "slug" else "other")
            if kind == "category_uuid":
                new.public_id = original.public_id
            session.add(new)
        else:
            original = session.get(Product, product_id)
            new = Product(
                name="Другой товар",
                category_id=child_id,
                unit=ProductUnit.KG,
                price_minor=100,
                barcode=original.barcode if kind == "barcode" else generate_internal_ean13(2),
            )
            if kind == "product_uuid":
                new.public_id = original.public_id
            session.add(new)


@pytest.mark.parametrize("value", [True, "100", 1.5, -1, MAX_PRICE_MINOR + 1])
def test_orm_rejects_invalid_price_before_sql(value: object) -> None:
    with pytest.raises(ValueError, match="price_minor"):
        Product(price_minor=value)


def test_orm_rejects_invalid_barcode_before_sql() -> None:
    with pytest.raises(ValueError, match="EAN"):
        Product(barcode="2000000000016")


def test_populated_downgrade_and_reupgrade(engine: Engine, populated: tuple[int, int, int]) -> None:
    with engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "base")
        assert set(inspect(connection).get_table_names()) == {"alembic_version"}
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT count(*) FROM products")) == 0
        command.check(config)
    assert inspect(engine).has_table("categories")


def test_migration_rollback_is_atomic(tmp_path: Path) -> None:
    engine = create_db_engine(URL.create("sqlite", database=str(tmp_path / "rollback.db")))
    try:
        with pytest.raises(RuntimeError, match="Abort"), engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
            raise RuntimeError("Abort")
        assert inspect(engine).get_table_names() == []
    finally:
        engine.dispose()


def test_postgresql_offline_sql_without_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(database_url="postgresql://"),
    )
    config = Config(str(ROOT / "alembic.ini"))
    output = StringIO()
    config.output_buffer = output
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE categories" in sql
    assert "CREATE TABLE products" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "UUID" in sql
    assert "CREATE TYPE" not in sql
    assert "unit VARCHAR(5)" in sql
