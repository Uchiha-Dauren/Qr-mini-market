"""Consistent public errors and logging that excludes exception input values."""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from pydantic import JsonValue
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.schemas.common import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)
HTTP_ERRORS = {
    400: ("BAD_REQUEST", "Некорректный запрос."),
    401: ("UNAUTHORIZED", "Требуется авторизация."),
    403: ("FORBIDDEN", "Недостаточно прав."),
    404: ("NOT_FOUND", "Ресурс не найден."),
    405: ("METHOD_NOT_ALLOWED", "Метод запроса не поддерживается."),
    409: ("CONFLICT", "Операция конфликтует с текущим состоянием."),
    410: ("GONE", "Ресурс больше недоступен."),
    422: ("VALIDATION_ERROR", "Некорректные данные запроса."),
    429: ("TOO_MANY_REQUESTS", "Слишком много запросов."),
    500: ("INTERNAL_ERROR", "Внутренняя ошибка сервера."),
    502: ("BAD_GATEWAY", "Ошибка внешнего сервиса."),
    503: ("SERVICE_UNAVAILABLE", "Сервис временно недоступен."),
}


class AppError(Exception):
    """An intentional error containing only data safe to expose to the client."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, JsonValue] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers={**(headers or {}), "Cache-Control": "no-store"},
    )


def log_safe_exception(exc: Exception) -> None:
    """Log stack locations without exception messages, source lines, or local values."""
    frames = traceback.extract_tb(exc.__traceback__)
    locations = "\n".join(f"{frame.filename}:{frame.lineno} in {frame.name}" for frame in frames)
    logger.error("Request failure (%s)\n%s", type(exc).__name__, locations)


class UnexpectedErrorMiddleware:
    """Handle failures before server middleware can log their unfiltered messages."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception as exc:
            log_safe_exception(exc)
            if response_started:
                raise RuntimeError("Request failed after response started") from None
            response = error_response(500, *HTTP_ERRORS[500])
            await response(scope, receive, send)


def install_error_handlers(app: FastAPI) -> None:
    """Register handlers for domain, HTTP, and request validation errors."""

    @app.exception_handler(AppError)
    def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(HTTPException)
    def handle_http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code >= 500:
            log_safe_exception(exc)
        code, message = HTTP_ERRORS.get(exc.status_code, ("HTTP_ERROR", "Ошибка запроса."))
        return error_response(exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]
        return error_response(422, *HTTP_ERRORS[422], details={"fields": fields})

    app.add_middleware(UnexpectedErrorMiddleware)
