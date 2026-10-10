"""Argon2 credentials, short-lived JWTs, and live role checks for every request."""

import hmac
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import UserRole
from app.core.errors import AppError
from app.db.transactions import run_write
from app.models import User
from app.schemas.auth import CreateUserInput, LoginInput, LoginResponse, UserResponse

TOKEN_ISSUER = "qr-mini-market"
TOKEN_AUDIENCE = "qr-mini-market:shop"
PASSWORD_HASHER = PasswordHasher()
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """Make nonexistent-user verification perform the same expensive operation."""
    return PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def create_user(factory: sessionmaker[Session], data: CreateUserInput) -> User:
    """Hash outside the write transaction; do not overwrite an existing account."""
    password_hash = PASSWORD_HASHER.hash(data.password.get_secret_value())

    def operation(session: Session) -> User:
        user = User(username=data.username, password_hash=password_hash, role=data.role)
        session.add(user)
        session.flush()
        return user

    try:
        return run_write(factory, operation)
    except IntegrityError:
        raise AppError(
            409, "USERNAME_EXISTS", "Пользователь с таким именем уже существует."
        ) from None


def authenticate(
    factory: sessionmaker[Session], data: LoginInput, settings: Settings
) -> LoginResponse:
    """Verify credentials without holding a database transaction during Argon2."""
    with factory() as session:
        user = session.scalar(select(User).where(User.username == data.username))
        stored_hash = user.password_hash if user is not None else None
    stored_hash = stored_hash if stored_hash is not None else _dummy_hash()
    try:
        valid = PASSWORD_HASHER.verify(stored_hash, data.password.get_secret_value())
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or user is None or not user.is_active:
        raise AppError(401, "INVALID_CREDENTIALS", "Неверное имя пользователя или пароль.")

    new_hash = (
        PASSWORD_HASHER.hash(data.password.get_secret_value())
        if PASSWORD_HASHER.check_needs_rehash(stored_hash)
        else None
    )

    def confirm(session: Session) -> User:
        current = session.scalar(select(User).where(User.id == user.id).with_for_update())
        if current is None or not current.is_active or current.password_hash != stored_hash:
            raise AppError(401, "INVALID_CREDENTIALS", "Неверное имя пользователя или пароль.")
        if new_hash is not None:
            current.password_hash = new_hash
            session.flush()
        return current

    current = run_write(factory, confirm)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(current.public_id),
            "iss": TOKEN_ISSUER,
            "aud": TOKEN_AUDIENCE,
            "iat": now,
            "nbf": now,
            "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
            "jti": secrets.token_urlsafe(24),
            "csrf": csrf_token,
        },
        settings.secret_key.get_secret_value(),
        algorithm="HS256",
    )
    return LoginResponse(
        user=UserResponse.model_validate(current), access_token=token, csrf_token=csrf_token
    )


def require_same_origin(request: Request) -> None:
    """Reject cross-site browser login attempts, while permitting originless API clients."""
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise AppError(403, "CSRF_FAILED", "Недопустимый источник запроса.")
    if origin is None:
        return
    try:
        supplied = urlsplit(origin)
        expected = urlsplit(str(request.base_url))
        supplied_origin = (
            supplied.scheme,
            supplied.hostname,
            supplied.port or _port(supplied.scheme),
        )
        expected_origin = (
            expected.scheme,
            expected.hostname,
            expected.port or _port(expected.scheme),
        )
    except ValueError:
        raise AppError(403, "CSRF_FAILED", "Недопустимый источник запроса.") from None
    if (
        supplied_origin != expected_origin
        or supplied.username is not None
        or supplied.password is not None
        or supplied.path not in ("", "/")
        or supplied.query
        or supplied.fragment
    ):
        raise AppError(403, "CSRF_FAILED", "Недопустимый источник запроса.")


def _port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def require_user(request: Request) -> User:
    """Return a detached active user; cookie-authenticated writes also require CSRF."""
    authorization = request.headers.get("authorization")
    cookie_auth = authorization is None
    if cookie_auth:
        token = request.cookies.get("access_token", "")
    else:
        parts = authorization.split()
        if len(parts) != 2 or parts[0].casefold() != "bearer":
            raise AppError(401, "UNAUTHORIZED", "Требуется авторизация.")
        token = parts[1]
    settings: Settings = request.app.state.settings
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=["HS256"],
            issuer=TOKEN_ISSUER,
            audience=TOKEN_AUDIENCE,
            options={"require": ["exp", "iat", "nbf", "sub", "iss", "aud", "jti", "csrf"]},
        )
        user_uuid = UUID(claims["sub"])
        if not isinstance(claims["csrf"], str) or len(claims["csrf"]) < 32:
            raise ValueError("Invalid CSRF claim")
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError):
        raise AppError(401, "UNAUTHORIZED", "Сессия недействительна. Войдите снова.") from None
    if cookie_auth and request.method not in SAFE_METHODS:
        require_same_origin(request)
        header = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get("csrf_token", "")
        # Encode attacker-controlled Unicode before constant-time comparison.
        if not hmac.compare_digest(
            header.encode(), claims["csrf"].encode()
        ) or not hmac.compare_digest(cookie.encode(), claims["csrf"].encode()):
            raise AppError(403, "CSRF_FAILED", "Обновите страницу и повторите действие.")
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        user = session.scalar(
            select(User).where(User.public_id == user_uuid, User.is_active.is_(True))
        )
        if user is None:
            raise AppError(401, "UNAUTHORIZED", "Сессия недействительна. Войдите снова.")
        session.expunge(user)
        return user


def require_cashier(request: Request) -> User:
    user = require_user(request)
    if user.role not in (UserRole.ADMIN, UserRole.CASHIER):
        raise AppError(403, "FORBIDDEN", "Недостаточно прав.")
    return user


def require_admin(request: Request) -> User:
    user = require_user(request)
    if user.role is not UserRole.ADMIN:
        raise AppError(403, "FORBIDDEN", "Требуются права администратора.")
    return user
