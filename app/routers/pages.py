"""Server-rendered entry pages with role checks and local static assets."""

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.errors import AppError
from app.services.auth import require_admin, require_cashier

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


def page(request: Request, name: str, *, role: str | None = None, **context: object):
    """Authenticate protected HTML pages before rendering any operational content."""
    user = None
    if role:
        try:
            user = require_admin(request) if role == "admin" else require_cashier(request)
        except AppError as exc:
            if exc.status_code == 401:
                return RedirectResponse("/login", status_code=303)
            raise
    response = templates.TemplateResponse(
        request=request,
        name=f"{name}.html",
        context={
            "page": name,
            "user": user,
            "development": request.app.state.settings.app_env == "development",
            "timezone": request.app.state.settings.timezone,
            **context,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    return response


@router.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse("/cashier", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login(request: Request):
    return page(request, "login")


@router.get("/cashier", response_class=HTMLResponse)
def cashier(request: Request):
    return page(request, "cashier", role="cashier")


@router.get("/display/{terminal_code}", response_class=HTMLResponse)
def display(request: Request, terminal_code: str):
    if not 1 <= len(terminal_code) <= 64 or not all(
        character.isascii() and (character.isalnum() or character in "_-")
        for character in terminal_code
    ):
        raise AppError(404, "NOT_FOUND", "Терминал не найден.")
    return page(request, "display", terminal_code=terminal_code)


@router.get("/price-check", response_class=HTMLResponse)
def price_check(request: Request):
    return page(request, "price-check")


@router.get("/receipt/{order_uuid}", response_class=HTMLResponse)
def receipt(request: Request, order_uuid: UUID):
    return page(request, "receipt", role="cashier", order_uuid=str(order_uuid))


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    return page(request, "admin", role="admin")
