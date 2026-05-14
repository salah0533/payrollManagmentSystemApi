from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_admin
from app.models.auth import User
from app.schemas.user import UserCreateRequest, UserResetPasswordRequest, UserRoleAssignRequest, UserUpdateRequest
from app.services.user_service import (
    activate_user,
    assign_roles,
    create_user,
    deactivate_user,
    get_user_or_404,
    list_employees_without_accounts,
    list_roles,
    list_users,
    remove_role,
    reset_password,
    serialize_user,
    update_user,
)


router = APIRouter()


@router.get("/")
def get_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return api_success(list_users(db))


@router.get("/roles")
def get_roles(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return api_success(list_roles(db))


@router.get("/available-employees")
def get_available_employees(
    include_user_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return api_success(list_employees_without_accounts(db, include_user_id=include_user_id))


@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return api_success(serialize_user(get_user_or_404(user_id, db)))


@router.post("/")
def create_new_user(payload: UserCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return api_success(create_user(payload, db, actor=current_user), status_code=201)


@router.put("/{user_id}")
def update_existing_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return api_success(update_user(user_id, payload, db, actor=current_user))


@router.post("/{user_id}/activate")
def activate_existing_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return api_success(activate_user(user_id, db, actor=current_user))


@router.post("/{user_id}/deactivate")
def deactivate_existing_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return api_success(deactivate_user(user_id, db, actor=current_user))


@router.post("/{user_id}/roles")
def assign_user_roles(
    user_id: int,
    payload: UserRoleAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return api_success(assign_roles(user_id, payload.role_ids, db, actor=current_user))


@router.delete("/{user_id}/roles/{role_id}")
def delete_user_role(
    user_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return api_success(remove_role(user_id, role_id, db, actor=current_user))


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: UserResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return api_success(reset_password(user_id, payload, db, actor=current_user))
