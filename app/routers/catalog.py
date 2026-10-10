"""Thin catalog endpoints; access checks run before service transactions."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.schemas.catalog import (
    Barcode,
    CategoryCreate,
    CategoryPage,
    CategoryPatch,
    CategoryRead,
    ProductCreate,
    ProductPage,
    ProductPatch,
    ProductRead,
    PublicProductPage,
    StockAdjustment,
)
from app.services.auth import require_admin, require_cashier
from app.services.catalog import CatalogService

router = APIRouter(prefix="/api/v1", tags=["catalog"])
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0, le=1_000_000)]
Search = Annotated[str | None, Query(max_length=200)]
BarcodeQuery = Annotated[Barcode | None, Query()]


def service(request: Request) -> CatalogService:
    return CatalogService(request.app.state.session_factory)


@router.get("/categories", response_model=CategoryPage, dependencies=[Depends(require_cashier)])
def categories(request: Request, limit: Limit = 50, offset: Offset = 0) -> dict:
    return service(request).list_categories(limit=limit, offset=offset)


@router.get("/public/categories", response_model=CategoryPage)
def public_categories(request: Request, limit: Limit = 50, offset: Offset = 0) -> dict:
    return service(request).list_categories(public=True, limit=limit, offset=offset)


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_category(request: Request, command: CategoryCreate) -> dict:
    return service(request).create_category(command)


@router.patch(
    "/categories/{category_id}", response_model=CategoryRead, dependencies=[Depends(require_admin)]
)
def update_category(request: Request, category_id: UUID, command: CategoryPatch) -> dict:
    return service(request).update_category(category_id, command)


@router.delete(
    "/categories/{category_id}", response_model=CategoryRead, dependencies=[Depends(require_admin)]
)
def delete_category(request: Request, category_id: UUID) -> dict:
    return service(request).delete_category(category_id)


@router.get("/products", response_model=ProductPage, dependencies=[Depends(require_cashier)])
def products(
    request: Request,
    q: Search = None,
    category_id: UUID | None = None,
    include_subcategories: bool = False,
    is_active: bool | None = None,
    barcode: BarcodeQuery = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    return service(request).list_products(
        q=q,
        category_id=category_id,
        include_subcategories=include_subcategories,
        is_active=is_active,
        barcode=barcode,
        limit=limit,
        offset=offset,
    )


@router.get("/public/products", response_model=PublicProductPage)
def public_products(
    request: Request,
    q: Search = None,
    category_id: UUID | None = None,
    include_subcategories: bool = False,
    barcode: BarcodeQuery = None,
    limit: Limit = 50,
    offset: Offset = 0,
) -> dict:
    return service(request).list_products(
        q=q,
        category_id=category_id,
        include_subcategories=include_subcategories,
        barcode=barcode,
        limit=limit,
        offset=offset,
        public=True,
    )


@router.post(
    "/products", response_model=ProductRead, status_code=201, dependencies=[Depends(require_admin)]
)
def create_product(request: Request, command: ProductCreate) -> dict:
    return service(request).create_product(command)


@router.get(
    "/products/by-barcode/{barcode}",
    response_model=ProductRead,
    dependencies=[Depends(require_cashier)],
)
def product_by_barcode(request: Request, barcode: Barcode) -> dict:
    return service(request).get_by_barcode(barcode)


@router.get(
    "/products/{product_id}", response_model=ProductRead, dependencies=[Depends(require_cashier)]
)
def product(request: Request, product_id: UUID) -> dict:
    return service(request).get_product(product_id)


@router.patch(
    "/products/{product_id}", response_model=ProductRead, dependencies=[Depends(require_admin)]
)
def update_product(request: Request, product_id: UUID, command: ProductPatch) -> dict:
    return service(request).update_product(product_id, command)


@router.delete(
    "/products/{product_id}", response_model=ProductRead, dependencies=[Depends(require_admin)]
)
def delete_product(request: Request, product_id: UUID) -> dict:
    return service(request).delete_product(product_id)


@router.post(
    "/products/{product_id}/stock-adjustments",
    response_model=ProductRead,
    dependencies=[Depends(require_admin)],
)
def adjust_stock(request: Request, product_id: UUID, command: StockAdjustment) -> dict:
    return service(request).adjust_stock(product_id, command)
