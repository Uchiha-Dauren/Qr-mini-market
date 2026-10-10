"""Validated credentials and deliberately small public user contracts."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.core.enums import UserRole


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: SecretStr = Field(min_length=1, max_length=128, repr=False)


class CreateUserInput(LoginInput):
    password: SecretStr = Field(min_length=12, max_length=128, repr=False)
    role: UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    public_id: UUID
    username: str
    role: UserRole


class LoginResponse(BaseModel):
    user: UserResponse
    access_token: str = Field(repr=False)
    csrf_token: str = Field(repr=False)
