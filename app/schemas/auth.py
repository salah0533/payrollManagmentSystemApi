from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.localization import LanguageCode


class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=255)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip()


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=255)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, value: str) -> str:
        if value.lower() == "password":
            raise ValueError("new_password is too weak")
        if value.strip() != value:
            raise ValueError("new_password may not start or end with whitespace")
        return value


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    refresh_expires_in_seconds: int
    must_change_password: bool


class LogoutResponse(BaseModel):
    message: str


class AuthMeEmployee(BaseModel):
    id: int
    first_name: str
    last_name: str
    full_name: str
    email: Optional[EmailStr] = None
    position: Optional[str] = None
    status: str


class AuthMeResponse(BaseModel):
    id: int
    employee_id: int | None
    username: str
    email: Optional[EmailStr] = None
    language: LanguageCode
    is_active: bool
    must_change_password: bool
    last_login_at: Optional[datetime] = None
    roles: list[str]
    permissions: list[str]
    employee: Optional[AuthMeEmployee] = None


class UpdateLanguageRequest(BaseModel):
    language: LanguageCode
