"""Reservation, external invoice creation, and atomic final payment transitions."""

import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import OrderStatus, PaymentStatus, StockReason
from app.core.errors import AppError
from app.core.money import MAX_SAFE_MINOR, calculate_line_total
from app.db.transactions import run_write
from app.models import Category, Order, OrderItem, Payment, PaymentEvent, Product, StockMovement
from app.providers.base import BankStatus, InvoiceSnapshot, PaymentProvider, ProviderUnavailable
from app.schemas.payments import BankEvent, EventData, PaymentRead

logger = logging.getLogger(__name__)
EVENT_STATUSES = {
    "invoice.paid": PaymentStatus.SUCCEEDED,
    "invoice.failed": PaymentStatus.FAILED,
    "invoice.expired": PaymentStatus.EXPIRED,
    "invoice.cancelled": PaymentStatus.CANCELLED,
}


class PaymentService:
    def __init__(
        self, factory: sessionmaker[Session], provider: PaymentProvider, settings: Settings
    ) -> None:
        self.factory, self.provider, self.settings = factory, provider, settings

    @staticmethod
    def _payment(session: Session, public_id: UUID, *, lock: bool = False) -> Payment:
        query = select(Payment).where(Payment.public_id == public_id)
        if lock:
            query = query.with_for_update()
        payment = session.scalar(query)
        if payment is None:
            raise AppError(404, "PAYMENT_NOT_FOUND", "Платёж не найден.")
        return payment

    @staticmethod
    def _dto(session: Session, payment: Payment) -> dict:
        order = session.get(Order, payment.order_id)
        remaining = 0
        if payment.status is PaymentStatus.PENDING and payment.expires_at is not None:
            remaining = max(0, int((payment.expires_at - datetime.now(UTC)).total_seconds()))
        return PaymentRead(
            public_id=payment.public_id,
            order_id=order.public_id,
            status=payment.status,
            amount_minor=payment.amount_minor,
            currency=payment.currency,
            pay_url=payment.pay_url,
            expires_at=payment.expires_at,
            seconds_left=remaining,
            failure_reason=payment.failure_reason,
            needs_review=payment.needs_review,
        ).model_dump(mode="json")

    def get_payment(self, public_id: UUID) -> dict:
        with self.factory() as session:
            return self._dto(session, self._payment(session, public_id))

    @staticmethod
    def _active_category(session: Session, category_id: int) -> bool:
        visited: set[int] = set()
        while category_id is not None:
            if category_id in visited:
                return False
            visited.add(category_id)
            category = session.scalar(
                select(Category).where(Category.id == category_id).with_for_update()
            )
            if category is None or not category.is_active:
                return False
            category_id = category.parent_id
        return True

    def checkout(self, order_uuid: UUID) -> dict:
        def prepare(session: Session) -> UUID:
            order = session.scalar(
                select(Order).where(Order.public_id == order_uuid).with_for_update()
            )
            if order is None:
                raise AppError(404, "ORDER_NOT_FOUND", "Чек не найден.")
            pending = session.scalar(
                select(Payment).where(
                    Payment.order_id == order.id, Payment.status == PaymentStatus.PENDING
                )
            )
            if pending is not None:
                return pending.public_id
            changed = session.execute(
                update(Order)
                .where(Order.id == order.id, Order.status == OrderStatus.OPEN)
                .values(status=OrderStatus.PENDING_PAYMENT, updated_at=datetime.now(UTC))
            )
            if changed.rowcount != 1:
                raise AppError(409, "ORDER_NOT_OPEN", "Чек нельзя отправить на оплату.")
            items = list(
                session.scalars(
                    select(OrderItem)
                    .where(OrderItem.order_id == order.id)
                    .order_by(OrderItem.product_id)
                )
            )
            if not items:
                raise AppError(409, "EMPTY_ORDER", "Добавьте товары в чек.")
            total = 0
            missing = []
            for item in items:
                item.line_total_minor = calculate_line_total(
                    item.unit, item.unit_price_minor, item.quantity
                )
                total += item.line_total_minor
                product = session.get(Product, item.product_id)
                if product is None or not self._active_category(session, product.category_id):
                    missing.append({"product_id": str(product.public_id) if product else None})
                    continue
                reserved = session.execute(
                    update(Product)
                    .where(
                        Product.id == item.product_id,
                        Product.category_id == product.category_id,
                        Product.is_active.is_(True),
                        Product.unit == item.unit,
                        Product.stock_quantity - Product.reserved_quantity >= item.quantity,
                    )
                    .values(reserved_quantity=Product.reserved_quantity + item.quantity)
                )
                if reserved.rowcount != 1:
                    missing.append({"product_id": str(product.public_id)})
            if missing:
                raise AppError(
                    409,
                    "INSUFFICIENT_STOCK",
                    "Товара недостаточно или он недоступен.",
                    {
                        "items": missing,
                    },
                )
            if not 0 < total <= MAX_SAFE_MINOR:
                raise AppError(
                    422, "INVALID_PAYMENT_AMOUNT", "Сумма оплаты вне допустимого диапазона."
                )
            order.total_minor = total
            payment = Payment(
                order_id=order.id,
                provider="mock_bank",
                amount_minor=total,
                currency=order.currency,
                status=PaymentStatus.PENDING,
                expires_at=datetime.now(UTC) + timedelta(seconds=self.settings.payment_ttl_seconds),
            )
            session.add(payment)
            session.flush()
            return payment.public_id

        public_id = run_write(self.factory, prepare)
        self._ensure_invoice(public_id)
        return self.get_payment(public_id)

    @staticmethod
    def _mark_review(payment: Payment, reason: str) -> None:
        payment.needs_review = True
        payment.review_reason = reason
        logger.warning("Payment requires review: %s (%s)", payment.public_id, reason)

    def _provider_error(
        self,
        public_id: UUID,
        failure: ProviderUnavailable,
        *,
        creating: bool,
        attempt: int | None = None,
    ) -> None:
        logger.warning("Payment provider request failed: %s", public_id)
        if creating and attempt == 1 and failure.definitely_not_created:

            def compensate(session: Session) -> None:
                payment = self._payment(session, public_id, lock=True)
                if (
                    payment.status is not PaymentStatus.PENDING
                    or payment.provider_invoice_id
                    or payment.creation_attempts != attempt
                ):
                    return
                event_id = str(uuid5(NAMESPACE_URL, f"provider-unavailable:{public_id}"))
                existing = session.scalar(
                    select(PaymentEvent.id).where(
                        PaymentEvent.provider == "mock_bank",
                        PaymentEvent.provider_event_id == event_id,
                    )
                )
                if existing is None:
                    session.add(
                        PaymentEvent(
                            payment_id=payment.id,
                            provider="mock_bank",
                            provider_event_id=event_id,
                            event_type="provider.unavailable",
                            raw_body="{}",
                            signature_valid=False,
                            outcome="applied",
                        )
                    )
                    self._finalize(session, payment, PaymentStatus.FAILED, "provider_unavailable")

            run_write(self.factory, compensate)
        raise AppError(
            503,
            "PROVIDER_UNAVAILABLE",
            "Банк недоступен. Проверьте оплату повторно.",
            {
                "payment_id": str(public_id),
            },
        ) from None

    def _ensure_invoice(self, public_id: UUID) -> None:
        def claim(session: Session):
            payment = self._payment(session, public_id, lock=True)
            if (
                payment.provider_invoice_id is not None
                or payment.status is not PaymentStatus.PENDING
            ):
                return
            now = datetime.now(UTC)
            if (
                payment.creation_started_at is not None
                and payment.creation_started_at > now - timedelta(seconds=30)
            ):
                return
            payment.creation_started_at = now
            payment.creation_attempts += 1
            order = session.get(Order, payment.order_id)
            parameters = {
                "amount_minor": payment.amount_minor,
                "currency": payment.currency,
                "merchant_reference": payment.public_id,
                "description": f"Чек {order.number}",
                "ttl_seconds": self.settings.payment_ttl_seconds,
            }
            return parameters, payment.creation_attempts

        claimed = run_write(self.factory, claim)
        if claimed is None:
            return
        parameters, attempt = claimed
        try:
            try:
                invoice = self.provider.create_invoice(**parameters)
            except ProviderUnavailable as exc:
                self._provider_error(public_id, exc, creating=True, attempt=attempt)
                return
            self._accept_snapshot(public_id, invoice)
        finally:

            def release(session: Session) -> None:
                session.execute(
                    update(Payment)
                    .where(
                        Payment.public_id == public_id,
                        Payment.creation_attempts == attempt,
                    )
                    .values(creation_started_at=None)
                )

            run_write(self.factory, release)

    def _accept_snapshot(self, public_id: UUID, invoice: InvoiceSnapshot) -> None:
        def accept(session: Session) -> str:
            payment = self._payment(session, public_id, lock=True)
            if (
                invoice.merchant_reference != payment.public_id
                or invoice.amount_minor != payment.amount_minor
                or invoice.currency != payment.currency
                or payment.provider_invoice_id not in (None, str(invoice.invoice_id))
            ):
                self._mark_review(payment, "provider_snapshot_mismatch")
                return "mismatch"
            other_owner = session.scalar(
                select(Payment.id).where(
                    Payment.provider_invoice_id == str(invoice.invoice_id),
                    Payment.id != payment.id,
                )
            )
            if other_owner is not None:
                self._mark_review(payment, "provider_invoice_collision")
                return "mismatch"
            payment.provider_invoice_id = str(invoice.invoice_id)
            payment.pay_url = str(invoice.pay_url)
            payment.expires_at = invoice.expires_at
            session.flush()
            waiting = list(
                session.scalars(
                    select(PaymentEvent)
                    .where(
                        PaymentEvent.payment_id == payment.id,
                        PaymentEvent.outcome == "awaiting_invoice",
                    )
                    .order_by(PaymentEvent.id)
                )
            )
            for stored in waiting:
                self._apply_event(
                    session, BankEvent.model_validate_json(stored.raw_body), stored.raw_body
                )
            if invoice.status is not BankStatus.CREATED:
                event = BankEvent(
                    event_id=invoice.event_id,
                    type=f"invoice.{invoice.status.value.lower()}",
                    created_at=invoice.paid_at or datetime.now(UTC),
                    data=EventData(
                        invoice_id=invoice.invoice_id,
                        merchant_reference=invoice.merchant_reference,
                        amount_minor=invoice.amount_minor,
                        currency=invoice.currency,
                        failure_reason=invoice.failure_reason,
                    ),
                )
                return self._apply_event(session, event, event.model_dump_json())
            return "accepted"

        outcome = self._write_event(accept)
        if outcome == "mismatch":
            raise AppError(422, "PAYMENT_MISMATCH", "Данные банка не совпадают. Нужна проверка.")

    def _finalize(
        self,
        session: Session,
        payment: Payment,
        status: PaymentStatus,
        failure_reason: str | None,
        paid_at: datetime | None = None,
    ) -> None:
        """The only method that changes a pending payment and its reserved inventory."""
        order = session.scalar(select(Order).where(Order.id == payment.order_id).with_for_update())
        if order.status is not OrderStatus.PENDING_PAYMENT:
            raise AppError(409, "PAYMENT_STATE_CONFLICT", "Состояние оплаты требует проверки.")
        now = datetime.now(UTC)
        succeeded = status is PaymentStatus.SUCCEEDED
        changed = session.execute(
            update(Payment)
            .where(Payment.id == payment.id, Payment.status == PaymentStatus.PENDING)
            .values(
                status=status,
                paid_at=(paid_at or now) if succeeded else None,
                failure_reason=failure_reason,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            raise AppError(409, "PAYMENT_STATE_CONFLICT", "Состояние оплаты изменилось.")
        changed = session.execute(
            update(Order)
            .where(Order.id == order.id, Order.status == OrderStatus.PENDING_PAYMENT)
            .values(
                status=OrderStatus.PAID if succeeded else OrderStatus.OPEN,
                paid_at=(paid_at or now) if succeeded else None,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            raise AppError(409, "PAYMENT_STATE_CONFLICT", "Состояние чека изменилось.")
        for item in session.scalars(select(OrderItem).where(OrderItem.order_id == order.id)):
            values = {"reserved_quantity": Product.reserved_quantity - item.quantity}
            if succeeded:
                values["stock_quantity"] = Product.stock_quantity - item.quantity
            changed = session.execute(
                update(Product)
                .where(
                    Product.id == item.product_id,
                    Product.reserved_quantity >= item.quantity,
                    Product.stock_quantity >= item.quantity,
                )
                .values(**values)
            )
            if changed.rowcount != 1:
                raise AppError(409, "RESERVATION_CONFLICT", "Резерв товара требует проверки.")
            if succeeded:
                session.add(
                    StockMovement(
                        product_id=item.product_id,
                        delta=-item.quantity,
                        reason=StockReason.SALE,
                        order_id=order.id,
                    )
                )
        logger.info("Payment transition: %s -> %s", payment.public_id, status.value)

    def _apply_event(self, session: Session, event: BankEvent, raw: str) -> str:
        stored = session.scalar(
            select(PaymentEvent)
            .where(
                PaymentEvent.provider == "mock_bank",
                PaymentEvent.provider_event_id == str(event.event_id),
            )
            .with_for_update()
        )
        if stored is not None and stored.outcome != "awaiting_invoice":
            return "duplicate"
        by_invoice = session.scalar(
            select(Payment)
            .where(Payment.provider_invoice_id == str(event.data.invoice_id))
            .with_for_update()
        )
        payment = by_invoice or session.scalar(
            select(Payment)
            .where(Payment.public_id == event.data.merchant_reference)
            .with_for_update()
        )
        if stored is None:
            stored = PaymentEvent(
                provider="mock_bank",
                provider_event_id=str(event.event_id),
                event_type=event.type,
                raw_body=raw,
                signature_valid=True,
                outcome="received",
                payment_id=payment.id if payment is not None else None,
            )
            session.add(stored)
            session.flush()
        if payment is None:
            stored.outcome = "unknown_payment"
            return stored.outcome
        if (
            event.data.merchant_reference != payment.public_id
            or event.data.amount_minor != payment.amount_minor
            or event.data.currency != payment.currency
            or payment.provider_invoice_id not in (None, str(event.data.invoice_id))
        ):
            self._mark_review(payment, "event_data_mismatch")
            stored.outcome = "mismatch"
            return stored.outcome
        if payment.provider_invoice_id is None:
            stored.outcome = "awaiting_invoice"
            return stored.outcome
        status = EVENT_STATUSES[event.type]
        if payment.status is not PaymentStatus.PENDING:
            if status is PaymentStatus.SUCCEEDED and payment.status is not PaymentStatus.SUCCEEDED:
                self._mark_review(payment, "late_success")
                stored.outcome = "late_success"
            else:
                stored.outcome = "already_final"
            return stored.outcome
        try:
            with session.begin_nested():
                self._finalize(
                    session,
                    payment,
                    status,
                    event.data.failure_reason,
                    event.created_at if status is PaymentStatus.SUCCEEDED else None,
                )
        except AppError:
            self._mark_review(payment, "reservation_or_order_conflict")
            stored.outcome = "state_conflict"
        else:
            stored.outcome = "applied"
        return stored.outcome

    def _write_event(self, operation):
        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            # PostgreSQL may race on event uniqueness; retry in a new transaction
            # so the durable winner is seen and no stock mutation can run twice.
            return run_write(self.factory, operation)

    def process_webhook(self, raw_body: bytes, timestamp: str, signature: str) -> dict:
        if (
            len(raw_body) > 16384
            or len(timestamp) > 16
            or len(signature) != 64
            or not signature.isascii()
        ):
            raise AppError(401, "INVALID_SIGNATURE", "Неверная подпись уведомления.")
        try:
            issued_at = int(timestamp)
        except ValueError:
            raise AppError(401, "INVALID_SIGNATURE", "Неверная подпись уведомления.") from None
        expected = hmac.new(
            self.settings.webhook_secret.get_secret_value().encode(),
            timestamp.encode() + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if abs(time.time() - issued_at) > 300 or not hmac.compare_digest(expected, signature):
            logger.warning("Rejected invalid or expired bank notification signature")
            raise AppError(401, "INVALID_SIGNATURE", "Неверная подпись уведомления.")
        try:
            event = BankEvent.model_validate_json(raw_body)
            raw = raw_body.decode("utf-8")
        except (ValueError, ValidationError):
            raise AppError(422, "INVALID_WEBHOOK", "Некорректное уведомление банка.") from None
        outcome = self._write_event(lambda session: self._apply_event(session, event, raw))
        if outcome == "mismatch":
            raise AppError(422, "PAYMENT_MISMATCH", "Данные оплаты не совпадают. Нужна проверка.")
        return {"accepted": True, "outcome": outcome}

    def refresh(self, public_id: UUID) -> dict:
        self._ensure_invoice(public_id)
        with self.factory() as session:
            payment = self._payment(session, public_id)
            invoice_id = payment.provider_invoice_id
            if payment.status is not PaymentStatus.PENDING or invoice_id is None:
                return self._dto(session, payment)
        try:
            invoice = self.provider.get_invoice_status(UUID(invoice_id))
        except ProviderUnavailable as exc:
            self._provider_error(public_id, exc, creating=False)
            raise AssertionError("Unreachable") from None
        self._accept_snapshot(public_id, invoice)
        return self.get_payment(public_id)

    def cancel(self, public_id: UUID) -> dict:
        self._ensure_invoice(public_id)
        with self.factory() as session:
            payment = self._payment(session, public_id)
            if payment.status is PaymentStatus.SUCCEEDED:
                raise AppError(409, "ALREADY_PAID", "Чек уже оплачен.")
            if payment.status is not PaymentStatus.PENDING:
                return self._dto(session, payment)
            invoice_id = payment.provider_invoice_id
        if invoice_id is None:
            raise AppError(409, "INVOICE_NOT_READY", "Создание счёта ещё не завершено.")
        try:
            invoice = self.provider.cancel_invoice(UUID(invoice_id))
        except ProviderUnavailable as exc:
            self._provider_error(public_id, exc, creating=False)
            raise AssertionError("Unreachable") from None
        self._accept_snapshot(public_id, invoice)
        result = self.get_payment(public_id)
        if result["status"] == PaymentStatus.SUCCEEDED:
            raise AppError(409, "ALREADY_PAID", "Чек уже оплачен.")
        if result["status"] == PaymentStatus.PENDING:
            raise AppError(503, "CANCELLATION_UNCONFIRMED", "Банк ещё не подтвердил отмену.")
        return result

    def cancel_order(self, order_uuid: UUID) -> dict:
        with self.factory() as session:
            order = session.scalar(select(Order).where(Order.public_id == order_uuid))
            if order is None:
                raise AppError(404, "ORDER_NOT_FOUND", "Чек не найден.")
            pending = session.scalar(
                select(Payment).where(
                    Payment.order_id == order.id, Payment.status == PaymentStatus.PENDING
                )
            )
            payment_uuid = pending.public_id if pending else None
        if payment_uuid is not None:
            self.cancel(payment_uuid)

        def cancel_open(session: Session) -> None:
            order = session.scalar(
                select(Order).where(Order.public_id == order_uuid).with_for_update()
            )
            if order.status is OrderStatus.CANCELLED:
                return
            changed = session.execute(
                update(Order)
                .where(
                    Order.id == order.id,
                    Order.status == OrderStatus.OPEN,
                )
                .values(
                    status=OrderStatus.CANCELLED,
                    cancelled_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            if changed.rowcount != 1:
                code = (
                    "ALREADY_PAID" if order.status is OrderStatus.PAID else "ORDER_STATE_CONFLICT"
                )
                raise AppError(409, code, "Чек нельзя отменить в текущем состоянии.")

        run_write(self.factory, cancel_open)
        from app.services.orders import OrderService

        return OrderService(self.factory).get_order(order_uuid)

    def sweep(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.settings.payment_expiry_grace_seconds)
        with self.factory() as session:
            public_ids = list(
                session.scalars(
                    select(Payment.public_id)
                    .where(
                        Payment.status == PaymentStatus.PENDING,
                        (Payment.expires_at < cutoff) | Payment.provider_invoice_id.is_(None),
                    )
                    .order_by(Payment.id)
                    .limit(100)
                )
            )
        for public_id in public_ids:
            try:
                self.refresh(public_id)
            except AppError:
                logger.warning("Payment reconciliation deferred: %s", public_id)
        return len(public_ids)
