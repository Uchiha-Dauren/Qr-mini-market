"""Orders use price snapshots, serialized mutations, and server-calculated totals."""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.enums import OrderStatus, PaymentStatus
from app.core.errors import AppError
from app.core.money import MAX_SAFE_MINOR, calculate_line_total
from app.db.transactions import run_write
from app.models import Order, OrderItem, Payment, Product
from app.models.catalog import MAX_QUANTITY
from app.schemas.orders import ItemAdd, ItemPatch, OrderCreate
from app.services.catalog import product_available


def payment_summary(payment: Payment | None, order_uuid: UUID) -> dict[str, Any] | None:
    if payment is None:
        return None
    seconds_left = 0
    if payment.status is PaymentStatus.PENDING and payment.expires_at is not None:
        seconds_left = max(0, int((payment.expires_at - datetime.now(UTC)).total_seconds()))
    return {
        "public_id": payment.public_id,
        "order_id": order_uuid,
        "status": payment.status,
        "amount_minor": payment.amount_minor,
        "currency": payment.currency,
        "pay_url": payment.pay_url,
        "expires_at": payment.expires_at,
        "seconds_left": seconds_left,
        "failure_reason": payment.failure_reason,
        "needs_review": payment.needs_review,
    }


def order_dict(session: Session, order: Order) -> dict[str, Any]:
    rows = session.execute(
        select(OrderItem, Product.public_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.id)
    )
    payment = session.scalar(
        select(Payment).where(Payment.order_id == order.id).order_by(Payment.id.desc()).limit(1)
    )
    return {
        "public_id": order.public_id,
        "number": order.number,
        "terminal_code": order.terminal_code,
        "status": order.status,
        "total_minor": order.total_minor,
        "currency": order.currency,
        "created_at": order.created_at,
        "paid_at": order.paid_at,
        "cancelled_at": order.cancelled_at,
        "items": [
            {
                "public_id": item.public_id,
                "product_id": product_uuid,
                "product_name": item.product_name,
                "barcode": item.barcode,
                "unit": item.unit,
                "unit_price_minor": item.unit_price_minor,
                "quantity": item.quantity,
                "line_total_minor": item.line_total_minor,
            }
            for item, product_uuid in rows
        ],
        "payment": payment_summary(payment, order.public_id),
    }


