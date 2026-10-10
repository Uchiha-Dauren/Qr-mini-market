"""Public payment contracts and bounded signed notification input."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictInt

from app.core.enums import PaymentStatus


class PaymentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_id: UUID
    order_id: UUID
    status: PaymentStatus
    amount_minor: int
    currency: str
    pay_url: str | None
    expires_at: AwareDatetime | None
    seconds_left: int
    failure_reason: str | None
    needs_review: bool


class EventData(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    invoice_id: UUID
    merchant_reference: UUID
    amount_minor: StrictInt = Field(gt=0, le=2**63 - 1)
    currency: str = Field(min_length=3, max_length=3)
    failure_reason: str | None = Field(default=None, max_length=100)


class BankEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    event_id: UUID
    type: Literal["invoice.paid", "invoice.failed", "invoice.expired", "invoice.cancelled"]
    created_at: AwareDatetime
    data: EventData
