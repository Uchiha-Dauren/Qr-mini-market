"""Shared domain values used by calculations and future catalog models."""

from enum import StrEnum


class ProductUnit(StrEnum):
    PIECE = "PIECE"
    KG = "KG"


class OrderStatus(StrEnum):
    OPEN = "OPEN"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class StockReason(StrEnum):
    SALE = "SALE"
    RESTOCK = "RESTOCK"
    ADJUSTMENT = "ADJUSTMENT"


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    CASHIER = "CASHIER"
