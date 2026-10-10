"""Exercise checkout, bank settlement, notifications, recovery, and stock contention."""

import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from threading import Barrier
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.core.barcodes import generate_internal_ean13
from app.core.enums import StockReason
from app.models import PaymentEvent, Product, StockMovement
from mock_bank.models import Invoice


def build_cart(market, terminal: str = "demo") -> tuple[dict, list[dict]]:
    category = market.api("POST", "/categories", json={"name": "Еда", "slug": "food"})
    products = []
    for number, (name, unit, price, stock) in enumerate(
        [
            ("Хлеб", "PIECE", 40000, 10),
            ("Молоко", "PIECE", 70000, 10),
            ("Шоколад", "PIECE", 100000, 10),
            ("Яблоки", "KG", 80000, 5000),
        ],
        start=1,
    ):
        products.append(
            market.api(
                "POST",
                "/products",
                json={
                    "name": name,
                    "barcode": generate_internal_ean13(number),
                    "category_id": category["public_id"],
                    "unit": unit,
                    "price_minor": price,
                    "stock_quantity": stock,
                },
            )
        )
    order = market.api("POST", "/orders", json={"terminal_code": terminal})
    for product in products:
        order = market.api(
            "POST",
            f"/orders/{order['public_id']}/items",
            json={"barcode": product["barcode"], "quantity": 750 if product["unit"] == "KG" else 1},
        )
    assert order["total_minor"] == 270000
    assert len(order["items"]) == 4
    return order, products


def checkout(market, order: dict) -> tuple[dict, str, dict]:
    payment = market.api("POST", f"/orders/{order['public_id']}/checkout")
    assert payment["status"] == "PENDING"
    assert payment["amount_minor"] == order["total_minor"]
    token = urlsplit(payment["pay_url"]).path.rsplit("/", 1)[-1]
    response = market.bank.get(f"/api/pay/{token}")
    assert response.status_code == 200, response.text
    return payment, token, response.json()


def stock_snapshot(market, products: list[dict]) -> dict[str, tuple[int, int]]:
    with market.shop.app.state.session_factory() as session:
        rows = session.scalars(
            select(Product).where(Product.public_id.in_([UUID(p["public_id"]) for p in products]))
        )
        return {str(row.public_id): (row.stock_quantity, row.reserved_quantity) for row in rows}


def assert_no_private_fields(value: object) -> None:
    if isinstance(value, dict):
        assert not value.keys() & {
            "id",
            "provider_invoice_id",
            "password_hash",
            "cashier_id",
            "reserved_quantity",
            "min_stock_quantity",
            "raw_body",
        }
        for child in value.values():
            assert_no_private_fields(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_private_fields(child)


def test_three_piece_products_and_weight_are_paid_once_over_http(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    display = market.shop.get("/api/v1/public/terminals/demo/display")
    assert display.status_code == 200
    assert display.json()["state"] == "awaiting_payment"
    assert display.json()["seconds_left"] > 0
    assert_no_private_fields(display.json())

    qr = market.shop.get(f"/api/v1/payments/{payment['public_id']}/qr.png")
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.headers["cache-control"] == "no-store"
    assert qr.content.startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(BytesIO(qr.content)) as image:
        assert image.width >= 300 and image.height >= 300

    rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
    paid = market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]})
    assert paid.status_code == 200, paid.text
    result = market.api("GET", f"/orders/{order['public_id']}")
    assert result["status"] == "PAID"
    assert result["payment"]["status"] == "SUCCEEDED"
    assert market.shop.get("/api/v1/public/terminals/demo/display").json()["state"] == "paid"
    assert (
        market.shop.get(f"/api/v1/payments/{payment['public_id']}").json()["status"] == "SUCCEEDED"
    )
    assert market.shop.get(f"/api/v1/payments/{payment['public_id']}/qr.png").status_code in (
        409,
        410,
    )

    stock = stock_snapshot(market, products)
    for product in products:
        quantity = 750 if product["unit"] == "KG" else 1
        assert stock[product["public_id"]] == (product["stock_quantity"] - quantity, 0)
    receipt = market.api("GET", f"/orders/{order['public_id']}/receipt")
    assert receipt["total_minor"] == 270000
    assert receipt["payment_method"] == "QR"
    assert "не фискальный" in receipt["disclaimer"]

    assert len(market.bridge.requests) == 1
    _, raw, headers = market.bridge.requests[0]
    lowered_headers = {name.lower(): value for name, value in headers.items()}
    timestamp = lowered_headers["x-timestamp"]
    signature = hmac.new(
        market.settings.webhook_secret.get_secret_value().encode(),
        timestamp.encode() + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(lowered_headers["x-signature"], signature)
    duplicate = market.shop.post("/api/v1/webhooks/mock-bank", content=raw, headers=headers)
    assert duplicate.status_code == 200
    repeated_pay = market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]})
    assert repeated_pay.status_code == 409
    assert stock_snapshot(market, products) == stock
    with market.shop.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.reason == StockReason.SALE)
            )
            == 4
        )
    updated = market.bank.get(f"/api/pay/{token}").json()
    rich_after = next(a for a in updated["accounts"] if a["public_id"] == rich["public_id"])
    assert rich_after["balance_minor"] == rich["balance_minor"] - payment["amount_minor"]


def test_poor_account_releases_reserve_and_order_can_be_retried(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    poor = min(
        (account for account in invoice["accounts"] if account["balance_minor"] > 0),
        key=lambda account: account["balance_minor"],
    )
    response = market.bank.post(f"/api/pay/{token}", json={"account_id": poor["public_id"]})
    assert response.status_code == 200, response.text
    assert market.shop.get(f"/api/v1/payments/{payment['public_id']}").json()["status"] == "FAILED"
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == "OPEN"
    display = market.shop.get("/api/v1/public/terminals/demo/display").json()
    assert display["state"] == "payment_failed"
    for product in products:
        assert stock_snapshot(market, products)[product["public_id"]] == (
            product["stock_quantity"],
            0,
        )
    updated = market.bank.get(f"/api/pay/{token}").json()
    poor_after = next(a for a in updated["accounts"] if a["public_id"] == poor["public_id"])
    assert poor_after["balance_minor"] == poor["balance_minor"]
    retry = market.api("POST", f"/orders/{order['public_id']}/checkout")
    assert retry["status"] == "PENDING"
    assert retry["public_id"] != payment["public_id"]


def test_lost_webhook_is_recovered_by_refresh_without_double_sale(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    market.bridge.unavailable = True
    rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
    response = market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]})
    assert response.status_code == 200
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == "PENDING_PAYMENT"
    result = market.api("POST", f"/payments/{payment['public_id']}/refresh")
    assert result["status"] == "SUCCEEDED"
    stock = stock_snapshot(market, products)
    market.bridge.unavailable = False
    _, raw, headers = market.bridge.requests[0]
    assert (
        market.shop.post("/api/v1/webhooks/mock-bank", content=raw, headers=headers).status_code
        == 200
    )
    assert market.api("POST", f"/payments/{payment['public_id']}/refresh")["status"] == "SUCCEEDED"
    assert stock_snapshot(market, products) == stock
    with market.shop.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 1


def test_expiration_queries_bank_and_releases_reserve(market) -> None:
    order, products = build_cart(market)
    payment, token, invoice = checkout(market, order)
    with market.bank.app.state.session_factory.begin() as session:
        bank_invoice = session.scalar(select(Invoice).where(Invoice.token == token))
        bank_invoice.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    result = market.api("POST", f"/payments/{payment['public_id']}/refresh")
    assert result["status"] == "EXPIRED"
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == "OPEN"
    for product in products:
        assert stock_snapshot(market, products)[product["public_id"]] == (
            product["stock_quantity"],
            0,
        )
    rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
    assert (
        market.bank.post(f"/api/pay/{token}", json={"account_id": rich["public_id"]}).status_code
        == 410
    )


@pytest.mark.parametrize("cancel_order", [False, True])
def test_cashier_cancellation_reaches_bank_and_releases_reserve(market, cancel_order: bool) -> None:
    order, products = build_cart(market)
    payment, token, _ = checkout(market, order)
    path = (
        f"/orders/{order['public_id']}/cancel"
        if cancel_order
        else f"/payments/{payment['public_id']}/cancel"
    )
    market.api("POST", path)
    expected = "CANCELLED" if cancel_order else "OPEN"
    assert market.api("GET", f"/orders/{order['public_id']}")["status"] == expected
    assert market.bank.get(f"/api/pay/{token}").json()["status"] == "CANCELLED"
    assert (
        market.shop.get(f"/api/v1/payments/{payment['public_id']}").json()["status"] == "CANCELLED"
    )
    for product in products:
        assert stock_snapshot(market, products)[product["public_id"]] == (
            product["stock_quantity"],
            0,
        )


def test_last_product_can_be_reserved_by_only_one_terminal(market) -> None:
    category = market.api("POST", "/categories", json={"name": "Еда", "slug": "food"})
    product = market.api(
        "POST",
        "/products",
        json={
            "name": "Последний хлеб",
            "barcode": generate_internal_ean13(1),
            "category_id": category["public_id"],
            "unit": "PIECE",
            "price_minor": 30000,
            "stock_quantity": 1,
        },
    )
    orders = []
    for terminal in ("left", "right"):
        order = market.api("POST", "/orders", json={"terminal_code": terminal})
        market.api(
            "POST",
            f"/orders/{order['public_id']}/items",
            json={"product_id": product["public_id"], "quantity": 1},
        )
        orders.append(order)
    barrier = Barrier(2)

    def reserve(order: dict):
        barrier.wait(timeout=10)
        return market.shop.post(
            f"/api/v1/orders/{order['public_id']}/checkout", headers=market.headers
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(reserve, orders))
    assert sorted(response.status_code for response in responses) == [200, 409]
    failed = next(response for response in responses if response.status_code == 409)
    assert failed.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert stock_snapshot(market, [product])[product["public_id"]] == (1, 1)
    with market.bank.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Invoice)) == 1


def test_public_price_check_and_payment_status_do_not_grant_catalog_access(market) -> None:
    order, _ = build_cart(market)
    payment, _, _ = checkout(market, order)
    products = market.shop.get("/api/v1/public/products", params={"q": "МОЛОКО"})
    assert products.status_code == 200
    assert products.json()["total"] == 1
    product = products.json()["items"][0]
    assert "stock_quantity" not in product
    assert_no_private_fields(product)
    assert_no_private_fields(market.shop.get(f"/api/v1/payments/{payment['public_id']}").json())
    for method, path in [
        ("GET", "/products"),
        ("GET", f"/orders/{order['public_id']}/receipt"),
        ("POST", f"/payments/{payment['public_id']}/cancel"),
    ]:
        assert market.shop.request(method, "/api/v1" + path).status_code == 401
