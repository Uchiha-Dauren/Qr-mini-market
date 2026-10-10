"""Session cookies for the browser and bearer tokens for API clients."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.models import User
from app.schemas.auth import LoginInput, LoginResponse, UserResponse
from app.services.auth import authenticate, require_same_origin, require_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(data: LoginInput, request: Request, response: Response) -> LoginResponse:
    require_same_origin(request)
    settings = request.app.state.settings
    result = authenticate(request.app.state.session_factory, data, settings)
    options = {"secure": settings.app_env == "production", "samesite": "lax", "path": "/"}
    maximum_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        "access_token", result.access_token, httponly=True, max_age=maximum_age, **options
    )
    response.set_cookie(
        "csrf_token", result.csrf_token, httponly=False, max_age=maximum_age, **options
    )
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(require_user)], response: Response) -> UserResponse:
    response.headers["Cache-Control"] = "no-store"
    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(
    _user: Annotated[User, Depends(require_user)], request: Request, response: Response
) -> dict[str, bool]:
    options = {
        "secure": request.app.state.settings.app_env == "production",
        "samesite": "lax",
        "path": "/",
    }
    response.delete_cookie("access_token", httponly=True, **options)
    response.delete_cookie("csrf_token", httponly=False, **options)
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
