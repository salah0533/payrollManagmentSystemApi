from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import decode_token
from app.db.session import get_db
from app.exceptions.base_exception import ForbiddenException, UnauthorizedException
from app.models.auth import Permission, Role, RolePermission, User, UserRole


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
PASSWORD_CHANGE_ALLOWED_PATHS = {"/auth/me", "/auth/change-password", "/auth/logout", "/auth/language"}


def _load_user(user_id: int, db: Session) -> User | None:
    return db.scalar(
        select(User)
        .options(
            selectinload(User.employee),
            selectinload(User.user_roles)
            .selectinload(UserRole.role)
            .selectinload(Role.role_permissions)
            .selectinload(RolePermission.permission),
        )
        .where(User.id == user_id, User.deleted_at.is_(None))
    )


def _forbidden(detail: str) -> ForbiddenException:
    return ForbiddenException(detail)


def _ensure_password_change_allowed(user: User, request: Request) -> None:
    if not user.must_change_password:
        return
    if request.url.path in PASSWORD_CHANGE_ALLOWED_PATHS:
        return
    raise _forbidden("Password change required before accessing this resource")


def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = UnauthorizedException(
        "Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise credentials_error from exc

    if payload.get("token_type") != "access":
        raise credentials_error

    user_id = payload.get("user_id")
    if not user_id:
        raise credentials_error

    user = _load_user(int(user_id), db)
    if not user:
        raise credentials_error
    if not user.is_active:
        raise _forbidden("Inactive users cannot access this resource")

    request.state.current_user = user
    return user


def require_authenticated_user(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    _ensure_password_change_allowed(current_user, request)
    return current_user


def require_roles(*role_codes: str) -> Callable:
    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        _ensure_password_change_allowed(current_user, request)
        user_roles = set(current_user.active_role_codes)
        if "admin" in user_roles:
            return current_user
        if not user_roles.intersection(role_codes):
            raise _forbidden("You do not have the required role")
        return current_user

    return dependency


def require_permissions(*permission_codes: str) -> Callable:
    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        _ensure_password_change_allowed(current_user, request)
        user_roles = set(current_user.active_role_codes)
        if "admin" in user_roles:
            return current_user
        permissions = set(current_user.active_permission_codes)
        missing = [code for code in permission_codes if code not in permissions]
        if missing:
            raise _forbidden(f"Missing required permission(s): {', '.join(missing)}")
        return current_user

    return dependency


def require_admin(
    current_user: User = Depends(require_roles("admin")),
) -> User:
    return current_user


def require_hr_or_admin(
    current_user: User = Depends(require_roles("hr", "admin")),
) -> User:
    return current_user


def require_self_or_permission(permission_code: str, *, employee_param: str = "employee_id") -> Callable:
    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
    ) -> User:
        _ensure_password_change_allowed(current_user, request)
        if "admin" in set(current_user.active_role_codes):
            return current_user
        permissions = set(current_user.active_permission_codes)
        if permission_code in permissions:
            return current_user
        route_value = request.path_params.get(employee_param)
        if route_value is None or current_user.employee_id is None or int(route_value) != int(current_user.employee_id):
            raise _forbidden("You are not allowed to access another employee's data")
        return current_user

    return dependency
