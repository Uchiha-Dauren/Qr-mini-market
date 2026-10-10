"""Import mapped classes so Alembic sees the complete shop metadata."""

from app.models.catalog import Category, Product
from app.models.commerce import Order, OrderItem, Payment, PaymentEvent, StockMovement, User

__all__ = [
    "Category",
    "Product",
    "Order",
    "OrderItem",
    "Payment",
    "PaymentEvent",
    "StockMovement",
    "User",
]
