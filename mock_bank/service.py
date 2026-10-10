"""Atomic invoice transitions and stable final events; never performs HTTP."""

import json
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.config import Settings
from mock_bank.db import run_write, utc_now
from mock_bank.errors import BankError
from mock_bank.models import BankAccount, BankEvent, BankTransaction, Invoice, InvoiceStatus
from mock_bank.schemas import InvoiceCreate


class BankService:
    def __init__(self, factory: sessionmaker[Session], settings: Settings) -> None:
        self.factory = factory
        self.settings = settings

    def snapshot(self, session: Session, invoice: Invoice) -> dict:
        event_id = session.scalar(select(BankEvent.id).where(BankEvent.invoice_id == invoice.id))
        return {
            "invoice_id": str(invoice.id),
            "merchant_reference": str(invoice.merchant_reference),
            "merchant_name": invoice.merchant_name,
            "amount_minor": invoice.amount_minor,
            "amount_minor_text": str(invoice.amount_minor),
            "currency": invoice.currency,
            "description": invoice.description,
            "status": invoice.status.value,
            "pay_url": f"{str(self.settings.bank_public_url).rstrip('/')}/pay/{invoice.token}",
            "expires_at": invoice.expires_at.isoformat(),
            "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
            "failure_reason": invoice.failure_reason,
            "event_id": str(event_id) if event_id else None,
            "seconds_left": max(0, int((invoice.expires_at - utc_now()).total_seconds())),
        }

    @staticmethod
    def _find(session: Session, identifier: UUID | str) -> Invoice:
        condition = (
            Invoice.id == identifier
            if isinstance(identifier, UUID)
            else Invoice.token == identifier
        )
        invoice = session.scalar(select(Invoice).where(condition).with_for_update())
        if invoice is None:
            raise BankError(404, "INVOICE_NOT_FOUND", "Счёт не найден.")
        return invoice

    @staticmethod
    def _finalize(
        session: Session,
        invoice: Invoice,
        status: InvoiceStatus,
        reason: str | None = None,
        account_id: UUID | None = None,
    ) -> None:
        now = utc_now()
        values = {"status": status, "failure_reason": reason, "updated_at": now}
        if status is InvoiceStatus.PAID:
            values.update(paid_at=now, paid_by_account_id=account_id)
        changed = session.execute(
            update(Invoice)
            .where(Invoice.id == invoice.id, Invoice.status == InvoiceStatus.CREATED)
            .values(**values)
        ).rowcount
        if changed != 1:
            raise BankError(409, "INVOICE_FINAL", "Счёт уже завершён.")
        event_id = uuid4()
        event_type = f"invoice.{status.value.lower()}"
        body = {
            "event_id": str(event_id),
            "type": event_type,
            "created_at": now.isoformat(),
            "data": {
                "invoice_id": str(invoice.id),
                "merchant_reference": str(invoice.merchant_reference),
                "amount_minor": invoice.amount_minor,
                "currency": invoice.currency,
                "failure_reason": reason,
            },
        }
        session.add(
            BankEvent(
                id=event_id,
                invoice_id=invoice.id,
                event_type=event_type,
                raw_body=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
                created_at=now,
                next_attempt_at=now,
            )
        )
        if status in (InvoiceStatus.PAID, InvoiceStatus.FAILED):
            session.add(
                BankTransaction(
                    invoice_id=invoice.id,
                    account_id=account_id,
                    amount_minor=invoice.amount_minor,
                    status=status.value,
                    failure_reason=reason,
                )
            )
        session.flush()

    def _expire(self, session: Session, invoice: Invoice) -> None:
        if invoice.status is InvoiceStatus.CREATED and invoice.expires_at <= utc_now():
            self._finalize(session, invoice, InvoiceStatus.EXPIRED, "expired")

    def create_invoice(self, payload: InvoiceCreate) -> dict:
        def operation(session: Session) -> dict:
            invoice = session.scalar(
                select(Invoice)
                .where(Invoice.merchant_reference == payload.merchant_reference)
                .with_for_update()
            )
            if invoice is not None:
                if any(
                    getattr(invoice, key) != value for key, value in payload.model_dump().items()
                ):
                    raise BankError(
                        409, "IDEMPOTENCY_CONFLICT", "Параметры повторного запроса отличаются."
                    )
                self._expire(session, invoice)
                return self.snapshot(session, invoice)
            invoice = Invoice(
                **payload.model_dump(),
                token=secrets.token_urlsafe(24),
                merchant_name=self.settings.merchant_name,
                expires_at=utc_now() + timedelta(seconds=payload.ttl_seconds),
            )
            session.add(invoice)
            session.flush()
            return self.snapshot(session, invoice)

        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            # A concurrent merchant_reference insertion won; compare the committed invoice.
            return run_write(self.factory, operation)

    def get_invoice(self, identifier: UUID | str, *, accounts: bool = False) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, identifier)
            self._expire(session, invoice)
            result = self.snapshot(session, invoice)
            if accounts:
                result["accounts"] = [
                    {
                        "public_id": str(account.id),
                        "holder_name": account.holder_name,
                        "balance_minor": account.balance_minor,
                        "balance_minor_text": str(account.balance_minor),
                    }
                    for account in session.scalars(
                        select(BankAccount).order_by(BankAccount.holder_name)
                    )
                ]
            return result

        return run_write(self.factory, operation)

    def pay(self, token: str, account_id: UUID) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, token)
            self._expire(session, invoice)
            if invoice.status is not InvoiceStatus.CREATED:
                return self.snapshot(session, invoice)
            if session.get(BankAccount, account_id) is None:
                raise BankError(404, "ACCOUNT_NOT_FOUND", "Демо-счёт не найден.")
            debited = session.execute(
                update(BankAccount)
                .where(
                    BankAccount.id == account_id,
                    BankAccount.balance_minor >= invoice.amount_minor,
                )
                .values(balance_minor=BankAccount.balance_minor - invoice.amount_minor)
            ).rowcount
            self._finalize(
                session,
                invoice,
                InvoiceStatus.PAID if debited else InvoiceStatus.FAILED,
                None if debited else "insufficient_funds",
                account_id,
            )
            result = self.snapshot(session, invoice)
            result["_new_payment"] = True
            return result

        result = run_write(self.factory, operation)
        if result.pop("_new_payment", False):
            return result
        if result["status"] == "EXPIRED":
            raise BankError(410, "INVOICE_EXPIRED", "Срок действия счёта истёк.")
        raise BankError(409, "INVOICE_FINAL", "Счёт уже завершён.")

    def cancel(self, identifier: UUID | str) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, identifier)
            self._expire(session, invoice)
            if invoice.status is InvoiceStatus.CREATED:
                self._finalize(session, invoice, InvoiceStatus.CANCELLED, "cancelled")
            return self.snapshot(session, invoice)

        result = run_write(self.factory, operation)
        if result["status"] == "PAID":
            raise BankError(409, "ALREADY_PAID", "Счёт уже оплачен.")
        return result

    def decline(self, token: str) -> dict:
        def operation(session: Session) -> dict:
            invoice = self._find(session, token)
            self._expire(session, invoice)
            if invoice.status is InvoiceStatus.CREATED:
                self._finalize(session, invoice, InvoiceStatus.FAILED, "bank_declined")
            return self.snapshot(session, invoice)

        return run_write(self.factory, operation)

    def sweep_expired(self) -> int:
        def operation(session: Session) -> int:
            invoices = session.scalars(
                select(Invoice)
                .where(
                    Invoice.status == InvoiceStatus.CREATED,
                    Invoice.expires_at <= utc_now(),
                )
                .order_by(Invoice.expires_at)
                .limit(100)
                .with_for_update()
            ).all()
            for invoice in invoices:
                self._finalize(session, invoice, InvoiceStatus.EXPIRED, "expired")
            return len(invoices)

        return run_write(self.factory, operation)