class OrderService:
    def __init__(self, factory: sessionmaker[Session], currency: str = "KZT") -> None:
        self.factory = factory
        self.currency = currency

    @staticmethod
    def _order(session: Session, order_uuid: UUID, *, editable: bool = False) -> Order:
        if editable:
            result = session.execute(
                update(Order)
                .where(Order.public_id == order_uuid, Order.status == OrderStatus.OPEN)
                .values(updated_at=datetime.now(UTC))
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                existing = session.scalar(select(Order.id).where(Order.public_id == order_uuid))
                if existing is not None:
                    raise AppError(
                        409, "ORDER_NOT_OPEN", "Чек нельзя изменить в текущем состоянии."
                    )
        order = session.scalar(select(Order).where(Order.public_id == order_uuid))
        if order is None:
            raise AppError(404, "ORDER_NOT_FOUND", "Чек не найден.")
        return order

    @staticmethod
    def _item(session: Session, order: Order, item_uuid: UUID) -> OrderItem:
        item = session.scalar(
            select(OrderItem).where(
                OrderItem.order_id == order.id, OrderItem.public_id == item_uuid
            )
        )
        if item is None:
            raise AppError(404, "ITEM_NOT_FOUND", "Позиция чека не найдена.")
        return item

    @staticmethod
    def _check_quantity(session: Session, product: Product, quantity: int) -> None:
        if not product_available(session, product):
            raise AppError(409, "PRODUCT_INACTIVE", "Товар или его категория недоступны.")
        if quantity > MAX_QUANTITY:
            raise AppError(422, "QUANTITY_TOO_LARGE", "Количество превышает допустимый предел.")
        if quantity > product.stock_quantity - product.reserved_quantity:
            raise AppError(
                409,
                "INSUFFICIENT_STOCK",
                "Недостаточно доступного остатка.",
                {"product_id": str(product.public_id)},
            )

    @staticmethod
    def _line_total(item: OrderItem) -> int:
        total = calculate_line_total(item.unit, item.unit_price_minor, item.quantity)
        if total > MAX_SAFE_MINOR or item.unit_price_minor > MAX_SAFE_MINOR:
            raise AppError(422, "AMOUNT_TOO_LARGE", "Сумма позиции превышает допустимый предел.")
        return total

    @staticmethod
    def _recalculate(session: Session, order: Order) -> None:
        session.flush()
        amounts = session.scalars(
            select(OrderItem.line_total_minor).where(OrderItem.order_id == order.id)
        )
        # Python integers detect overflow before a database aggregate can overflow.
        total = sum(amounts)
        if total > MAX_SAFE_MINOR:
            raise AppError(422, "AMOUNT_TOO_LARGE", "Сумма чека превышает допустимый предел.")
        order.total_minor = total
        session.flush()

    def create_order(self, command: OrderCreate, cashier_id: int | None = None) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            active = session.scalar(
                select(Order).where(
                    Order.terminal_code == command.terminal_code,
                    Order.status.in_([OrderStatus.OPEN, OrderStatus.PENDING_PAYMENT]),
                )
            )
            if active is not None:
                raise AppError(
                    409,
                    "ACTIVE_ORDER_EXISTS",
                    "На терминале уже есть открытый чек.",
                    {"order_id": str(active.public_id)},
                )
            order_uuid = uuid4()
            order = Order(
                public_id=order_uuid,
                number=f"{datetime.now(UTC):%Y%m%d}-{order_uuid.hex}",
                terminal_code=command.terminal_code,
                currency=self.currency,
                status=OrderStatus.OPEN,
                total_minor=0,
                cashier_id=cashier_id,
            )
            session.add(order)
            session.flush()
            return order_dict(session, order)

        try:
            return run_write(self.factory, operation)
        except IntegrityError:
            raise AppError(
                409, "ACTIVE_ORDER_EXISTS", "На терминале уже есть открытый чек."
            ) from None

    def get_order(self, order_uuid: UUID) -> dict[str, Any]:
        with self.factory() as session:
            return order_dict(session, self._order(session, order_uuid))

    def list_orders(
        self,
        *,
        terminal_code: str | None = None,
        status: OrderStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        with self.factory() as session:
            query = select(Order)
            if terminal_code is not None:
                query = query.where(Order.terminal_code == terminal_code)
            if status is not None:
                query = query.where(Order.status == status)
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            orders = session.scalars(query.order_by(Order.id.desc()).limit(limit).offset(offset))
            return {
                "items": [order_dict(session, order) for order in orders],
                "total": total,
                "limit": limit,
                "offset": offset,
            }

    def add_item(self, order_uuid: UUID, command: ItemAdd) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            order = self._order(session, order_uuid, editable=True)
            query = (
                select(Product).where(Product.barcode == command.barcode)
                if command.barcode
                else select(Product).where(Product.public_id == command.product_id)
            )
            product = session.scalar(query)
            if product is None:
                raise AppError(404, "PRODUCT_NOT_FOUND", "Товар не найден.")
            item = session.scalar(
                select(OrderItem).where(
                    OrderItem.order_id == order.id, OrderItem.product_id == product.id
                )
            )
            quantity = command.quantity + (item.quantity if item else 0)
            self._check_quantity(session, product, quantity)
            if item is None:
                item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name=product.name,
                    barcode=product.barcode,
                    unit=product.unit,
                    unit_price_minor=product.price_minor,
                    quantity=quantity,
                )
                session.add(item)
            else:
                item.quantity = quantity
            item.line_total_minor = self._line_total(item)
            self._recalculate(session, order)
            return order_dict(session, order)

        return run_write(self.factory, operation)

    def update_item(self, order_uuid: UUID, item_uuid: UUID, command: ItemPatch) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            order = self._order(session, order_uuid, editable=True)
            item = self._item(session, order, item_uuid)
            product = session.get(Product, item.product_id)
            self._check_quantity(session, product, command.quantity)
            item.quantity = command.quantity
            item.line_total_minor = self._line_total(item)
            self._recalculate(session, order)
            return order_dict(session, order)

        return run_write(self.factory, operation)

    def remove_item(self, order_uuid: UUID, item_uuid: UUID) -> dict[str, Any]:
        def operation(session: Session) -> dict[str, Any]:
            order = self._order(session, order_uuid, editable=True)
            session.delete(self._item(session, order, item_uuid))
            self._recalculate(session, order)
            return order_dict(session, order)

        return run_write(self.factory, operation)

    def receipt(self, order_uuid: UUID) -> dict[str, Any]:
        result = self.get_order(order_uuid)
        if result["status"] is not OrderStatus.PAID:
            raise AppError(409, "RECEIPT_NOT_READY", "Чек доступен после успешной оплаты.")
        return {**result, "payment_method": "QR", "disclaimer": "Учебный проект, не фискальный чек"}

    def display(self, terminal_code: str) -> dict[str, Any]:
        with self.factory() as session:
            order = session.scalar(
                select(Order)
                .where(
                    Order.terminal_code == terminal_code,
                    Order.status.in_([OrderStatus.OPEN, OrderStatus.PENDING_PAYMENT]),
                )
                .order_by(Order.id.desc())
                .limit(1)
            )
            if order is None:
                order = session.scalar(
                    select(Order)
                    .where(
                        Order.terminal_code == terminal_code,
                        Order.status == OrderStatus.PAID,
                        Order.paid_at >= datetime.now(UTC) - timedelta(seconds=15),
                    )
                    .order_by(Order.paid_at.desc(), Order.id.desc())
                    .limit(1)
                )
            if order is None:
                return {
                    "state": "idle",
                    "order": None,
                    "payment": None,
                    "seconds_left": 0,
                    "failure_reason": None,
                }
            result = order_dict(session, order)
            payment = result["payment"]
            state = "cart"
            failure_reason = None
            if order.status is OrderStatus.PAID:
                state = "paid"
            elif order.status is OrderStatus.PENDING_PAYMENT:
                state = "awaiting_payment"
            elif payment and payment["status"] in {
                PaymentStatus.FAILED,
                PaymentStatus.EXPIRED,
                PaymentStatus.CANCELLED,
            }:
                state = "payment_failed"
                failure_reason = {
                    PaymentStatus.EXPIRED: "expired",
                    PaymentStatus.CANCELLED: "cancelled",
                }.get(payment["status"], "declined")
            return {
                "state": state,
                "order": result,
                "payment": payment,
                "seconds_left": payment["seconds_left"] if payment else 0,
                "failure_reason": failure_reason,
            }
