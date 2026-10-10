"""Create categories and products.

Revision ID: 0001_catalog
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_catalog"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(create_constraint=True, name=op.f("ck_categories_active_bool")),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(name) BETWEEN 1 AND 100", name=op.f("ck_categories_name_length")
        ),
        sa.CheckConstraint(
            "length(slug) BETWEEN 1 AND 100", name=op.f("ck_categories_slug_length")
        ),
        sa.CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name=op.f("ck_categories_not_own_parent")
        ),
        sa.CheckConstraint(
            "sort_order BETWEEN -2147483648 AND 2147483647 "
            "AND sort_order = CAST(sort_order AS INTEGER)",
            name=op.f("ck_categories_sort_order_range"),
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["categories.id"],
            name=op.f("fk_categories_parent_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("public_id", name=op.f("uq_categories_public_id")),
        sa.UniqueConstraint("slug", name=op.f("uq_categories_slug")),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("name_normalized", sa.String(600), nullable=False),
        sa.Column("barcode", sa.String(13), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column(
            "unit",
            sa.Enum(
                "PIECE",
                "KG",
                native_enum=False,
                create_constraint=True,
                name=op.f("ck_products_product_unit"),
            ),
            nullable=False,
        ),
        sa.Column("price_minor", sa.BigInteger(), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("min_stock_quantity", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(create_constraint=True, name=op.f("ck_products_active_bool")),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 200", name=op.f("ck_products_name_length")),
        sa.CheckConstraint(
            "length(name_normalized) BETWEEN 1 AND 600",
            name=op.f("ck_products_name_normalized_length"),
        ),
        sa.CheckConstraint("length(barcode) IN (8, 13)", name=op.f("ck_products_barcode_length")),
        sa.CheckConstraint(
            "description IS NULL OR length(description) <= 2000",
            name=op.f("ck_products_description_length"),
        ),
        sa.CheckConstraint(
            "price_minor BETWEEN 0 AND 9223372036854775807 "
            "AND price_minor = CAST(price_minor AS BIGINT)",
            name=op.f("ck_products_price_range"),
        ),
        sa.CheckConstraint(
            "stock_quantity BETWEEN 0 AND 2147483647 "
            "AND stock_quantity = CAST(stock_quantity AS INTEGER)",
            name=op.f("ck_products_stock_range"),
        ),
        sa.CheckConstraint(
            "reserved_quantity BETWEEN 0 AND 2147483647 "
            "AND reserved_quantity = CAST(reserved_quantity AS INTEGER)",
            name=op.f("ck_products_reserved_range"),
        ),
        sa.CheckConstraint(
            "min_stock_quantity BETWEEN 0 AND 2147483647 "
            "AND min_stock_quantity = CAST(min_stock_quantity AS INTEGER)",
            name=op.f("ck_products_min_stock_range"),
        ),
        sa.CheckConstraint(
            "reserved_quantity <= stock_quantity", name=op.f("ck_products_reserved_within_stock")
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_products_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("public_id", name=op.f("uq_products_public_id")),
    )
    op.create_index("ix_products_barcode", "products", ["barcode"], unique=True)
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_index("ix_products_name_normalized", "products", ["name_normalized"])


def downgrade() -> None:
    op.drop_table("products")
    # SQLite RESTRICT also applies while dropping a populated self-referencing table.
    op.execute("UPDATE categories SET parent_id = NULL")
    op.drop_table("categories")
