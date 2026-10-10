"""Strict merchant and customer request contracts."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_minor: Annotated[StrictInt, Field(gt=0, le=2**63 - 1)]
    currency: Literal["KZT"]
    merchant_reference: UUID
    description: str = Field(min_length=1, max_length=500)
    ttl_seconds: Annotated[StrictInt, Field(gt=0, le=86400)]


class PayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID
