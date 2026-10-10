"""Payment invariants, ambiguous network outcomes, and signed event processing."""

import hashlib
import hmac
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from threading import Event
from uuid import UUID, uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.enums import OrderStatus, PaymentStatus, ProductUnit
from app.core.errors import AppError, install_error_handlers
from app.db.session import create_db_engine, create_session_factory
from app.models import Category, Order, OrderItem, Payment, PaymentEvent, Product, StockMovement
from app.providers.base import BankStatus, ProviderUnavailable
from app.providers.fake import FakeProvider
from app.providers.mock_bank import MockBankProvider
from app.routers.payments import router
from app.services.payments import PaymentService
from app.services.qr_service import make_qr_png

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for key in Settings.model_fields:
        monkeypatch.delenv(key.upper(), raising=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'payments.db'}",
        secret_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        bank_merchant_api_key=secrets.token_urlsafe(32),
    )
    engine = create_db_engine(settings.database_url)
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    factory = create_session_factory(engine)
    with factory.begin() as session:
        category = Category(name="Еда", slug="food")
        session.add(category)
        session.flush()
        product = Product(
            name="Молоко",
            barcode="2000000000015",
            category_id=category.id,
            unit=ProductUnit.PIECE,
            price_minor=100,
            stock_quantity=5,
        )
        session.add(product)
        order = Order(number="TEST-1", terminal_code="main")
        session.add(order)
        session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name=product.name,
                barcode=product.barcode,
                unit=product.unit,
                unit_price_minor=100,
                quantity=2,
                line_total_minor=200,
            )
        )
        order_uuid = order.public_id
    provider = FakeProvider()
    service = PaymentService(factory, provider, settings)
    yield service, factory, provider, settings, order_uuid
    engine.dispose()


def make_event(provider, payment, *, status=BankStatus.PAID, **changes):
    invoice = provider.finish(provider.references[UUID(payment["public_id"])], status)
    body = {
        "event_id": str(invoice.event_id),
        "type": f"invoice.{status.value.lower()}",
        "created_at": datetime.now(UTC).isoformat(),
        "data": {
            "invoice_id": str(invoice.invoice_id),
            "merchant_reference": str(invoice.merchant_reference),
            "amount_minor": invoice.amount_minor,
            "currency": invoice.currency,
            "failure_reason": invoice.failure_reason,
        },
    }
    body["data"].update(changes)
    return json.dumps(body).encode()


def deliver(service, settings, body, timestamp=None):
    timestamp = str(int(time.time())) if timestamp is None else timestamp
    signature = hmac.new(
        settings.webhook_secret.get_secret_value().encode(),
        timestamp.encode() + b"." + body,
        hashlib.sha256,
    ).hexdigest()
    return service.process_webhook(body, timestamp, signature)


def test_checkout_is_idempotent_and_success_commits_once(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    assert service.checkout(order_uuid)["public_id"] == payment["public_id"]
    assert provider.create_calls == 1
    body = make_event(provider, payment)
    assert deliver(service, settings, body)["outcome"] == "applied"
    assert deliver(service, settings, body)["outcome"] == "duplicate"
    assert service.refresh(UUID(payment["public_id"]))["status"] == "SUCCEEDED"
    with factory() as session:
        product = session.scalar(select(Product))
        assert (product.stock_quantity, product.reserved_quantity) == (3, 0)
        assert session.scalar(select(Order.status)) is OrderStatus.PAID
        assert session.scalar(select(func.count()).select_from(StockMovement)) == 1
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 1


@pytest.mark.parametrize("mode", ["signature", "past", "future", "malformed"])
def test_invalid_signed_input_changes_nothing(setup, mode):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    body = make_event(provider, payment)
    with pytest.raises(AppError) as error:
        if mode == "signature":
            service.process_webhook(body, str(int(time.time())), "0" * 64)
        elif mode == "malformed":
            deliver(service, settings, body, "not-a-timestamp")
        else:
            offset = -301 if mode == "past" else 301
            deliver(service, settings, body, str(int(time.time()) + offset))
    assert error.value.status_code == 401
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(PaymentEvent)) == 0
        assert session.scalar(select(Payment.status)) is PaymentStatus.PENDING
        assert session.scalar(select(Product.reserved_quantity)) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"amount_minor": 201},
        {"currency": "USD"},
        {"merchant_reference": str(uuid4())},
        {"invoice_id": str(uuid4())},
    ],
)
def test_wrong_signed_data_is_durable_review_without_transition(setup, change):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    body = make_event(provider, payment, **change)
    with pytest.raises(AppError) as error:
        deliver(service, settings, body)
    assert error.value.status_code == 422
    assert deliver(service, settings, body)["outcome"] == "duplicate"
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.status is PaymentStatus.PENDING and payment.needs_review
        assert session.scalar(select(Product.reserved_quantity)) == 2
        assert session.scalar(select(PaymentEvent.outcome)) == "mismatch"


