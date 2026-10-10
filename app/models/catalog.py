"""Catalog tables and database invariants, independent of HTTP routes."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Enum, ForeignKey, String, Uuid, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column, validates
from sqlalchemy.sql import true

from app.core.barcodes import validate_ean
from app.core.enums import ProductUnit
from app.db.base import Base
from app.db.types import UTCDateTime

MAX_PRICE_MINOR = 2**63 - 1
MAX_QUANTITY = 2**31 - 1


def utc_now() -> datetime:
    return datetime.now(UTC)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 100", name="name_length"),
        CheckConstraint("length(slug) BETWEEN 1 AND 100", name="slug_length"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="not_own_parent"),
        CheckConstraint(
            "sort_order BETWEEN -2147483648 AND 2147483647 "
            "AND sort_order = CAST(sort_order AS INTEGER)",
            name="sort_order_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="active_bool"), default=True, server_default=true()
    )


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 200", name="name_length"),
        CheckConstraint("length(name_normalized) BETWEEN 1 AND 600", name="name_normalized_length"),
        CheckConstraint("length(barcode) IN (8, 13)", name="barcode_length"),
        CheckConstraint(
            "description IS NULL OR length(description) <= 2000", name="description_length"
        ),
        CheckConstraint(
            f"price_minor BETWEEN 0 AND {MAX_PRICE_MINOR} "
            "AND price_minor = CAST(price_minor AS BIGINT)",
            name="price_range",
        ),
        CheckConstraint(
            f"stock_quantity BETWEEN 0 AND {MAX_QUANTITY} "
            "AND stock_quantity = CAST(stock_quantity AS INTEGER)",
            name="stock_range",
        ),
        CheckConstraint(
            f"reserved_quantity BETWEEN 0 AND {MAX_QUANTITY} "
            "AND reserved_quantity = CAST(reserved_quantity AS INTEGER)",
            name="reserved_range",
        ),
        CheckConstraint(
            f"min_stock_quantity BETWEEN 0 AND {MAX_QUANTITY} "
            "AND min_stock_quantity = CAST(min_stock_quantity AS INTEGER)",
            name="min_stock_range",
        ),
        CheckConstraint("reserved_quantity <= stock_quantity", name="reserved_within_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    name_normalized: Mapped[str] = mapped_column(String(600), index=True)
    barcode: Mapped[str] = mapped_column(String(13), unique=True, index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    unit: Mapped[ProductUnit] = mapped_column(
        Enum(
            ProductUnit,
            values_callable=lambda members: [member.value for member in members],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="product_unit",
        )
    )
    price_minor: Mapped[int] = mapped_column(BigInteger())
    stock_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    reserved_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    min_stock_quantity: Mapped[int] = mapped_column(default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="active_bool"), default=True, server_default=true()
    )
    description: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)

    @validates("barcode")
    def validate_barcode(self, _key: str, value: str) -> str:
        return validate_ean(value)

    @validates("price_minor", "stock_quantity", "reserved_quantity", "min_stock_quantity")
    def validate_integer(self, key: str, value: int) -> int:
        maximum = MAX_PRICE_MINOR if key == "price_minor" else MAX_QUANTITY
        if type(value) is not int or not 0 <= value <= maximum:
            raise ValueError(f"{key} must be an integer between 0 and {maximum}")
        return value


@event.listens_for(Product, "before_insert")
@event.listens_for(Product, "before_update")
def normalize_product_name(
    _mapper: Mapper[Product], _connection: Connection, target: Product
) -> None:
    """Keep normalization in sync for ORM writes, including renames."""
    if not isinstance(target.name, str) or not 1 <= len(target.name.strip()) <= 200:
        raise ValueError("Product name must contain between 1 and 200 characters")
    target.name = target.name.strip()
    target.name_normalized = target.name.casefold()
