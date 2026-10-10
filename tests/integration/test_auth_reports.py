"""Exercise real password/JWT validation, browser CSRF, roles, and report snapshots."""

import secrets
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

import jwt
import pytest
from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event, inspect, select

import app.create_user as create_user_cli
from app.core.barcodes import generate_internal_ean13
from app.core.config import Settings
from app.core.enums import OrderStatus, PaymentStatus, ProductUnit, UserRole
from app.core.errors import AppError, install_error_handlers
from app.db.session import create_db_engine, create_session_factory
from app.models import Category, Order, OrderItem, Payment, Product, User
from app.routers.auth import router as auth_router
from app.routers.reports import router as reports_router
from app.schemas.auth import CreateUserInput, LoginInput
from app.services.auth import (
    PASSWORD_HASHER,
    TOKEN_AUDIENCE,
    TOKEN_ISSUER,
    authenticate,
    create_user,
    require_admin,
    require_cashier,
)
from app.services.reports import low_stock_report, payments_review_report, sales_report

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def credentials() -> tuple[str, str]:
    password = secrets.token_urlsafe(24)
    return password, PASSWORD_HASHER.hash(password)


@pytest.fixture
def auth_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, credentials: tuple[str, str]):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
        secret_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        bank_merchant_api_key=secrets.token_urlsafe(32),
    )
    engine = create_db_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        with engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with factory.begin() as session:
            admin = User(username="admin", password_hash=credentials[1], role=UserRole.ADMIN)
            cashier = User(username="cashier", password_hash=credentials[1], role=UserRole.CASHIER)
            session.add_all([admin, cashier])
            session.flush()
        app = FastAPI()
        app.state.settings = settings
        app.state.session_factory = factory
        install_error_handlers(app)
        app.include_router(auth_router)
        app.include_router(reports_router)

        @app.get("/_test/cashier")
        def cashier_only(user: Annotated[User, Depends(require_cashier)]) -> dict:
            return {"username": user.username, "detached": inspect(user).detached}

        @app.post("/_test/admin")
        def admin_only(user: Annotated[User, Depends(require_admin)]) -> dict:
            return {"username": user.username}

        yield app, settings, factory, admin, cashier
    finally:
        engine.dispose()


@pytest.fixture
def client(auth_context) -> Iterator[TestClient]:
    with TestClient(auth_context[0]) as value:
        yield value


def login(client: TestClient, credentials: tuple[str, str], username: str = "admin") -> dict:
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": credentials[0]}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_login_cookie_flags_me_and_logout(client: TestClient, credentials: tuple[str, str]) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    cookies = response.headers.get_list("set-cookie")
    assert "HttpOnly" in cookies[0] and "SameSite=lax" in cookies[0]
    assert "HttpOnly" not in cookies[1]
    me = client.get("/api/v1/auth/me")
    assert set(me.json()) == {"public_id", "username", "role"}
    assert me.json()["role"] == "ADMIN"
    assert credentials[0] not in response.text and credentials[1] not in response.text
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": response.json()["csrf_token"]}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cookie_mutations_require_signed_double_submit_token(
    client: TestClient, credentials
) -> None:
    result = login(client, credentials)
    assert client.post("/_test/admin").status_code == 403
    assert client.post("/_test/admin", headers={"X-CSRF-Token": "forged"}).status_code == 403
    headers = {"X-CSRF-Token": result["csrf_token"]}
    assert client.post("/_test/admin", headers=headers).status_code == 200
    assert (
        client.post(
            "/_test/admin", headers={**headers, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    client.cookies.set("csrf_token", "forged")
    assert client.post("/_test/admin", headers=headers).status_code == 403


def test_bearer_does_not_need_cookie_csrf_and_users_are_detached(
    client: TestClient, credentials
) -> None:
    token = login(client, credentials)["access_token"]
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/_test/admin", headers=headers).status_code == 200
    assert client.get("/_test/cashier", headers=headers).json()["detached"] is True


@pytest.mark.parametrize(
    "origin",
    ["https://evil.example", "null", "http://testserver:81", "http://testserver@evil.example"],
)
def test_cross_origin_login_rejected(client: TestClient, credentials, origin: str) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials[0]},
        headers={"Origin": origin},
    )
    assert response.status_code == 403


def test_same_origin_login_allowed(client: TestClient, credentials) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": credentials[0]},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize("username", ["admin", "unknown"])
def test_wrong_credentials_are_generic(client: TestClient, username: str, caplog) -> None:
    canary = "not-a-valid-password-'; DROP TABLE users;--"
    response = client.post("/api/v1/auth/login", json={"username": username, "password": canary})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert canary not in response.text and canary not in caplog.text


def test_invalid_username_form_login_and_password_overflow_rejected(client: TestClient) -> None:
    for body in (
        {"username": "admin' OR 1=1--", "password": "x"},
        {"username": "admin", "password": "x" * 129},
        {"username": "admin", "password": "x", "role": "ADMIN"},
    ):
        assert client.post("/api/v1/auth/login", json=body).status_code == 422
    assert (
        client.post("/api/v1/auth/login", data={"username": "admin", "password": "x"}).status_code
        == 422
    )


def test_live_role_and_active_checks(client: TestClient, auth_context, credentials) -> None:
    _, _, factory, admin, _ = auth_context
    result = login(client, credentials)
    headers = {"Authorization": f"Bearer {result['access_token']}"}
    with factory.begin() as session:
        session.get(User, admin.id).role = UserRole.CASHIER
    assert client.post("/_test/admin", headers=headers).status_code == 403
    assert client.get("/_test/cashier", headers=headers).status_code == 200
    with factory.begin() as session:
        session.get(User, admin.id).is_active = False
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/reports/sales",
        "/api/v1/reports/low-stock",
        "/api/v1/reports/payments-needing-review",
    ],
)
def test_reports_require_admin(client: TestClient, credentials, path: str) -> None:
    assert client.get(path).status_code == 401
    login(client, credentials, "cashier")
    assert client.get(path).status_code == 403


