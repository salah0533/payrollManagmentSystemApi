from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token, get_password_hash, utc_now, verify_password
from app.models.auth import User
from app.schemas.auth import ChangePasswordRequest, TokenResponse
from app.services.audit_service import save_audit_log
from app.services.user_service import get_user_by_identifier, get_user_or_404, serialize_auth_me


def authenticate_user(identifier: str, password: str, db: Session) -> User:
    user = get_user_by_identifier(identifier, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive users cannot log in")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user


def build_token_response(user: User) -> TokenResponse:
    roles = user.active_role_codes
    subject = user.username
    access_token = create_access_token(subject=subject, user_id=user.id, employee_id=user.employee_id, roles=roles)
    refresh_token = create_refresh_token(subject=subject, user_id=user.id, employee_id=user.employee_id, roles=roles)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in_seconds=settings.access_token_expire_minutes * 60,
        refresh_expires_in_seconds=settings.refresh_token_expire_minutes * 60,
        must_change_password=user.must_change_password,
    )


def login(identifier: str, password: str, db: Session) -> TokenResponse:
    user = authenticate_user(identifier, password, db)
    user.last_login_at = utc_now()
    db.add(user)
    db.flush()
    save_audit_log(db, action="login", entity_type="User", entity_id=user.id, user_id=user.id)
    db.commit()
    db.refresh(user)
    return build_token_response(get_user_or_404(user.id, db))


def refresh_access_token(refresh_token: str, db: Session) -> TokenResponse:
    try:
        payload = decode_token(refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token") from exc
    if payload.get("token_type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = get_user_or_404(int(user_id), db)
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive users cannot refresh tokens")
    return build_token_response(user)


def change_password(current_user: User, payload: ChangePasswordRequest, db: Session) -> None:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.password_hash = get_password_hash(payload.new_password)
    current_user.must_change_password = False
    db.add(current_user)
    db.flush()
    save_audit_log(
        db,
        action="password_changed",
        entity_type="User",
        entity_id=current_user.id,
        user_id=current_user.id,
    )
    db.commit()


def get_me(current_user: User):
    return serialize_auth_me(current_user)