def test_late_success_after_cancellation_does_not_sell_stock(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    assert service.cancel(UUID(payment["public_id"]))["status"] == "CANCELLED"
    body = json.loads(make_event(provider, payment))
    body["event_id"] = str(uuid4())
    body["type"] = "invoice.paid"
    assert deliver(service, settings, json.dumps(body).encode())["outcome"] == "late_success"
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.status is PaymentStatus.CANCELLED and payment.needs_review
        assert payment.review_reason == "late_success"
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN
        assert session.scalar(select(Product.stock_quantity)) == 5
        assert session.scalar(select(Product.reserved_quantity)) == 0


def test_connection_refusal_compensates_but_timeout_preserves_reservation(setup):
    service, factory, provider, settings, order_uuid = setup
    provider.create_error = ProviderUnavailable(definitely_not_created=True)
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.status_code == 503
    with factory() as session:
        assert session.scalar(select(Payment.status)) is PaymentStatus.FAILED
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN
        assert session.scalar(select(Product.reserved_quantity)) == 0
    provider.create_error = ProviderUnavailable()
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory() as session:
        pending_id = session.scalar(
            select(Payment.public_id).where(Payment.status == PaymentStatus.PENDING)
        )
        assert session.scalar(select(Order.status)) is OrderStatus.PENDING_PAYMENT
        assert session.scalar(select(Product.reserved_quantity)) == 2
    provider.create_error = None
    recovered = service.refresh(pending_id)
    assert recovered["public_id"] == str(pending_id)
    assert recovered["pay_url"]


def test_lost_creation_response_recovers_same_invoice(setup, monkeypatch):
    service, factory, provider, settings, order_uuid = setup
    original = provider.create_invoice

    def lose_response(**kwargs):
        original(**kwargs)
        raise ProviderUnavailable()

    monkeypatch.setattr(provider, "create_invoice", lose_response)
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory() as session:
        payment_id = session.scalar(select(Payment.public_id))
    assert len(provider.invoices) == 1
    monkeypatch.setattr(provider, "create_invoice", original)
    assert service.refresh(payment_id)["pay_url"]
    assert len(provider.invoices) == 1


def test_early_webhook_waits_for_invoice_binding(setup, monkeypatch):
    service, factory, provider, settings, order_uuid = setup
    original = provider.create_invoice

    def early_event(**kwargs):
        invoice = original(**kwargs)
        body = make_event(provider, {"public_id": str(invoice.merchant_reference)})
        assert deliver(service, settings, body)["outcome"] == "awaiting_invoice"
        return invoice

    monkeypatch.setattr(provider, "create_invoice", early_event)
    payment = service.checkout(order_uuid)
    assert payment["status"] == "SUCCEEDED"
    with factory() as session:
        assert session.scalar(select(PaymentEvent.outcome)) == "applied"
        assert session.scalar(select(Product.stock_quantity)) == 3


def test_multi_item_shortage_rolls_back_every_reservation(setup):
    service, factory, provider, settings, order_uuid = setup
    with factory.begin() as session:
        product = session.scalar(select(Product))
        second = Product(
            name="Сыр",
            barcode="2000000000022",
            category_id=product.category_id,
            unit=ProductUnit.PIECE,
            price_minor=100,
            stock_quantity=0,
        )
        session.add(second)
        session.flush()
        order = session.scalar(select(Order))
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=second.id,
                product_name=second.name,
                barcode=second.barcode,
                unit=second.unit,
                unit_price_minor=100,
                quantity=1,
                line_total_minor=100,
            )
        )
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "INSUFFICIENT_STOCK"
    with factory() as session:
        assert list(session.scalars(select(Product.reserved_quantity))) == [0, 0]
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN
        assert session.scalar(select(func.count()).select_from(Payment)) == 0
    assert provider.create_calls == 0


