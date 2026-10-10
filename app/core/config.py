"""Load and validate the shop configuration without import-time side effects."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Shop settings; bank-only environment entries are intentionally ignored."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
        frozen=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = Field(default="sqlite:///./shop.db", min_length=1, repr=False)
    currency: Literal["KZT"] = "KZT"
    timezone: str = "Asia/Almaty"
    payment_provider: Literal["mock_bank"] = "mock_bank"
    payment_ttl_seconds: int = Field(default=300, gt=0, le=86400)
    payment_expiry_grace_seconds: int = Field(default=30, ge=0)
    bank_base_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8001")
    bank_merchant_api_key: SecretStr = Field(repr=False)
    webhook_secret: SecretStr = Field(repr=False)
    secret_key: SecretStr = Field(repr=False)
    access_token_expire_minutes: int = Field(default=60, gt=0)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("TIMEZONE must be a valid IANA time zone") from exc
        return value

    @field_validator("bank_base_url")
    @classmethod
    def validate_bank_base_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("BANK_BASE_URL must not contain credentials")
        if value.query is not None or value.fragment is not None or value.path not in (None, "/"):
            raise ValueError("BANK_BASE_URL must contain only an HTTP(S) origin")
        return value

    @field_validator("bank_merchant_api_key", "webhook_secret", "secret_key")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or any(character.isspace() for character in secret):
            raise ValueError("Secrets must contain at least 32 characters and no whitespace")
        if secret.casefold().startswith(("change-me", "changeme", "replace-me", "your-secret")):
            raise ValueError("Replace example secrets with independently generated values")
        return value


@lru_cache
def get_settings() -> Settings:
    """Load settings on first use; restart the process after changing configuration."""
    return Settings()