@pytest.mark.parametrize(
    "kind",
    [
        "expired",
        "future",
        "issuer",
        "audience",
        "missing_exp",
        "missing_csrf",
        "bad_sub",
        "none",
        "wrong_signature",
    ],
)
def test_invalid_jwt_rejected(client: TestClient, auth_context, kind: str) -> None:
    _, settings, _, admin, _ = auth_context
    now = datetime.now(UTC)
    claims = {
        "sub": str(admin.public_id),
        "iss": TOKEN_ISSUER,
        "aud": TOKEN_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=1),
        "jti": "test",
        "csrf": "x" * 32,
    }
    if kind == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    elif kind == "future":
        claims["nbf"] = now + timedelta(hours=1)
    elif kind in ("issuer", "audience"):
        claims["iss" if kind == "issuer" else "aud"] = "wrong"
    elif kind.startswith("missing_"):
        claims.pop(kind.removeprefix("missing_"))
    elif kind == "bad_sub":
        claims["sub"] = "123"
    key = (
        secrets.token_urlsafe(32)
        if kind == "wrong_signature"
        else settings.secret_key.get_secret_value()
    )
    token = jwt.encode(
        claims, None if kind == "none" else key, algorithm="none" if kind == "none" else "HS256"
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_bad_authorization_does_not_fall_back_to_cookie(client: TestClient, credentials) -> None:
    login(client, credentials)
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_production_cookie_uses_secure_flag(client: TestClient, auth_context, credentials) -> None:
    app, settings, *_ = auth_context
    app.state.settings = settings.model_copy(update={"app_env": "production"})
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
    )
    assert response.status_code == 200
    assert all("Secure" in item for item in response.headers.get_list("set-cookie"))


def test_corrupt_password_hash_returns_generic_401(
    client: TestClient, auth_context, credentials
) -> None:
    _, _, factory, admin, _ = auth_context
    with factory.begin() as session:
        session.get(User, admin.id).password_hash = "corrupted-hash"
    response = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": credentials[0]}
    )
    assert response.status_code == 401
    assert "corrupted-hash" not in response.text


def test_create_user_cli_getpass_and_safe_output(
    auth_context, credentials, monkeypatch, capsys
) -> None:
    _, settings, factory, _, _ = auth_context
    monkeypatch.setattr("sys.argv", ["create_user", "--username", "cli-user", "--role", "CASHIER"])
    monkeypatch.setattr(create_user_cli.getpass, "getpass", lambda _prompt: credentials[0])
    monkeypatch.setattr(create_user_cli, "get_settings", lambda: settings)
    assert create_user_cli.main() == 0
    with factory() as session:
        user = session.scalar(select(User).where(User.username == "cli-user"))
        assert user is not None and PASSWORD_HASHER.verify(user.password_hash, credentials[0])
    output = capsys.readouterr()
    assert "cli-user" in output.out
    assert credentials[0] not in output.out + output.err


