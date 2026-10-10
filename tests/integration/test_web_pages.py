"""Verify protected HTML routes, template escaping, and offline asset delivery."""

import secrets
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.enums import UserRole
from app.db.session import create_db_engine, create_session_factory
from app.main import create_app
from app.models import User
from app.providers.fake import FakeProvider
from app.services.auth import PASSWORD_HASHER

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def password_pair():
    password = secrets.token_urlsafe(24)
    return password, PASSWORD_HASHER.hash(password)


@pytest.fixture
def web_client(tmp_path, monkeypatch, password_pair):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'pages.db'}",
        secret_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        bank_merchant_api_key=secrets.token_urlsafe(32),
    )
    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        with create_session_factory(engine).begin() as session:
            session.add_all(
                [
                    User(username="admin", password_hash=password_pair[1], role=UserRole.ADMIN),
                    User(username="cashier", password_hash=password_pair[1], role=UserRole.CASHIER),
                ]
            )
    finally:
        engine.dispose()
    with TestClient(create_app(settings, provider=FakeProvider(), run_worker=False)) as client:
        yield client


def login(client, password_pair, username="admin"):
    response = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password_pair[0]}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/cashier", "/admin", f"/receipt/{uuid4()}"])
def test_protected_html_redirects_before_render(web_client, path):
    response = web_client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "product-form" not in response.text


@pytest.mark.parametrize("path", ["/login", "/price-check", "/display/main"])
def test_public_html_uses_local_assets_and_security_policy(web_client, path):
    response = web_client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert 'src="/static/shop.js"' in response.text
    assert 'href="/static/shop.css"' in response.text
    assert "https://" not in response.text
    assert 'lang="ru"' in response.text


def test_cashier_role_cannot_render_admin(web_client, password_pair):
    login(web_client, password_pair, "cashier")
    response = web_client.get("/admin")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    response = web_client.get("/cashier")
    assert response.status_code == 200
    assert 'id="scan-form"' in response.text
    assert 'href="/admin"' not in response.text


def test_admin_can_render_operational_pages(web_client, password_pair):
    login(web_client, password_pair)
    for path in ["/admin", "/cashier", f"/receipt/{uuid4()}"]:
        response = web_client.get(path)
        assert response.status_code == 200
        assert 'href="/admin"' in response.text
    assert 'id="print-receipt"' in response.text


def test_injected_terminal_does_not_render_html(web_client):
    response = web_client.get("/display/%3Cscript%3Ealert(1)%3C%2Fscript%3E")
    assert response.status_code in (404, 422)
    assert "<script>alert" not in response.text


@pytest.mark.parametrize("filename", ["shop.css", "shop.js", "mark.svg"])
def test_static_assets_are_delivered_without_auth(web_client, filename):
    response = web_client.get(f"/static/{filename}")
    assert response.status_code == 200
    assert response.content


def test_logout_protects_next_html_request(web_client, password_pair):
    login(web_client, password_pair)
    response = web_client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": web_client.cookies["csrf_token"]}
    )
    assert response.status_code == 200
    assert web_client.get("/cashier", follow_redirects=False).status_code == 303
