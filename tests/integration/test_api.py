"""Exercise application lifecycle, error contracts, and session cleanup."""

import os
import secrets
from pathlib import Path
from typing import Annotated
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Integer, MetaData, Table, func, inspect, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

import app.main as main_module
from app.core.config import Settings
from app.core.errors import AppError
from app.dependencies import get_session
from app.main import create_app
from app.schemas.common import HealthResponse

CANARY = "test-only-sensitive-value"


class InputPayload(BaseModel):
    quantity: int = Field(gt=0)
    password: str

    @field_validator("password")
    @classmethod
    def reject_canary(cls, value: str) -> str:
        if value == CANARY:
            raise ValueError(value)
        return value


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.casefold() in Settings.model_fields:
            monkeypatch.delenv(name)
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        bank_merchant_api_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
        secret_key=secrets.token_urlsafe(32),
    )


@pytest.fixture
def application(settings: Settings) -> FastAPI:
    app = create_app(settings, run_worker=False)

    @app.post("/_test/input", include_in_schema=False)
    def validate_input(payload: InputPayload) -> dict[str, int]:
        return {"quantity": payload.quantity}

    @app.get("/_test/domain", include_in_schema=False)
    def domain_error() -> None:
        raise AppError(409, "ORDER_NOT_OPEN", "Чек нельзя изменить.", {"status": "PAID"})

    @app.get("/_test/http/{status_code}", include_in_schema=False)
    def http_error(status_code: int) -> None:
        raise HTTPException(status_code, detail=CANARY, headers={"WWW-Authenticate": "Bearer"})

    @app.get("/_test/failure", include_in_schema=False)
    def unexpected_error() -> None:
        raise RuntimeError(CANARY)

    @app.get("/_test/response", response_model=HealthResponse, include_in_schema=False)
    def invalid_response() -> dict[str, str]:
        return {"status": CANARY, "database": "ok"}

    return app


def test_factory_is_lazy(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    engine_factory = Mock(side_effect=AssertionError("Engine must not be created yet"))
    monkeypatch.setattr(main_module, "create_db_engine", engine_factory)
    app = create_app(settings, run_worker=False)
    assert not hasattr(app.state, "engine")
    engine_factory.assert_not_called()


def test_health_lifecycle_and_no_schema_creation(settings: Settings) -> None:
    app = create_app(settings, run_worker=False)
    with TestClient(app) as client:
        engine = app.state.engine
        dispose = Mock(wraps=engine.dispose)
        engine.dispose = dispose
        response = client.get("/health", headers={"Origin": "http://untrusted.example"})
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "database": "ok"}
        assert response.headers["cache-control"] == "no-store"
        assert "access-control-allow-origin" not in response.headers
        assert inspect(engine).get_table_names() == []
    dispose.assert_called_once_with()
    assert not hasattr(app.state, "session_factory")
    assert not hasattr(app.state, "engine")


def test_dispose_after_startup_failure(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = main_module.create_db_engine(settings.database_url)
    dispose = Mock(wraps=engine.dispose)
    monkeypatch.setattr(engine, "dispose", dispose)
    monkeypatch.setattr(main_module, "create_db_engine", lambda _url: engine)
    monkeypatch.setattr(
        main_module, "ping_database", Mock(side_effect=RuntimeError("Startup failed"))
    )
    app = create_app(settings, run_worker=False)
    with pytest.raises(RuntimeError, match="Startup failed"), TestClient(app):
        pytest.fail("Startup must fail")
    dispose.assert_called_once_with()
    assert not hasattr(app.state, "engine")


@pytest.mark.parametrize("path", ["/missing", "/docs", "/redoc"])
def test_not_found_is_json(application: FastAPI, path: str) -> None:
    with TestClient(application) as client:
        response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_method_error_preserves_allow_header(application: FastAPI) -> None:
    with TestClient(application) as client:
        response = client.post("/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in response.headers["allow"]


def test_domain_error_contract(application: FastAPI) -> None:
    with TestClient(application) as client:
        response = client.get("/_test/domain")
    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "ORDER_NOT_OPEN",
            "message": "Чек нельзя изменить.",
            "details": {"status": "PAID"},
        }
    }


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 410, 422, 429, 500, 502, 503])
def test_http_errors_do_not_echo_detail(
    application: FastAPI, status_code: int, caplog: pytest.LogCaptureFixture
) -> None:
    with TestClient(application) as client:
        response = client.get(f"/_test/http/{status_code}")
    assert response.status_code == status_code
    assert set(response.json()["error"]) == {"code", "message", "details"}
    assert response.headers["www-authenticate"] == "Bearer"
    assert CANARY not in response.text
    assert CANARY not in caplog.text


@pytest.mark.parametrize("quantity", [None, 0, -1, "invalid"])
def test_validation_does_not_echo_sensitive_values(application: FastAPI, quantity: object) -> None:
    with TestClient(application) as client:
        response = client.post("/_test/input", json={"quantity": quantity, "password": CANARY})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["fields"]
    assert CANARY not in response.text
    for field in error["details"]["fields"]:
        assert set(field) == {"location", "type"}


@pytest.mark.parametrize("path", ["/_test/failure", "/_test/response"])
def test_internal_error_is_safe_without_reraising(
    application: FastAPI, path: str, caplog: pytest.LogCaptureFixture
) -> None:
    with TestClient(application) as client:
        response = client.get(path)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "Traceback" not in response.text
    assert CANARY not in response.text
    assert CANARY not in caplog.text
    assert "Request failure" in caplog.text


def test_database_failure_is_503(
    application: FastAPI, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with TestClient(application) as client:
        failure = OperationalError("SELECT 1", {}, RuntimeError(CANARY))
        monkeypatch.setattr(application.state.engine, "connect", Mock(side_effect=failure))
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert CANARY not in response.text
    assert CANARY not in caplog.text


@pytest.mark.parametrize("fail", [False, True])
def test_request_session_closes_without_commit(application: FastAPI, fail: bool) -> None:
    metadata = MetaData()
    probe = Table("request_probe", metadata, Column("id", Integer, primary_key=True))

    @application.post("/_test/session", include_in_schema=False)
    def write_without_commit(session: Annotated[Session, Depends(get_session)]) -> dict[str, bool]:
        session.execute(probe.insert().values(id=1))
        if fail:
            raise RuntimeError(CANARY)
        return {"ok": True}

    with TestClient(application) as client:
        engine = application.state.engine
        metadata.create_all(engine)
        assert client.post("/_test/session").status_code == (500 if fail else 200)
        assert engine.pool.checkedout() == 0
        with engine.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(probe)) == 0


def test_openapi_exposes_only_real_routes_and_error_schema(settings: Settings) -> None:
    with TestClient(create_app(settings, run_worker=False)) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert {
        "/health",
        "/api/v1/products",
        "/api/v1/orders",
        "/api/v1/auth/login",
        "/api/v1/webhooks/mock-bank",
    } <= set(schema["paths"])
    assert not any(path.startswith("/_test") for path in schema["paths"])
    response_schema = schema["paths"]["/health"]["get"]["responses"]["503"]
    assert response_schema["content"]["application/json"]["schema"]["$ref"].endswith(
        "ErrorResponse"
    )
