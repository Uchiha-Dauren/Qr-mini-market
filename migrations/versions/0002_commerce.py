"""Add users orders payments and stock ledger

Revision ID: 0002_commerce
Revises: 0001_catalog
Create Date: 2026-10-10 05:57:15.907599
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_commerce"
down_revision: str | Sequence[str] | None = "0001_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "ADMIN", "CASHIER", name="user_role", native_enum=False, create_constraint=False
            ),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(create_constraint=False, name="active_bool"),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('ADMIN', 'CASHIER')", name=op.f("ck_users_user_role")),
        sa.CheckConstraint("is_active IN (0, 1)", name=op.f("ck_users_active_bool")),
        sa.CheckConstraint(
            "length(username) BETWEEN 3 AND 64", name=op.f("ck_users_username_length")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("public_id", name=op.f("uq_users_public_id")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=False),
        sa.Column("terminal_code", sa.String(length=64), server_default="main", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "OPEN",
                "PENDING_PAYMENT",
                "PAID",
                "CANCELLED",
                name="order_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="OPEN",
            nullable=False,
        ),
        sa.Column("total_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="KZT", nullable=False),
        sa.Column("cashier_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("currency = 'KZT'", name=op.f("ck_orders_currency")),
        sa.CheckConstraint(
            "status IN ('OPEN', 'PENDING_PAYMENT', 'PAID', 'CANCELLED')",
            name=op.f("ck_orders_order_status"),
        ),
        sa.CheckConstraint(
            "length(terminal_code) BETWEEN 1 AND 64", name=op.f("ck_orders_terminal_length")
        ),
        sa.CheckConstraint(
            "total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND total_minor = CAST(total_minor AS BIGINT)",
            name=op.f("ck_orders_total_range"),
        ),
        sa.ForeignKeyConstraint(
            ["cashier_id"],
            ["users.id"],
            name=op.f("fk_orders_cashier_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_orders")),
        sa.UniqueConstraint("number", name=op.f("uq_orders_number")),
        sa.UniqueConstraint("public_id", name=op.f("uq_orders_public_id")),
    )
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.create_index(
            "ix_orders_status_terminal_code", ["status", "terminal_code"], unique=False
        )
        batch_op.create_index(
            "uq_orders_active_terminal",
            ["terminal_code"],
            unique=True,
            sqlite_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
            postgresql_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
        )

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("barcode", sa.String(length=13), nullable=False),
        sa.Column(
            "unit",
            sa.Enum("PIECE", "KG", name="product_unit", native_enum=False, create_constraint=False),
            nullable=False,
        ),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("line_total_minor", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("unit IN ('PIECE', 'KG')", name=op.f("ck_order_items_product_unit")),
        sa.CheckConstraint(
            "line_total_minor BETWEEN 0 AND 9223372036854775807 "
            "AND line_total_minor = CAST(line_total_minor AS BIGINT)",
            name=op.f("ck_order_items_total_range"),
        ),
        sa.CheckConstraint(
            "quantity BETWEEN 1 AND 2147483647 AND quantity = CAST(quantity AS INTEGER)",
            name=op.f("ck_order_items_quantity_range"),
        ),
        sa.CheckConstraint(
            "unit_price_minor BETWEEN 0 AND 9223372036854775807 "
            "AND unit_price_minor = CAST(unit_price_minor AS BIGINT)",
            name=op.f("ck_order_items_price_range"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_order_items_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_order_items_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_items")),
        sa.UniqueConstraint(
            "order_id", "product_id", name=op.f("uq_order_items_order_id_product_id")
        ),
        sa.UniqueConstraint("public_id", name=op.f("uq_order_items_public_id")),
    )
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_order_items_order_id"), ["order_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="mock_bank", nullable=False),
        sa.Column("provider_invoice_id", sa.String(length=64), nullable=True),
        sa.Column("creation_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creation_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="KZT", nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "SUCCEEDED",
                "FAILED",
                "EXPIRED",
                "CANCELLED",
                name="payment_status",
                native_enum=False,
                create_constraint=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("pay_url", sa.String(length=2048), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "needs_review",
            sa.Boolean(create_constraint=False, name="review_bool"),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("review_reason", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("currency = 'KZT'", name=op.f("ck_payments_currency")),
        sa.CheckConstraint(
            "creation_attempts >= 0", name=op.f("ck_payments_creation_attempts_nonnegative")
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'EXPIRED', 'CANCELLED')",
            name=op.f("ck_payments_payment_status"),
        ),
        sa.CheckConstraint(
            "amount_minor BETWEEN 1 AND 9223372036854775807 "
            "AND amount_minor = CAST(amount_minor AS BIGINT)",
            name=op.f("ck_payments_amount_range"),
        ),
        sa.CheckConstraint("needs_review IN (0, 1)", name=op.f("ck_payments_review_bool")),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_payments_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
        sa.UniqueConstraint("provider_invoice_id", name=op.f("uq_payments_provider_invoice_id")),
        sa.UniqueConstraint("public_id", name=op.f("uq_payments_public_id")),
    )
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_payments_order_id"), ["order_id"], unique=False)
        batch_op.create_index(
            "ix_payments_status_expires_at", ["status", "expires_at"], unique=False
        )
        batch_op.create_index(
            "uq_payments_pending_order",
            ["order_id"],
            unique=True,
            sqlite_where=sa.text("status = 'PENDING'"),
            postgresql_where=sa.text("status = 'PENDING'"),
        )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column(
            "reason",
            sa.Enum(
                "SALE",
                "RESTOCK",
                "ADJUSTMENT",
                name="stock_reason",
                native_enum=False,
                create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reason IN ('SALE', 'RESTOCK', 'ADJUSTMENT')",
            name=op.f("ck_stock_movements_stock_reason"),
        ),
        sa.CheckConstraint(
            "delta BETWEEN -2147483647 AND 2147483647 AND delta <> 0 "
            "AND delta = CAST(delta AS INTEGER)",
            name=op.f("ck_stock_movements_delta_range"),
        ),
        sa.ForeignKeyConstraint(
            ["order_id"],
            ["orders.id"],
            name=op.f("fk_stock_movements_order_id_orders"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_stock_movements_product_id_products"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stock_movements")),
    )
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_stock_movements_order_id"), ["order_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_stock_movements_product_id"), ["product_id"], unique=False
        )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_event_id", sa.String(length=100), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("raw_body", sa.Text(), nullable=False),
        sa.Column(
            "signature_valid",
            sa.Boolean(create_constraint=False, name="signature_bool"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "signature_valid IN (0, 1)", name=op.f("ck_payment_events_signature_bool")
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.id"],
            name=op.f("fk_payment_events_payment_id_payments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_events")),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name=op.f("uq_payment_events_provider_provider_event_id"),
        ),
    )
    with op.batch_alter_table("payment_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_payment_events_payment_id"), ["payment_id"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("payment_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_events_payment_id"))

    op.drop_table("payment_events")
    with op.batch_alter_table("stock_movements", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_stock_movements_product_id"))
        batch_op.drop_index(batch_op.f("ix_stock_movements_order_id"))

    op.drop_table("stock_movements")
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_payments_pending_order",
            sqlite_where=sa.text("status = 'PENDING'"),
            postgresql_where=sa.text("status = 'PENDING'"),
        )
        batch_op.drop_index("ix_payments_status_expires_at")
        batch_op.drop_index(batch_op.f("ix_payments_order_id"))

    op.drop_table("payments")
    with op.batch_alter_table("order_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_order_items_order_id"))

    op.drop_table("order_items")
    with op.batch_alter_table("orders", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_orders_active_terminal",
            sqlite_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
            postgresql_where=sa.text("status IN ('OPEN', 'PENDING_PAYMENT')"),
        )
        batch_op.drop_index("ix_orders_status_terminal_code")

    op.drop_table("orders")
    op.drop_table("users")
