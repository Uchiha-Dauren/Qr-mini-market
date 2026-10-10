"""Bank-only configuration without import-time environment access."""

from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        hide_input_in_errors=True,
        frozen=True,
    )
    bank_database_url: str = Field(default="sqlite:///./bank.db", min_length=1, repr=False)
    bank_public_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8001")
    shop_webhook_url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:8000/api/v1/webhooks/mock-bank")
    merchant_name: str = Field(default="QR Mini-Market", min_length=1, max_length=200)
    bank_merchant_api_key: SecretStr = Field(repr=False)
    webhook_secret: SecretStr = Field(repr=False)

    @field_validator("bank_merchant_api_key", "webhook_secret")
    @classmethod
    def validate_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value()
        if len(secret) < 32 or any(character.isspace() for character in secret):
            raise ValueError("Secrets must contain at least 32 characters and no whitespace")
        if secret.casefold().startswith(("change-me", "changeme", "replace-me", "your-secret")):
            raise ValueError("Replace example secrets with independently generated values")
        return value

    @field_validator("bank_public_url", "shop_webhook_url")
    @classmethod
    def validate_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username is not None or value.password is not None or value.fragment is not None:
            raise ValueError("Service URLs must not contain credentials or fragments")
        return value

    @field_validator("bank_public_url")
    @classmethod
    def validate_origin(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.query is not None or value.path not in (None, "/"):
            raise ValueError("BANK_PUBLIC_URL must contain only an HTTP(S) origin")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
