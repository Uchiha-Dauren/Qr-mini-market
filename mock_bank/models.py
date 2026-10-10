"""Bank balances, invoices, immutable events, and durable delivery attempts."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from mock_bank.db import Base, UTCDateTime, utc_now


class InvoiceStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    __table_args__ = (
        CheckConstraint(
            "balance_minor >= 0 AND balance_minor <= 9223372036854775807", name="balance_range"
        ),
        CheckConstraint("balance_minor = CAST(balance_minor AS BIGINT)", name="balance_integer"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    seed_key: Mapped[str | None] = mapped_column(String(30), unique=True)
    holder_name: Mapped[str] = mapped_column(String(100))
    balance_minor: Mapped[int] = mapped_column(BigInteger())


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(
            "amount_minor > 0 AND amount_minor <= 9223372036854775807", name="amount_positive"
        ),
        CheckConstraint("amount_minor = CAST(amount_minor AS BIGINT)", name="amount_integer"),
        CheckConstraint("currency = 'KZT'", name="invoice_currency"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    merchant_reference: Mapped[UUID] = mapped_column(Uuid(), unique=True)
    merchant_name: Mapped[str] = mapped_column(String(200))
    amount_minor: Mapped[int] = mapped_column(BigInteger())
    currency: Mapped[str] = mapped_column(String(3), default="KZT")
    description: Mapped[str] = mapped_column(String(500))
    ttl_seconds: Mapped[int] = mapped_column()
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, native_enum=False, create_constraint=True, name="invoice_status"),
        default=InvoiceStatus.CREATED,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    paid_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    paid_by_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="RESTRICT")
    )
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class BankTransaction(Base):
    __tablename__ = "bank_transactions"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), unique=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="RESTRICT")
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger())
    status: Mapped[str] = mapped_column(String(20))
    failure_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class BankEvent(Base):
    __tablename__ = "bank_events"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    invoice_id: Mapped[UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="RESTRICT"), unique=True
    )
    event_type: Mapped[str] = mapped_column(String(40))
    raw_body: Mapped[str] = mapped_column(Text())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    delivered: Mapped[bool] = mapped_column(Boolean(), default=False)
    stopped: Mapped[bool] = mapped_column(Boolean(), default=False)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid())
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime())


class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("bank_events.id", ondelete="RESTRICT"), index=True
    )
    attempt: Mapped[int] = mapped_column()
    requested_at: Mapped[datetime] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    response_status: Mapped[int | None] = mapped_column()
    error_kind: Mapped[str | None] = mapped_column(String(100))
