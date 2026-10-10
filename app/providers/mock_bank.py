"""HTTP adapter; it deliberately imports no code from the bank application."""

from uuid import UUID

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.providers.base import InvoiceSnapshot, ProviderUnavailable


class MockBankProvider:
    def __init__(self, client: httpx.Client, settings: Settings) -> None:
        self.client = client
        self.base_url = str(settings.bank_base_url).rstrip("/")
        self.api_key = settings.bank_merchant_api_key.get_secret_value()

    def _request(self, method: str, path: str, *, payload: dict | None = None) -> InvoiceSnapshot:
        try:
            response = self.client.request(
                method,
                self.base_url + path,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
        except httpx.ConnectError:
            raise ProviderUnavailable(definitely_not_created=True) from None
        except httpx.HTTPError:
            raise ProviderUnavailable() from None
        if response.status_code >= 400:
            raise ProviderUnavailable(
                definitely_not_created=response.status_code in (400, 401, 403, 422)
            )
        try:
            return InvoiceSnapshot.model_validate(response.json())
        except (ValueError, ValidationError):
            raise ProviderUnavailable() from None

    def create_invoice(
        self,
        *,
        amount_minor: int,
        currency: str,
        merchant_reference: UUID,
        description: str,
        ttl_seconds: int,
    ) -> InvoiceSnapshot:
        return self._request(
            "POST",
            "/api/merchant/invoices",
            payload={
                "amount_minor": amount_minor,
                "currency": currency,
                "merchant_reference": str(merchant_reference),
                "description": description,
                "ttl_seconds": ttl_seconds,
            },
        )

    def get_invoice_status(self, invoice_id: UUID) -> InvoiceSnapshot:
        return self._request("GET", f"/api/merchant/invoices/{invoice_id}")

    def cancel_invoice(self, invoice_id: UUID) -> InvoiceSnapshot:
        try:
            return self._request("POST", f"/api/merchant/invoices/{invoice_id}/cancel")
        except ProviderUnavailable:
            # A concurrent payment can make cancellation return 409; a lost cancel
            # response can also hide a final result. Always reconcile before release.
            return self.get_invoice_status(invoice_id)
