"""Run the independent applications through their actual HTTP contracts."""

import os
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.enums import UserRole
from app.db.session import create_db_engine
from app.main import create_app
from app.providers.mock_bank import MockBankProvider
from app.schemas.auth import CreateUserInput
from app.services.auth import create_user
from mock_bank.config import Settings as BankSettings
from mock_bank.main import create_app as create_bank_app
from mock_bank.seed import seed_accounts

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class WebhookBridge:
    """Capture signed HTTP bytes and optionally simulate a shop outage."""

    client: TestClient | None = None
    unavailable: bool = False
    requests: list[tuple[str, bytes, dict[str, str]]] = field(default_factory=list)

    def post(self, url: str, **kwargs: object) -> httpx.Response:
        content = kwargs["content"]
        headers = kwargs["headers"]
        assert isinstance(content, bytes)
        assert isinstance(headers, dict)
        self.requests.append((url, content, headers.copy()))
        if self.unavailable:
            return httpx.Response(503, request=httpx.Request("POST", url))
        assert self.client is not None
        return self.client.post(urlsplit(url).path, **kwargs)


@dataclass
class Market:
    shop: TestClient
    bank: TestClient
    bridge: WebhookBridge
    settings: Settings
    headers: dict[str, str]

    def api(self, method: str, path: str, **kwargs: object) -> dict:
        response = self.shop.request(method, "/api/v1" + path, headers=self.headers, **kwargs)
        assert 200 <= response.status_code < 300, response.text
        return response.json()


@pytest.fixture
def market(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Market]:
    """Provision separate databases, then connect only the injected HTTP clients."""
    fields = Settings.model_fields.keys() | BankSettings.model_fields.keys()
    for name in list(os.environ):
        if name.casefold() in fields:
            monkeypatch.delenv(name)
    merchant_key = secrets.token_urlsafe(32)
    webhook_secret = secrets.token_urlsafe(32)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'shop.db'}",
        bank_base_url="http://bank.test",
        bank_merchant_api_key=merchant_key,
        webhook_secret=webhook_secret,
        secret_key=secrets.token_urlsafe(32),
    )
    bank_settings = BankSettings(
        _env_file=None,
        bank_database_url=f"sqlite:///{tmp_path / 'bank.db'}",
        bank_public_url="http://bank.test",
        shop_webhook_url="http://shop.test/api/v1/webhooks/mock-bank",
        merchant_name="Тестовый мини-маркет",
        bank_merchant_api_key=merchant_key,
        webhook_secret=webhook_secret,
    )
    engine = create_db_engine(settings.database_url)
    try:
        with engine.begin() as connection:
            config = Config(str(ROOT / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        engine.dispose()
    bridge = WebhookBridge()
    bank_app = create_bank_app(bank_settings, webhook_client=bridge, run_worker=False)
    with TestClient(bank_app, base_url="http://bank.test") as bank:
        seed_accounts(bank_app.state.session_factory)
        provider = MockBankProvider(bank, settings)
        shop_app = create_app(settings, provider=provider, run_worker=False)
        with TestClient(shop_app, base_url="http://shop.test") as shop:
            bridge.client = shop
            password = secrets.token_urlsafe(24) + "Aa1!"
            create_user(
                shop_app.state.session_factory,
                CreateUserInput(username="e2e-admin", password=password, role=UserRole.ADMIN),
            )
            login = shop.post(
                "/api/v1/auth/login", json={"username": "e2e-admin", "password": password}
            )
            assert login.status_code == 200, login.text
            token = login.json()["access_token"]
            shop.cookies.clear()
            yield Market(shop, bank, bridge, settings, {"Authorization": f"Bearer {token}"})