@pytest.mark.parametrize("operation", ["cancel", "refresh"])
def test_network_unavailable_during_existing_invoice_keeps_reserve(setup, monkeypatch, operation):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)

    def fail(_invoice_id):
        raise ProviderUnavailable(definitely_not_created=True)

    monkeypatch.setattr(
        provider, "cancel_invoice" if operation == "cancel" else "get_invoice_status", fail
    )
    with pytest.raises(AppError):
        getattr(service, operation)(UUID(payment["public_id"]))
    with factory() as session:
        assert session.scalar(select(Payment.status)) is PaymentStatus.PENDING
        assert session.scalar(select(Product.reserved_quantity)) == 2


def test_expiry_sweep_waits_for_grace_and_bank_confirmation(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    invoice_id = provider.references[UUID(payment["public_id"])]
    with factory.begin() as session:
        session.scalar(select(Payment)).expires_at = datetime.now(UTC) - timedelta(seconds=10)
    assert service.sweep() == 0
    with factory.begin() as session:
        session.scalar(select(Payment)).expires_at = datetime.now(UTC) - timedelta(seconds=60)
    assert service.sweep() == 1
    assert service.get_payment(UUID(payment["public_id"]))["status"] == "PENDING"
    provider.invoices[invoice_id] = provider.invoices[invoice_id].model_copy(
        update={
            "expires_at": datetime.now(UTC) - timedelta(seconds=60),
        }
    )
    with factory.begin() as session:
        session.scalar(select(Payment)).expires_at = datetime.now(UTC) - timedelta(seconds=60)
    assert service.sweep() == 1
    assert service.get_payment(UUID(payment["public_id"]))["status"] == "EXPIRED"


def test_qr_png_size_and_exact_payload(monkeypatch):
    import qrcode

    captured = []
    original = qrcode.QRCode.add_data

    def capture(self, data, *args, **kwargs):
        captured.append(data)
        return original(self, data, *args, **kwargs)

    monkeypatch.setattr(qrcode.QRCode, "add_data", capture)
    url = "http://bank.test/pay/random-token"
    png = make_qr_png(url)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert min(Image.open(BytesIO(png)).size) >= 300
    assert captured == [url]


@pytest.mark.parametrize("kind", ["connect", "timeout", "server", "invalid", "unauthorized"])
def test_http_adapter_classifies_failure_without_echoing_secrets(setup, kind):
    service, factory, provider, settings, order_uuid = setup

    def transport(request):
        if kind == "connect":
            raise httpx.ConnectError("sensitive-value")
        if kind == "timeout":
            raise httpx.ReadTimeout("sensitive-value")
        return httpx.Response(
            {"server": 503, "invalid": 200, "unauthorized": 401}[kind],
            json={"sensitive-value": "do-not-echo"},
        )

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        adapter = MockBankProvider(client, settings)
        with pytest.raises(ProviderUnavailable) as error:
            adapter.create_invoice(
                amount_minor=100,
                currency="KZT",
                merchant_reference=uuid4(),
                description="Чек",
                ttl_seconds=300,
            )
    assert error.value.definitely_not_created == (kind in ("connect", "unauthorized"))
    assert "sensitive" not in str(error.value)


def test_simultaneous_checkout_uses_one_creation_lease(setup, monkeypatch):
    service, factory, provider, settings, order_uuid = setup
    started, release = Event(), Event()
    original = provider.create_invoice

    def delayed(**kwargs):
        started.set()
        assert release.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(provider, "create_invoice", delayed)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(service.checkout, order_uuid)
        assert started.wait(timeout=5)
        try:
            second = service.checkout(order_uuid)
            assert second["status"] == "PENDING" and second["pay_url"] is None
            with pytest.raises(AppError) as error:
                service.cancel(UUID(second["public_id"]))
            assert error.value.code == "INVOICE_NOT_READY"
        finally:
            release.set()
        completed = first.result(timeout=5)
    assert completed["public_id"] == second["public_id"]
    assert completed["pay_url"] and provider.create_calls == 1
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.creation_attempts == 1 and payment.creation_started_at is None
        assert session.scalar(select(Product.reserved_quantity)) == 2


def test_connect_error_after_ambiguous_attempt_never_releases_reserve(setup):
    service, factory, provider, settings, order_uuid = setup
    provider.create_error = ProviderUnavailable()
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    provider.create_error = ProviderUnavailable(definitely_not_created=True)
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory() as session:
        payment = session.scalar(select(Payment))
        assert payment.status is PaymentStatus.PENDING
        assert payment.creation_attempts == 2
        assert session.scalar(select(Product.reserved_quantity)) == 2


def test_creation_lease_recovers_after_process_crash(setup):
    service, factory, provider, settings, order_uuid = setup
    provider.create_error = ProviderUnavailable()
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with factory.begin() as session:
        payment = session.scalar(select(Payment))
        payment.creation_started_at = datetime.now(UTC) - timedelta(seconds=31)
        payment_id = payment.public_id
    provider.create_error = None
    assert service.sweep() == 1
    assert service.get_payment(payment_id)["pay_url"]


def test_empty_inactive_and_zero_total_checkout_rollback(setup):
    service, factory, provider, settings, order_uuid = setup
    with factory.begin() as session:
        session.scalar(select(Category)).is_active = False
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "INSUFFICIENT_STOCK"
    with factory.begin() as session:
        session.scalar(select(Category)).is_active = True
        session.scalar(select(OrderItem)).unit_price_minor = 0
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "INVALID_PAYMENT_AMOUNT"
    with factory.begin() as session:
        session.delete(session.scalar(select(OrderItem)))
    with pytest.raises(AppError) as error:
        service.checkout(order_uuid)
    assert error.value.code == "EMPTY_ORDER"
    with factory() as session:
        assert session.scalar(select(Product.reserved_quantity)) == 0
        assert session.scalar(select(Order.status)) is OrderStatus.OPEN


def test_public_qr_route_signature_webhook_and_private_mutations(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    app = FastAPI()
    app.state.session_factory, app.state.provider, app.state.settings = factory, provider, settings
    install_error_handlers(app)
    app.include_router(router)
    path = f"/api/v1/payments/{payment['public_id']}"
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert "provider_invoice_id" not in response.text
        assert response.headers["cache-control"] == "no-store"
        image = client.get(path + "/qr.png")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.headers["cache-control"] == "no-store"
        assert min(Image.open(BytesIO(image.content)).size) >= 300
        assert client.post(path + "/cancel").status_code == 401
        assert client.post(path + "/refresh").status_code == 401
        raw = make_event(provider, payment)
        timestamp = str(int(time.time()))
        signature = hmac.new(
            settings.webhook_secret.get_secret_value().encode(),
            timestamp.encode() + b"." + raw,
            hashlib.sha256,
        ).hexdigest()
        result = client.post(
            "/api/v1/webhooks/mock-bank",
            content=raw,
            headers={"X-Timestamp": timestamp, "X-Signature": signature},
        )
        assert result.status_code == 200
        assert client.get(path + "/qr.png").status_code == 409
        assert client.post("/api/v1/webhooks/mock-bank", content=b"x" * 16385).status_code == 413


def test_cancel_order_and_already_paid_conflict(setup):
    service, factory, provider, settings, order_uuid = setup
    payment = service.checkout(order_uuid)
    cancelled = service.cancel_order(order_uuid)
    assert cancelled["status"] == "CANCELLED"
    assert service.cancel_order(order_uuid)["status"] == "CANCELLED"
    assert service.cancel(UUID(payment["public_id"]))["status"] == "CANCELLED"
    with pytest.raises(AppError):
        service.checkout(order_uuid)
    with pytest.raises(AppError) as error:
        service.cancel_order(uuid4())
    assert error.value.status_code == 404