def test_create_user_cli_password_mismatch_never_opens_database(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.argv", ["create_user", "--username", "cli-user", "--role", "ADMIN"])
    passwords = iter(["one-test-password", "another-test-password"])
    monkeypatch.setattr(create_user_cli.getpass, "getpass", lambda _prompt: next(passwords))
    monkeypatch.setattr(create_user_cli, "get_settings", lambda: pytest.fail("No database needed"))
    assert create_user_cli.main() == 1
    assert "Пароли не совпадают" in capsys.readouterr().err


def test_create_user_and_duplicate_are_safe(auth_context, credentials) -> None:
    _, settings, factory, _, _ = auth_context
    data = CreateUserInput(username="new-user", password=credentials[0], role="CASHIER")
    user = create_user(factory, data)
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != credentials[0]
    response = authenticate(
        factory, LoginInput(username="new-user", password=credentials[0]), settings
    )
    assert response.user.public_id == user.public_id
    with pytest.raises(AppError) as error:
        create_user(factory, data)
    assert error.value.status_code == 409
    with pytest.raises(ValidationError):
        CreateUserInput(username="new", password="short", role="ADMIN")


def test_successful_login_rehashes_old_argon_parameters(auth_context, credentials) -> None:
    _, settings, factory, admin, _ = auth_context
    old_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(credentials[0])
    with factory.begin() as session:
        session.get(User, admin.id).password_hash = old_hash
    authenticate(factory, LoginInput(username="admin", password=credentials[0]), settings)
    with factory() as session:
        new_hash = session.get(User, admin.id).password_hash
    assert new_hash != old_hash
    assert not PASSWORD_HASHER.check_needs_rehash(new_hash)


@pytest.fixture
def report_data(auth_context):
    _, _, factory, admin, _ = auth_context
    with factory.begin() as session:
        category = Category(name="Еда", slug="report-food")
        session.add(category)
        session.flush()
        product = Product(
            name="Новое имя",
            barcode=generate_internal_ean13(500),
            category_id=category.id,
            unit=ProductUnit.PIECE,
            price_minor=999,
            stock_quantity=10,
            reserved_quantity=8,
            min_stock_quantity=2,
        )
        inactive = Product(
            name="Неактивный",
            barcode=generate_internal_ean13(501),
            category_id=category.id,
            unit=ProductUnit.PIECE,
            price_minor=999,
            stock_quantity=0,
            min_stock_quantity=10,
            is_active=False,
        )
        session.add_all([product, inactive])
        session.flush()
        # 2026-10-10 starts at 19:00 UTC on the previous day in Asia/Almaty.
        paid_times = [
            datetime(2026, 10, 9, 18, 59, 59, tzinfo=UTC),
            datetime(2026, 10, 9, 19, tzinfo=UTC),
            datetime(2026, 10, 10, 18, 59, 59, tzinfo=UTC),
            datetime(2026, 10, 10, 19, tzinfo=UTC),
        ]
        orders = []
        for index, paid_at in enumerate(paid_times):
            order = Order(
                number=f"report-{index}",
                terminal_code=f"report-{index}",
                status=OrderStatus.PAID,
                total_minor=250,
                paid_at=paid_at,
                cashier_id=admin.id,
            )
            session.add(order)
            session.flush()
            session.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    product_name="Старое имя",
                    barcode=product.barcode,
                    unit=ProductUnit.PIECE,
                    unit_price_minor=125,
                    quantity=2,
                    line_total_minor=250,
                )
            )
            orders.append(order)
        excluded = Order(
            number="report-open",
            terminal_code="report-open",
            total_minor=999,
            status=OrderStatus.OPEN,
        )
        session.add(excluded)
        session.flush()
        payment = Payment(
            order_id=orders[0].id,
            status=PaymentStatus.FAILED,
            amount_minor=250,
            needs_review=True,
            review_reason="late_success",
            provider_invoice_id="internal-provider-id",
        )
        session.add(payment)
        session.flush()
        return product.public_id, category.public_id, payment.public_id


