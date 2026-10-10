"""Exercise catalog and order behavior against the migrated database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.barcodes import generate_internal_ean13
from app.core.enums import OrderStatus, PaymentStatus, ProductUnit, StockReason
from app.core.errors import AppError, install_error_handlers
from app.core.money import MAX_SAFE_MINOR
from app.db.session import create_db_engine, create_session_factory
from app.models import Order, Payment, Product, StockMovement
from app.models.catalog import MAX_QUANTITY
from app.routers.catalog import router as catalog_router
from app.routers.orders import router as orders_router
from app.schemas.catalog import (
    CategoryCreate,
    CategoryPatch,
    ProductCreate,
    ProductPatch,
    StockAdjustment,
)
from app.schemas.orders import ItemAdd, ItemPatch, OrderCreate
from app.seed import CATEGORIES, PRODUCTS, seed_catalog
from app.services.auth import require_admin, require_cashier
from app.services.catalog import CatalogService
from app.services.orders import OrderService


@pytest.fixture
def factory(tmp_path: Path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'services.db'}")
    with engine.begin() as connection:
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def market(factory):
    catalog = CatalogService(factory)
    orders = OrderService(factory)
    root = catalog.create_category(CategoryCreate(name="Еда", slug="food"))
    leaf = catalog.create_category(
        CategoryCreate(name="Молочное", slug="milk", parent_id=root["public_id"])
    )
    piece = catalog.create_product(
        ProductCreate(
            name="МОЛОКО",
            barcode=generate_internal_ean13(1),
            category_id=leaf["public_id"],
            unit=ProductUnit.PIECE,
            price_minor=125000,
            stock_quantity=20,
        )
    )
    weight = catalog.create_product(
        ProductCreate(
            name="Яблоки 100%",
            barcode=generate_internal_ean13(2),
            category_id=root["public_id"],
            unit=ProductUnit.KG,
            price_minor=1,
            stock_quantity=10000,
        )
    )
    return SimpleNamespace(
        factory=factory,
        catalog=catalog,
        orders=orders,
        root=root,
        leaf=leaf,
        piece=piece,
        weight=weight,
    )


def assert_error(code, operation):
    with pytest.raises(AppError) as caught:
        operation()
    assert caught.value.code == code


def test_catalog_search_descendants_pagination_and_safe_public_projection(market):
    service = market.catalog
    assert service.list_products(q="мОлОкО")["total"] == 1
    assert service.list_products(q="%")["items"][0]["name"] == "Яблоки 100%"
    assert service.list_products(q="_")["total"] == 0
    assert service.list_products(category_id=market.root["public_id"])["total"] == 1
    assert (
        service.list_products(category_id=market.root["public_id"], include_subcategories=True)[
            "total"
        ]
        == 2
    )
    page = service.list_products(limit=1, offset=1, public=True)
    assert page["total"] == 2 and len(page["items"]) == 1
    assert (
        not {
            "id",
            "stock_quantity",
            "reserved_quantity",
            "min_stock_quantity",
            "available_quantity",
        }
        & page["items"][0].keys()
    )
    assert service.list_categories(limit=1, offset=1)["total"] == 2
    assert service.get_by_barcode(market.piece["barcode"])["public_id"] == market.piece["public_id"]
    assert service.get_product(market.piece["public_id"])["unit"] is ProductUnit.PIECE
    assert service.list_products(barcode=market.piece["barcode"])["total"] == 1


def test_catalog_soft_delete_parent_activity_and_uniqueness(market):
    service = market.catalog
    assert_error(
        "CATALOG_CONFLICT",
        lambda: service.create_category(CategoryCreate(name="Дубль", slug="food")),
    )
    assert_error(
        "CATALOG_CONFLICT",
        lambda: service.create_product(
            ProductCreate(
                name="Дубль",
                barcode=market.piece["barcode"],
                category_id=market.root["public_id"],
                unit=ProductUnit.PIECE,
                price_minor=1,
            )
        ),
    )
    result = service.delete_product(market.piece["public_id"])
    assert result["is_active"] is False
    assert service.list_products()["total"] == 1
    assert service.list_products(is_active=False)["total"] == 1
    assert service.list_products(is_active=None)["total"] == 2
    assert_error("PRODUCT_NOT_FOUND", lambda: service.get_by_barcode(market.piece["barcode"]))
    service.update_product(
        market.piece["public_id"], ProductPatch(is_active=True, name="  КеФиР  ")
    )
    assert service.list_products(q="кефир")["total"] == 1
    service.delete_category(market.root["public_id"])
    assert service.list_categories(public=True)["total"] == 0
    assert service.list_products(public=True)["total"] == 0
    with market.factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 2


def test_category_cycle_and_reparenting(market):
    service = market.catalog
    assert_error(
        "CATEGORY_CYCLE",
        lambda: service.update_category(
            market.root["public_id"], CategoryPatch(parent_id=market.leaf["public_id"])
        ),
    )
    assert_error(
        "CATEGORY_CYCLE",
        lambda: service.update_category(
            market.leaf["public_id"], CategoryPatch(parent_id=market.leaf["public_id"])
        ),
    )
    result = service.update_category(
        market.leaf["public_id"], CategoryPatch(parent_id=None, slug="dairy")
    )
    assert result["parent_id"] is None and result["slug"] == "dairy"
    assert_error(
        "CATEGORY_NOT_FOUND", lambda: service.update_category(uuid4(), CategoryPatch(name="Нет"))
    )
    assert_error("CATEGORY_NOT_FOUND", lambda: service.list_products(category_id=uuid4()))


def test_opposite_category_moves_cannot_form_a_cycle(market):
    service = market.catalog
    first = service.create_category(CategoryCreate(name="Первый", slug="first"))["public_id"]
    second = service.create_category(CategoryCreate(name="Второй", slug="second"))["public_id"]

    def move(pair):
        try:
            service.update_category(pair[0], CategoryPatch(parent_id=pair[1]))
            return "ok"
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(move, [(first, second), (second, first)]))
    assert sorted(outcomes) == ["CATEGORY_CYCLE", "ok"]


def test_stock_adjustments_are_atomic_guard_reserved_and_journaled(market):
    service = market.catalog
    with market.factory.begin() as session:
        product = session.scalar(
            select(Product).where(Product.public_id == market.piece["public_id"])
        )
        product.reserved_quantity = 18
    assert_error(
        "STOCK_CONFLICT",
        lambda: service.adjust_stock(market.piece["public_id"], StockAdjustment(delta=-3)),
    )
    changed = service.adjust_stock(market.piece["public_id"], StockAdjustment(delta=-2))
    assert changed["stock_quantity"] == 18 and changed["available_quantity"] == 0
    changed = service.adjust_stock(
        market.piece["public_id"], StockAdjustment(delta=5, reason=StockReason.RESTOCK)
    )
    assert changed["available_quantity"] == 5
    with market.factory() as session:
        deltas = list(session.scalars(select(StockMovement.delta).order_by(StockMovement.id)))
        assert deltas == [20, 10000, -2, 5]
    assert_error(
        "UNIT_IMMUTABLE",
        lambda: service.update_product(
            market.piece["public_id"], ProductPatch(unit=ProductUnit.KG)
        ),
    )
    assert_error(
        "PRODUCT_NOT_FOUND", lambda: service.adjust_stock(uuid4(), StockAdjustment(delta=1))
    )
    assert_error("PRODUCT_NOT_FOUND", lambda: service.get_by_barcode(generate_internal_ean13(99)))
    assert_error("PRODUCT_NOT_FOUND", lambda: service.get_product(uuid4()))


@pytest.mark.parametrize("stock,delta", [(MAX_QUANTITY, 1), (0, -1)])
def test_stock_adjustment_rejects_range_overflow_without_ledger_entry(market, stock, delta):
    with market.factory.begin() as session:
        product = session.scalar(
            select(Product).where(Product.public_id == market.piece["public_id"])
        )
        product.stock_quantity = stock
        movement_count = session.scalar(select(func.count()).select_from(StockMovement))
    assert_error(
        "STOCK_CONFLICT",
        lambda: market.catalog.adjust_stock(
            market.piece["public_id"], StockAdjustment(delta=delta)
        ),
    )
    assert market.catalog.get_product(market.piece["public_id"])["stock_quantity"] == stock
    with market.factory() as session:
        assert session.scalar(select(func.count()).select_from(StockMovement)) == movement_count


def test_repeated_scan_snapshots_weight_rounding_edit_and_delete(market):
    order = market.orders.create_order(OrderCreate())
    order_id = order["public_id"]
    order = market.orders.add_item(order_id, ItemAdd(barcode=market.piece["barcode"], quantity=1))
    snapshot = order["items"][0]
    market.catalog.update_product(
        market.piece["public_id"], ProductPatch(price_minor=990000, name="Новое имя")
    )
    order = market.orders.add_item(
        order_id, ItemAdd(product_id=market.piece["public_id"], quantity=2)
    )
    assert len(order["items"]) == 1 and order["items"][0]["quantity"] == 3
    assert order["items"][0]["unit_price_minor"] == 125000
    assert order["items"][0]["product_name"] == "МОЛОКО"
    order = market.orders.add_item(
        order_id, ItemAdd(product_id=market.weight["public_id"], quantity=500)
    )
    order = market.orders.add_item(
        order_id, ItemAdd(product_id=market.weight["public_id"], quantity=500)
    )
    assert order["total_minor"] == 375001
    assert order["total_minor"] == sum(item["line_total_minor"] for item in order["items"])
    order = market.orders.update_item(order_id, snapshot["public_id"], ItemPatch(quantity=2))
    assert order["total_minor"] == 250001
    order = market.orders.remove_item(order_id, snapshot["public_id"])
    assert len(order["items"]) == 1 and order["total_minor"] == 1
    assert market.orders.get_order(order_id)["items"] == order["items"]
    assert market.orders.list_orders(terminal_code="main", status=OrderStatus.OPEN)["total"] == 1
    assert_error("ACTIVE_ORDER_EXISTS", lambda: market.orders.create_order(OrderCreate()))
    assert_error("RECEIPT_NOT_READY", lambda: market.orders.receipt(order_id))
    assert_error("ITEM_NOT_FOUND", lambda: market.orders.remove_item(order_id, uuid4()))


@pytest.mark.parametrize(
    "status", [OrderStatus.PENDING_PAYMENT, OrderStatus.PAID, OrderStatus.CANCELLED]
)
def test_non_open_orders_cannot_be_mutated(market, status):
    order = market.orders.create_order(OrderCreate())
    order_id = order["public_id"]
    order = market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"]))
    with market.factory.begin() as session:
        session.scalar(select(Order).where(Order.public_id == order_id)).status = status
    assert_error(
        "ORDER_NOT_OPEN",
        lambda: market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"])),
    )
    assert_error(
        "ORDER_NOT_OPEN",
        lambda: market.orders.update_item(
            order_id, order["items"][0]["public_id"], ItemPatch(quantity=2)
        ),
    )
    assert_error(
        "ORDER_NOT_OPEN",
        lambda: market.orders.remove_item(order_id, order["items"][0]["public_id"]),
    )


def test_orders_reject_unknown_inactive_unavailable_and_unsafe_totals(market):
    order = market.orders.create_order(OrderCreate())
    order_id = order["public_id"]
    assert_error("ORDER_NOT_FOUND", lambda: market.orders.get_order(uuid4()))
    assert_error(
        "ORDER_NOT_FOUND",
        lambda: market.orders.add_item(uuid4(), ItemAdd(product_id=market.piece["public_id"])),
    )
    assert_error(
        "PRODUCT_NOT_FOUND", lambda: market.orders.add_item(order_id, ItemAdd(product_id=uuid4()))
    )
    assert_error(
        "INSUFFICIENT_STOCK",
        lambda: market.orders.add_item(
            order_id, ItemAdd(product_id=market.piece["public_id"], quantity=21)
        ),
    )
    market.catalog.delete_product(market.piece["public_id"])
    assert_error(
        "PRODUCT_INACTIVE",
        lambda: market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"])),
    )
    market.catalog.update_product(
        market.piece["public_id"], ProductPatch(is_active=True, price_minor=MAX_SAFE_MINOR)
    )
    assert_error(
        "AMOUNT_TOO_LARGE",
        lambda: market.orders.add_item(
            order_id, ItemAdd(product_id=market.piece["public_id"], quantity=2)
        ),
    )
    market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"]))
    assert_error(
        "AMOUNT_TOO_LARGE",
        lambda: market.orders.add_item(
            order_id, ItemAdd(product_id=market.weight["public_id"], quantity=1000)
        ),
    )
    assert market.orders.get_order(order_id)["total_minor"] == MAX_SAFE_MINOR
    assert len(market.orders.get_order(order_id)["items"]) == 1


def test_concurrent_repeated_scans_do_not_lose_quantities(market):
    order_id = market.orders.create_order(OrderCreate())["public_id"]

    def scan(_index):
        market.orders.add_item(order_id, ItemAdd(product_id=market.piece["public_id"]))

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(scan, range(8)))
    order = market.orders.get_order(order_id)
    assert order["items"][0]["quantity"] == 8
    assert order["total_minor"] == 1000000


def test_display_timer_final_failure_and_paid_visibility_are_server_owned(market):
    assert market.orders.display("main")["state"] == "idle"
    order_id = market.orders.create_order(OrderCreate())["public_id"]
    assert market.orders.display("main")["state"] == "cart"
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.status = OrderStatus.PENDING_PAYMENT
        payment = Payment(
            order_id=order.id,
            amount_minor=100,
            currency="KZT",
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
            pay_url="http://bank/pay/demo",
        )
        session.add(payment)
    display = market.orders.display("main")
    assert display["state"] == "awaiting_payment" and 0 < display["seconds_left"] <= 60
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.status = OrderStatus.OPEN
        payment = session.scalar(select(Payment).where(Payment.order_id == order.id))
        payment.status = PaymentStatus.EXPIRED
    assert market.orders.display("main")["failure_reason"] == "expired"
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.status = OrderStatus.PAID
        order.paid_at = datetime.now(UTC)
    assert market.orders.display("main")["state"] == "paid"
    assert market.orders.receipt(order_id)["payment_method"] == "QR"
    with market.factory.begin() as session:
        order = session.scalar(select(Order).where(Order.public_id == order_id))
        order.paid_at = datetime.now(UTC) - timedelta(seconds=16)
    assert market.orders.display("main")["state"] == "idle"
    assert market.orders.display("main")["state"] == "idle"


def test_seed_is_idempotent_and_does_not_reset_existing_stock(factory):
    assert seed_catalog(factory) == {
        "categories_created": len(CATEGORIES),
        "products_created": len(PRODUCTS),
    }
    with factory.begin() as session:
        product = session.scalar(
            select(Product).where(Product.barcode == generate_internal_ean13(1))
        )
        product.stock_quantity = 1
    assert seed_catalog(factory) == {"categories_created": 0, "products_created": 0}
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) >= 40
        assert (
            session.scalar(
                select(func.count()).select_from(Product).where(Product.is_active.is_(False))
            )
            == 1
        )
        assert (
            session.scalar(
                select(Product.stock_quantity).where(Product.barcode == generate_internal_ean13(1))
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(StockMovement)) == len(PRODUCTS) - 1


@pytest.mark.parametrize(
    "schema,data",
    [
        (CategoryCreate, {"name": " ", "slug": "blank"}),
        (CategoryCreate, {"name": "Еда", "slug": "../bad"}),
        (CategoryPatch, {}),
        (CategoryPatch, {"name": None}),
        (ProductPatch, {"price_minor": True}),
        (ProductPatch, {"price_minor": MAX_SAFE_MINOR + 1}),
        (ProductPatch, {"category_id": None}),
        (ProductPatch, {"barcode": "2000000000016"}),
        (ProductPatch, {}),
        (StockAdjustment, {"delta": 0}),
        (StockAdjustment, {"delta": 1, "reason": "SALE"}),
        (StockAdjustment, {"delta": -1, "reason": "RESTOCK"}),
        (ItemAdd, {}),
        (ItemAdd, {"barcode": "2000000000015", "product_id": str(uuid4())}),
        (ItemPatch, {"quantity": True}),
        (ItemPatch, {"quantity": 0}),
        (OrderCreate, {"terminal_code": "../bad"}),
    ],
)
def test_commands_reject_ambiguous_or_invalid_inputs(schema, data):
    with pytest.raises(ValidationError):
        schema.model_validate(data)


def test_public_routes_validate_ids_and_hide_stock_fields(market):
    app = FastAPI()
    app.state.session_factory = market.factory
    app.state.settings = SimpleNamespace(currency="KZT")
    app.include_router(catalog_router)
    app.include_router(orders_router)
    install_error_handlers(app)
    app.dependency_overrides[require_cashier] = lambda: SimpleNamespace(id=None)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=None)
    with TestClient(app) as client:
        products = client.get("/api/v1/public/products")
        assert products.status_code == 200
        assert "stock_quantity" not in products.json()["items"][0]
        assert client.get("/api/v1/public/categories").json()["total"] == 2
        assert client.get("/api/v1/products/1").status_code == 422
        assert client.get("/api/v1/products/by-barcode/2000000000016").status_code == 422
        assert client.get("/api/v1/public/products?barcode=2000000000016").status_code == 422
        assert client.get("/api/v1/products", params={"limit": 101}).status_code == 422
        created = client.post("/api/v1/orders", json={"terminal_code": "main"})
        assert created.status_code == 201
        order_id = created.json()["public_id"]
        added = client.post(
            f"/api/v1/orders/{order_id}/items",
            json={"barcode": market.piece["barcode"], "quantity": 2},
        )
        assert added.status_code == 200 and added.json()["total_minor"] == 250000
        display = client.get("/api/v1/public/terminals/main/display")
        assert display.status_code == 200
        assert display.headers["cache-control"] == "no-store"
        assert display.json()["state"] == "cart"
