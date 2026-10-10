"""Public Russian error envelopes without exception messages or request input."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class BankError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def response(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status_code=status,
        headers={"Cache-Control": "no-store"},
    )


class SafeErrors:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = False

        async def track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; style-src 'self'; "
                        b"frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
                    ),
                ]
            await send(message)

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, track)
        except Exception as exc:
            logger.error("Bank request failed (%s)", type(exc).__name__)
            if started:
                raise RuntimeError("Bank response interrupted") from None
            await response(500, "INTERNAL_ERROR", "Внутренняя ошибка банка.")(scope, receive, track)


def install_errors(app: FastAPI) -> None:
    @app.exception_handler(BankError)
    def bank_error(_request: Request, exc: BankError) -> JSONResponse:
        return response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    def validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]
        return response(422, "VALIDATION_ERROR", "Некорректные данные запроса.", {"fields": fields})

    @app.exception_handler(HTTPException)
    def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        result = response(
            exc.status_code,
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "Ресурс не найден." if exc.status_code == 404 else "Ошибка запроса.",
        )
        if exc.headers:
            result.headers.update(exc.headers)
        return result

    app.add_middleware(SafeErrors)
