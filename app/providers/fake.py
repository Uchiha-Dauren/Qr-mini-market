"""Deterministic in-memory provider for tests, never selected by environment settings."""

from datetime import UTC, datetime, timedelta
from threading import RLock
from uuid import UUID, uuid4

from app.providers.base import BankStatus, InvoiceSnapshot, ProviderUnavailable


class FakeProvider:
    def __init__(self) -> None:
        self.invoices: dict[UUID, InvoiceSnapshot] = {}
        self.references: dict[UUID, UUID] = {}
        self.create_calls = 0
        self.status_calls = 0
        self.create_error: ProviderUnavailable | None = None
        self.lock = RLock()

    def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        merchant_reference: UUID,
        description: str,
        ttl_seconds: int,
    ) -> InvoiceSnapshot:
        with self.lock:
            self.create_calls += 1
            if self.create_error is not None:
                raise self.create_error
            if merchant_reference in self.references:
                invoice = self.invoices[self.references[merchant_reference]]
                if invoice.amount_minor != amount_minor or invoice.currency != currency:
                    raise ProviderUnavailable()
                return invoice
            invoice_id = uuid4()
            invoice = InvoiceSnapshot(
                invoice_id=invoice_id,
                merchant_reference=merchant_reference,
                amount_minor=amount_minor,
                currency=currency,
                status=BankStatus.CREATED,
                pay_url=f"http://bank.test/pay/{uuid4().hex}",
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            )
            self.invoices[invoice_id] = invoice
            self.references[merchant_reference] = invoice_id
            return invoice

    def get_invoice_status(self, invoice_id: UUID) -> InvoiceSnapshot:
        with self.lock:
            self.status_calls += 1
            invoice = self.invoices[invoice_id]
            if invoice.status is BankStatus.CREATED and invoice.expires_at <= datetime.now(UTC):
                return self.finish(invoice_id, BankStatus.EXPIRED)
            return invoice

    def cancel_invoice(self, invoice_id: UUID) -> InvoiceSnapshot:
        with self.lock:
            invoice = self.get_invoice_status(invoice_id)
            if invoice.status is BankStatus.CREATED:
                return self.finish(invoice_id, BankStatus.CANCELLED)
            return invoice

    def finish(
        self, invoice_id: UUID, status: BankStatus, failure_reason: str | None = None
    ) -> InvoiceSnapshot:
        with self.lock:
            invoice = self.invoices[invoice_id]
            if invoice.status is not BankStatus.CREATED:
                return invoice
            if status is BankStatus.CREATED:
                raise ValueError("A final status is required")
            invoice = invoice.model_copy(
                update={
                    "status": status,
                    "event_id": uuid4(),
                    "failure_reason": failure_reason,
                    "paid_at": datetime.now(UTC) if status is BankStatus.PAID else None,
                }
            )
            self.invoices[invoice_id] = invoice
            return invoice
