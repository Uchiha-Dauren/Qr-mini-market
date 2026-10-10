"""Provider contracts independent of a particular bank implementation."""

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import (
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    model_validator,
)


class BankStatus(StrEnum):
    CREATED = "CREATED"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class InvoiceSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    invoice_id: UUID
    merchant_reference: UUID
    amount_minor: StrictInt = Field(gt=0, le=2**63 - 1)
    currency: str = Field(min_length=3, max_length=3)
    status: BankStatus
    pay_url: AnyHttpUrl = Field(max_length=2048)
    expires_at: AwareDatetime
    paid_at: AwareDatetime | None = None
    failure_reason: str | None = Field(default=None, max_length=100)
    event_id: UUID | None = None

    @model_validator(mode="after")
    def validate_final_event(self) -> "InvoiceSnapshot":
        if self.status is not BankStatus.CREATED and self.event_id is None:
            raise ValueError("A final invoice must include its durable event ID")
        if self.pay_url.username is not None or self.pay_url.password is not None:
            raise ValueError("Payment URLs must not contain credentials")
        return self


class ProviderUnavailable(Exception):
    """A safe failure; only proven non-creation allows reservation compensation."""

    def __init__(self, *, definitely_not_created: bool = False) -> None:
        super().__init__("Payment provider unavailable")
        self.definitely_not_created = definitely_not_created


class PaymentProvider(Protocol):
    def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        merchant_reference: UUID,
        description: str,
        ttl_seconds: int,
    ) -> InvoiceSnapshot: ...

    def get_invoice_status(self, invoice_id: UUID) -> InvoiceSnapshot: ...

    def cancel_invoice(self, invoice_id: UUID) -> InvoiceSnapshot: ...
