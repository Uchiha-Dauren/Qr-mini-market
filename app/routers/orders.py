"""Order routes delegate all business decisions to the service layer."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.enums import OrderStatus
from app.models import User
from app.routers.catalog import Limit, Offset
from app.schemas.orders import (
    DisplayRead,
    ItemAdd,
    ItemPatch,
    OrderCreate,
    OrderPage,
    OrderRead,
    ReceiptRead,
    TerminalCode,
)
from app.services.auth import require_cashier
from app.services.orders import OrderService

router = APIRouter(prefix="/api/v1", tags=["orders"])


def service(request: Request) -> OrderService:
    return OrderService(request.app.state.session_factory, request.app.state.settings.currency)


@router.post("/orders", response_model=OrderRead, status_code=201)
def create_order(
    request: Request, command: OrderCreate, user: Annotated[User, Depends(require_cashier)]
) -> dict:
    return service(request).create_order(command, user.id)


@router.get("/orders", response_model=OrderPage, dependencies=[Depends(require_cashier)])
def orders(
    request: Request,
    terminal_code: TerminalCode | None = None,
    status: OrderStatus | None = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    return service(request).list_orders(
        terminal_code=terminal_code, status=status, limit=limit, offset=offset
    )


@router.get("/orders/{order_id}", response_model=OrderRead, dependencies=[Depends(require_cashier)])
def order(request: Request, order_id: UUID) -> dict:
    return service(request).get_order(order_id)


@router.post(
    "/orders/{order_id}/items", response_model=OrderRead, dependencies=[Depends(require_cashier)]
)
def add_item(request: Request, order_id: UUID, command: ItemAdd) -> dict:
    return service(request).add_item(order_id, command)


@router.patch(
    "/orders/{order_id}/items/{item_id}",
    response_model=OrderRead,
    dependencies=[Depends(require_cashier)],
)
def update_item(request: Request, order_id: UUID, item_id: UUID, command: ItemPatch) -> dict:
    return service(request).update_item(order_id, item_id, command)


@router.delete(
    "/orders/{order_id}/items/{item_id}",
    response_model=OrderRead,
    dependencies=[Depends(require_cashier)],
)
def remove_item(request: Request, order_id: UUID, item_id: UUID) -> dict:
    return service(request).remove_item(order_id, item_id)


@router.get(
    "/orders/{order_id}/receipt",
    response_model=ReceiptRead,
    dependencies=[Depends(require_cashier)],
)
def receipt(request: Request, order_id: UUID) -> dict:
    return service(request).receipt(order_id)


@router.get("/public/terminals/{terminal_code}/display", response_model=DisplayRead)
def display(request: Request, response: Response, terminal_code: TerminalCode) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return service(request).display(terminal_code)