def test_report_filters_local_days_and_uses_historical_snapshots(auth_context, report_data) -> None:
    _, settings, factory, _, _ = auth_context
    report = sales_report(factory, settings, date(2026, 10, 10), date(2026, 10, 10))
    assert report["orders_count"] == 2
    assert report["revenue_minor"] == 500
    assert report["revenue_minor_text"] == "500"
    assert report["days"] == [
        {"date": "2026-10-10", "orders_count": 2, "revenue_minor": 500, "revenue_minor_text": "500"}
    ]
    assert report["products"][0]["name"] == "Старое имя"
    assert report["products"][0]["quantity"] == 4
    assert report["categories"][0]["public_id"] == str(report_data[1])
    assert report["categories"][0]["revenue_minor"] == 500


def test_sales_totals_do_not_overflow_sqlite_or_python(auth_context, report_data) -> None:
    _, settings, factory, _, _ = auth_context
    with factory.begin() as session:
        for item in session.scalars(select(OrderItem)):
            item.line_total_minor = 2**63 - 1
    report = sales_report(factory, settings, date(2026, 10, 10), date(2026, 10, 10))
    assert report["revenue_minor"] == (2**63 - 1) * 2
    assert report["revenue_minor_text"] == str((2**63 - 1) * 2)


def test_sales_counts_multi_item_orders_in_one_statement_snapshot(
    auth_context, report_data
) -> None:
    """Header counts and line sums must share a statement snapshot on PostgreSQL."""
    _, settings, factory, _, _ = auth_context
    with factory.begin() as session:
        order = session.scalar(select(Order).where(Order.number == "report-1"))
        product = session.scalar(select(Product).where(Product.is_active.is_(False)))
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name="Вторая позиция",
                barcode=product.barcode,
                unit=ProductUnit.PIECE,
                unit_price_minor=150,
                quantity=1,
                line_total_minor=150,
            )
        )
    engine = factory.kw["bind"]
    statements = []

    def record(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        report = sales_report(factory, settings, date(2026, 10, 10), date(2026, 10, 10))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert len(statements) == 1
    assert report["orders_count"] == 2
    assert report["revenue_minor"] == 650
    assert len(report["products"]) == 2
    assert report["days"][0]["orders_count"] == 2
    assert report["days"][0]["revenue_minor"] == 650


@pytest.mark.parametrize(
    "dates",
    [
        (date(2026, 10, 11), date(2026, 10, 10)),
        (date(2025, 1, 1), date(2026, 10, 10)),
        (date.min, date.min),
        (date.max, date.max),
    ],
)
def test_invalid_report_period_rejected(auth_context, dates) -> None:
    with pytest.raises(AppError) as error:
        sales_report(auth_context[2], auth_context[1], *dates)
    assert error.value.status_code == 422


def test_low_stock_counts_available_and_excludes_inactive(auth_context, report_data) -> None:
    report = low_stock_report(auth_context[2], limit=1)
    assert report["total"] == 1
    item = report["items"][0]
    assert item["public_id"] == str(report_data[0])
    assert item["available_quantity"] == 2
    assert item["stock_quantity"] == 10
    assert item["category_id"] == str(report_data[1])
    assert "id" not in item
    assert low_stock_report(auth_context[2], limit=1, offset=1)["items"] == []


def test_payment_review_pagination_excludes_internal_fields(auth_context, report_data) -> None:
    report = payments_review_report(auth_context[2])
    assert report["total"] == 1
    item = report["items"][0]
    assert item["public_id"] == str(report_data[2])
    assert item["review_reason"] == "late_success"
    assert "provider_invoice_id" not in item
    assert "id" not in item
    assert payments_review_report(auth_context[2], limit=1, offset=1)["items"] == []


@pytest.mark.parametrize("parameters", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_report_pagination_validation(auth_context, parameters) -> None:
    with pytest.raises(AppError):
        low_stock_report(auth_context[2], **parameters)


def test_report_api_serializes_and_validates_parameters(
    client: TestClient, credentials, report_data
) -> None:
    login(client, credentials)
    response = client.get(
        "/api/v1/reports/sales", params={"date_from": "2026-10-10", "date_to": "2026-10-10"}
    )
    assert response.status_code == 200
    assert response.json()["revenue_minor"] == 500
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/reports/sales?date_from=bad").status_code == 422
    assert client.get("/api/v1/reports/low-stock?limit=101").status_code == 422
    assert client.get("/api/v1/reports/payments-needing-review").status_code == 200
