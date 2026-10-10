"""Shop users, order snapshots, payments, immutable events, and stock ledger."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import OrderStatus, PaymentStatus, ProductUnit, StockReason, UserRole
from app.db.base import Base
from app.db.types import UTCDateTime
from app.models.catalog import utc_now


def string_enum(kind: type[StrEnum], name: str) -> Enum:
    return Enum(
        kind,
        values_callable=lambda members: [member.value for member in members],
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        name=name,
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("length(username) BETWEEN 3 AND 64", name="username_length"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    role: Mapped[UserRole] = mapped_column(string_enum(UserRole, "user_role"))
    is_active: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="active_bool"), default=True, server_default=true()
    )


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND total_minor = CAST(total_minor AS BIGINT)",
            name="total_range",
        ),
        CheckConstraint("currency = 'KZT'", name="currency"),
        CheckConstraint("length(terminal_code) BETWEEN 1 AND 64", name="terminal_length"),
        Index("ix_orders_status_terminal_code", "status", "terminal_code"),
        Index(
            "uq_orders_active_terminal",
            "terminal_code",
            unique=True,
            sqlite_where=text("status IN ('OPEN', 'PENDING_PAYMENT')"),
            postgresql_where=text("status IN ('OPEN', 'PENDING_PAYMENT')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    number: Mapped[str] = mapped_column(String(64), unique=True)
    terminal_code: Mapped[str] = mapped_column(String(64), default="main", server_default="main")
    status: Mapped[OrderStatus] = mapped_column(
        string_enum(OrderStatus, "order_status"), default=OrderStatus.OPEN, server_default="OPEN"
    )
    total_minor: Mapped[int] = mapped_column(BigInteger(), default=0, server_default="0")
    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")
    cashier_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint("order_id", "product_id"),
        CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND quantity = CAST(quantity AS INTEGER)",
            name="quantity_range",
        ),
        CheckConstraint(
            "unit_price_minor BETWEEN 0 AND 9223372036854775807 "
            "AND unit_price_minor = CAST(unit_price_minor AS BIGINT)",
            name="price_range",
        ),
        CheckConstraint(
            "line_total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND line_total_minor = CAST(line_total_minor AS BIGINT)",
            name="total_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    product_name: Mapped[str] = mapped_column(String(200))
    barcode: Mapped[str] = mapped_column(String(13))
    unit: Mapped[ProductUnit] = mapped_column(string_enum(ProductUnit, "product_unit"))
    unit_price_minor: Mapped[int] = mapped_column(BigInteger())
    quantity: Mapped[int] = mapped_column()
    line_total_minor: Mapped[int] = mapped_column(BigInteger())


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("creation_attempts >= 0", name="creation_attempts_nonnegative"),
        CheckConstraint(
            "amount_minor BETWEEN 1 AND 9223372036854775807 "
            "AND amount_minor = CAST(amount_minor AS BIGINT)",
            name="amount_range",
        ),
        CheckConstraint("currency = 'KZT'", name="currency"),
        Index("ix_payments_status_expires_at", "status", "expires_at"),
        Index(
            "uq_payments_pending_order",
            "order_id",
            unique=True,
            sqlite_where=text("status = 'PENDING'"),
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(Uuid(), default=uuid4, unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column(
        String(32), default="mock_bank", server_default="mock_bank"
    )
    provider_invoice_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    creation_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    creation_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    amount_minor: Mapped[int] = mapped_column(BigInteger())
    currency: Mapped[str] = mapped_column(String(3), default="KZT", server_default="KZT")
    status: Mapped[PaymentStatus] = mapped_column(
        string_enum(PaymentStatus, "payment_status"),
        default=PaymentStatus.PENDING,
        server_default="PENDING",
    )
    pay_url: Mapped[str | None] = mapped_column(String(2048))
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    needs_review: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="review_bool"), default=False, server_default=false()
    )
    review_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(50))
    raw_body: Mapped[str] = mapped_column(Text())
    signature_valid: Mapped[bool] = mapped_column(
        Boolean(create_constraint=True, name="signature_bool")
    )
    outcome: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint(
            "delta BETWEEN -2147483647 AND 2147483647 "
            "AND delta <> 0 AND delta = CAST(delta AS INTEGER)",
            name="delta_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    delta: Mapped[int] = mapped_column()
    reason: Mapped[StockReason] = mapped_column(string_enum(StockReason, "stock_reason"))
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
