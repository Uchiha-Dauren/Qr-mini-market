"""Test environment isolation, configuration validation, and secret handling."""

import os
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in list(os.environ):
        if name.casefold() in Settings.model_fields:
            monkeypatch.delenv(name)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def secret_values() -> dict[str, str]:
    return {
        name: secrets.token_urlsafe(32)
        for name in ("bank_merchant_api_key", "webhook_secret", "secret_key")
    }


def test_defaults_and_masked_secrets(secret_values: dict[str, str]) -> None:
    settings = Settings(_env_file=None, **secret_values)
    assert settings.app_env == "development"
    assert settings.currency == "KZT"
    assert settings.timezone == "Asia/Almaty"
    assert settings.payment_ttl_seconds == 300
    assert settings.payment_expiry_grace_seconds == 30
    for value in secret_values.values():
        assert value not in repr(settings)
        assert value not in settings.model_dump_json()


def test_dotenv_and_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, secret_values: dict[str, str]
) -> None:
    env_file = tmp_path / ".env"
    lines = [f"{name.upper()}={value}" for name, value in secret_values.items()]
    lines.extend(
        [
            "APP_ENV=test",
            "TIMEZONE=UTC",
            "PAYMENT_TTL_SECONDS=30",
            "BANK_DATABASE_URL=sqlite:///./bank.db",
            'MERCHANT_NAME="Учебный магазин"',
        ]
    )
    env_file.write_text("\n".join(lines), encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.app_env == "test"
    assert settings.timezone == "UTC"
    assert settings.payment_ttl_seconds == 30
    assert not hasattr(settings, "bank_database_url")
    monkeypatch.setenv("PAYMENT_TTL_SECONDS", "45")
    assert Settings(_env_file=env_file).payment_ttl_seconds == 45


@pytest.mark.parametrize("field", ["bank_merchant_api_key", "webhook_secret", "secret_key"])
def test_missing_secret_is_rejected(field: str, secret_values: dict[str, str]) -> None:
    del secret_values[field]
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **secret_values)


@pytest.mark.parametrize("value", ["", "short", "x" * 32 + " ", "change-me-" + "x" * 32])
def test_invalid_secret_is_rejected_without_exposing_input(
    value: str, secret_values: dict[str, str]
) -> None:
    secret_values["secret_key"] = value
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, **secret_values)
    assert "input_value" not in str(error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("app_env", "unknown"),
        ("currency", "USD"),
        ("timezone", "Unknown/City"),
        ("timezone", "/absolute/path"),
        ("payment_provider", "fake"),
        ("payment_ttl_seconds", 0),
        ("payment_ttl_seconds", -1),
        ("payment_ttl_seconds", 86401),
        ("payment_expiry_grace_seconds", -1),
        ("access_token_expire_minutes", 0),
        ("database_url", ""),
        ("bank_base_url", "ftp://localhost:8001"),
        ("bank_base_url", "not-a-url"),
        ("bank_base_url", "http://user:password@localhost:8001"),
        ("bank_base_url", "http://localhost:8001/api"),
        ("bank_base_url", "http://localhost:8001?key=value"),
        ("bank_base_url", "http://localhost:8001#fragment"),
    ],
)
def test_invalid_settings_are_rejected(
    field: str, value: str | int, secret_values: dict[str, str]
) -> None:
    data = {**secret_values, field: value}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **data)


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:8001", "http://192.168.1.50:8001", "http://mock_bank:8001"]
)
def test_local_bank_urls_are_allowed(url: str, secret_values: dict[str, str]) -> None:
    settings = Settings(_env_file=None, bank_base_url=url, **secret_values)
    assert str(settings.bank_base_url).rstrip("/") == url


def test_short_demo_ttl_and_zero_grace_are_allowed(secret_values: dict[str, str]) -> None:
    settings = Settings(
        _env_file=None, payment_ttl_seconds=30, payment_expiry_grace_seconds=0, **secret_values
    )
    assert settings.payment_ttl_seconds == 30
    assert settings.payment_expiry_grace_seconds == 0


def test_production_is_enabled_with_valid_secrets(secret_values: dict[str, str]) -> None:
    assert Settings(_env_file=None, app_env="production", **secret_values).app_env == "production"
