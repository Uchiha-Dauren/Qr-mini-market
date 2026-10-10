"""Administrative reporting routes; authorization is mandatory in all environments."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from app.services.auth import require_admin
from app.services.reports import low_stock_report, payments_review_report, sales_report

router = APIRouter(
    prefix="/api/v1/reports", tags=["reports"], dependencies=[Depends(require_admin)]
)


@router.get("/sales")
def sales(
    request: Request,
    response: Response,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return sales_report(
        request.app.state.session_factory, request.app.state.settings, date_from, date_to
    )


@router.get("/low-stock")
def low_stock(
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return low_stock_report(request.app.state.session_factory, limit, offset)


@router.get("/payments-needing-review")
def payments_needing_review(
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return payments_review_report(request.app.state.session_factory, limit, offset)
