"""Thin payment endpoints; the signature covers the original notification bytes."""

import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.enums import PaymentStatus
from app.core.errors import AppError
from app.schemas.payments import PaymentRead
from app.services.auth import require_cashier
from app.services.payments import PaymentService
from app.services.qr_service import make_qr_png

router = APIRouter(prefix="/api/v1", tags=["payments"])


def get_payment_service(request: Request) -> PaymentService:
    return PaymentService(
        request.app.state.session_factory, request.app.state.provider, request.app.state.settings
    )


Service = Annotated[PaymentService, Depends(get_payment_service)]


@router.post(
    "/orders/{order_id}/checkout",
    response_model=PaymentRead,
    dependencies=[Depends(require_cashier)],
)
def checkout(order_id: UUID, service: Service) -> dict:
    return service.checkout(order_id)


@router.post("/orders/{order_id}/cancel", dependencies=[Depends(require_cashier)])
def cancel_order(order_id: UUID, service: Service) -> dict:
    return service.cancel_order(order_id)


@router.get("/payments/{payment_id}", response_model=PaymentRead)
def get_payment(payment_id: UUID, response: Response, service: Service) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return service.get_payment(payment_id)


@router.post(
    "/payments/{payment_id}/refresh",
    response_model=PaymentRead,
    dependencies=[Depends(require_cashier)],
)
def refresh(payment_id: UUID, service: Service) -> dict:
    return service.refresh(payment_id)


@router.post(
    "/payments/{payment_id}/cancel",
    response_model=PaymentRead,
    dependencies=[Depends(require_cashier)],
)
def cancel(payment_id: UUID, service: Service) -> dict:
    return service.cancel(payment_id)


@router.get("/payments/{payment_id}/qr.png")
def qr(payment_id: UUID, service: Service) -> Response:
    payment = service.get_payment(payment_id)
    if payment["status"] != PaymentStatus.PENDING:
        status = 410 if payment["status"] == PaymentStatus.EXPIRED else 409
        raise AppError(status, "PAYMENT_NOT_PENDING", "Этот QR-код больше нельзя использовать.")
    if payment["seconds_left"] <= 0:
        raise AppError(410, "QR_EXPIRED", "Срок QR-кода истёк. Проверьте статус оплаты.")
    if not payment["pay_url"]:
        raise AppError(409, "INVOICE_NOT_READY", "Счёт банка ещё не получен.")
    return Response(
        make_qr_png(payment["pay_url"]),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/webhooks/mock-bank")
async def webhook(request: Request, service: Service) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 16384:
            raise AppError(413, "WEBHOOK_TOO_LARGE", "Уведомление превышает допустимый размер.")
    return await asyncio.to_thread(
        service.process_webhook,
        bytes(body),
        request.headers.get("X-Timestamp", ""),
        request.headers.get("X-Signature", ""),
    )
