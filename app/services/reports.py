"""Read-only reports over paid snapshots and administrative stock/payment views."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import OrderStatus
from app.core.errors import AppError
from app.models import Category, Order, OrderItem, Payment, Product


def _pagination(limit: int, offset: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise AppError(
            422, "INVALID_PAGINATION", "Укажите limit от 1 до 100 и offset не меньше нуля."
        )


def sales_report(
    factory: sessionmaker[Session],
    settings: Settings,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Use local calendar days, UTC filtering, and exact Python integer accumulation.

    Product names/prices/units are order snapshots. Categories are the current
    catalog assignment because the order schema has no category snapshot.
    """
    timezone = ZoneInfo(settings.timezone)
    last = date_to or datetime.now(timezone).date()
    first = date_from or last.replace(day=1)
    if first > last or (last - first).days >= 366 or last == date.max:
        raise AppError(422, "INVALID_DATE_RANGE", "Укажите период от 1 до 366 дней.")
    try:
        start_utc = datetime.combine(first, time.min, timezone).astimezone(UTC)
        end_utc = datetime.combine(last + timedelta(days=1), time.min, timezone).astimezone(UTC)
    except (OverflowError, ValueError):
        raise AppError(422, "INVALID_DATE_RANGE", "Даты выходят за допустимый диапазон.") from None
    conditions = (
        Order.status == OrderStatus.PAID,
        Order.paid_at >= start_utc,
        Order.paid_at < end_utc,
    )
    days: dict[str, dict] = {}
    categories: dict[str, dict] = {}
    products: dict[tuple[str, str, str], dict] = {}
    count = 0
    revenue = 0
    with factory() as session:
        # One SQL statement shares a single MVCC snapshot under READ COMMITTED.
        # Separate header/item queries could observe a newly paid order differently.
        rows = session.execute(
            select(
                Order.id.label("order_id"),
                Order.paid_at,
                OrderItem.product_name,
                OrderItem.unit,
                OrderItem.quantity,
                OrderItem.line_total_minor,
                Product.public_id,
                Category.public_id.label("category_public_id"),
                Category.name.label("category_name"),
            )
            .select_from(Order)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(Product, Product.id == OrderItem.product_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
            .order_by(Order.id, OrderItem.id)
        ).yield_per(200)
        previous_order = None
        for row in rows:
            day_key = row.paid_at.astimezone(timezone).date().isoformat()
            day = days.setdefault(day_key, {"date": day_key, "orders_count": 0, "revenue_minor": 0})
            if previous_order != row.order_id:
                day["orders_count"] += 1
                count += 1
                previous_order = row.order_id
            day["revenue_minor"] += row.line_total_minor
            revenue += row.line_total_minor
            category_key = str(row.category_public_id)
            category = categories.setdefault(
                category_key,
                {"public_id": category_key, "name": row.category_name, "revenue_minor": 0},
            )
            category["revenue_minor"] += row.line_total_minor
            # Keep historical renamed products or changed units distinguishable.
            product_key = (str(row.public_id), row.product_name, row.unit.value)
            product = products.setdefault(
                product_key,
                {
                    "public_id": str(row.public_id),
                    "name": row.product_name,
                    "unit": row.unit.value,
                    "quantity": 0,
                    "revenue_minor": 0,
                },
            )
            product["quantity"] += row.quantity
            product["revenue_minor"] += row.line_total_minor
    for item in [*days.values(), *categories.values(), *products.values()]:
        item["revenue_minor_text"] = str(item["revenue_minor"])
    return {
        "date_from": first.isoformat(),
        "date_to": last.isoformat(),
        "timezone": settings.timezone,
        "currency": settings.currency,
        "orders_count": count,
        "revenue_minor": revenue,
        "revenue_minor_text": str(revenue),
        "days": sorted(days.values(), key=lambda item: item["date"]),
        "categories": sorted(
            categories.values(), key=lambda item: (-item["revenue_minor"], item["public_id"])
        ),
        "products": sorted(
            products.values(),
            key=lambda item: (-item["revenue_minor"], item["name"], item["public_id"]),
        ),
    }


def low_stock_report(factory: sessionmaker[Session], limit: int = 50, offset: int = 0) -> dict:
    """Include active products whose unreserved stock has reached its threshold."""
    _pagination(limit, offset)
    available = Product.stock_quantity - Product.reserved_quantity
    conditions = (Product.is_active.is_(True), available <= Product.min_stock_quantity)
    with factory() as session:
        total = session.scalar(select(func.count()).select_from(Product).where(*conditions))
        rows = session.execute(
            select(Product, Category.public_id)
            .join(Category, Category.id == Product.category_id)
            .where(*conditions)
            .order_by(available, Product.id)
            .limit(limit)
            .offset(offset)
        )
        items = [
            {
                "public_id": str(product.public_id),
                "name": product.name,
                "barcode": product.barcode,
                "unit": product.unit.value,
                "category_id": str(category_uuid),
                "stock_quantity": product.stock_quantity,
                "available_quantity": product.stock_quantity - product.reserved_quantity,
                "min_stock_quantity": product.min_stock_quantity,
            }
            for product, category_uuid in rows
        ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def payments_review_report(
    factory: sessionmaker[Session], limit: int = 50, offset: int = 0
) -> dict:
    """Expose review reasons to admins without provider identifiers or raw event bodies."""
    _pagination(limit, offset)
    with factory() as session:
        total = session.scalar(
            select(func.count()).select_from(Payment).where(Payment.needs_review.is_(True))
        )
        rows = session.execute(
            select(Payment, Order.public_id)
            .join(Order, Order.id == Payment.order_id)
            .where(Payment.needs_review.is_(True))
            .order_by(Payment.created_at.desc(), Payment.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [
            {
                "public_id": str(payment.public_id),
                "order_id": str(order_uuid),
                "status": payment.status.value,
                "amount_minor": payment.amount_minor,
                "currency": payment.currency,
                "needs_review": payment.needs_review,
                "review_reason": payment.review_reason,
                "created_at": payment.created_at,
                "updated_at": payment.updated_at,
            }
            for payment, order_uuid in rows
        ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}
