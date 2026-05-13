from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_token(
    *,
    subject: str,
    user_id: int,
    employee_id: int | None,
    roles: list[str],
    expires_delta: timedelta,
    token_type: str,
) -> str:
    issued_at = utc_now()
    payload: dict[str, Any] = {
        "sub": subject,
        "user_id": user_id,
        "employee_id": employee_id,
        "roles": roles,
        "token_type": token_type,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + expires_delta).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, subject: str, user_id: int, employee_id: int | None, roles: list[str]) -> str:
    return create_token(
        subject=subject,
        user_id=user_id,
        employee_id=employee_id,
        roles=roles,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(*, subject: str, user_id: int, employee_id: int | None, roles: list[str]) -> str:
    return create_token(
        subject=subject,
        user_id=user_id,
        employee_id=employee_id,
        roles=roles,
        expires_delta=timedelta(minutes=settings.refresh_token_expire_minutes),
        token_type="refresh",
    )


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc
