"""Validated order commands and response contracts with public UUIDs only."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.enums import OrderStatus, PaymentStatus, ProductUnit
from app.models.catalog import MAX_QUANTITY
from app.schemas.catalog import Barcode, Command

TerminalCode = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")]
PositiveQuantity = Annotated[int, Field(strict=True, ge=1, le=MAX_QUANTITY)]


class OrderCreate(Command):
    terminal_code: TerminalCode = "main"


class ItemAdd(Command):
    barcode: Barcode | None = None
    product_id: UUID | None = None
    quantity: PositiveQuantity = 1

    @model_validator(mode="after")
    def exactly_one_identifier(self) -> "ItemAdd":
        if (self.barcode is None) == (self.product_id is None):
            raise ValueError("Provide exactly one of barcode or product_id")
        return self


class ItemPatch(Command):
    quantity: PositiveQuantity


class PaymentSummary(BaseModel):
    public_id: UUID
    order_id: UUID
    status: PaymentStatus
    amount_minor: int
    currency: str
    pay_url: str | None
    expires_at: datetime | None
    seconds_left: int
    failure_reason: str | None
    needs_review: bool


class OrderItemRead(BaseModel):
    public_id: UUID
    product_id: UUID
    product_name: str
    barcode: str
    unit: ProductUnit
    unit_price_minor: int
    quantity: int
    line_total_minor: int


class OrderRead(BaseModel):
    public_id: UUID
    number: str
    terminal_code: str
    status: OrderStatus
    total_minor: int
    currency: str
    created_at: datetime
    paid_at: datetime | None
    cancelled_at: datetime | None
    items: list[OrderItemRead]
    payment: PaymentSummary | None


class OrderPage(BaseModel):
    items: list[OrderRead]
    total: int
    limit: int
    offset: int


class ReceiptRead(OrderRead):
    payment_method: Literal["QR"] = "QR"
    disclaimer: str = "Учебный проект, не фискальный чек"


class DisplayRead(BaseModel):
    state: Literal["idle", "cart", "awaiting_payment", "paid", "payment_failed"]
    order: OrderRead | None
    payment: PaymentSummary | None
    seconds_left: int
    failure_reason: str | None = None
