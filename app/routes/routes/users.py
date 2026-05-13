from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

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
    list_users,
    remove_role,
    reset_password,
    serialize_user,
    update_user,
)


router = APIRouter()


@router.get("/")
def get_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return {"message": "", "data": list_users(db), "status": True}


@router.get("/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return {"message": "", "data": serialize_user(get_user_or_404(user_id, db)), "status": True}


@router.post("/")
def create_new_user(payload: UserCreateRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return {"message": "", "data": create_user(payload, db, actor=current_user), "status": True}


@router.put("/{user_id}")
def update_existing_user(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return {"message": "", "data": update_user(user_id, payload, db, actor=current_user), "status": True}


@router.post("/{user_id}/activate")
def activate_existing_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return {"message": "", "data": activate_user(user_id, db, actor=current_user), "status": True}


@router.post("/{user_id}/deactivate")
def deactivate_existing_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return {"message": "", "data": deactivate_user(user_id, db, actor=current_user), "status": True}


@router.post("/{user_id}/roles")
def assign_user_roles(
    user_id: int,
    payload: UserRoleAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return {"message": "", "data": assign_roles(user_id, payload.role_ids, db, actor=current_user), "status": True}


@router.delete("/{user_id}/roles/{role_id}")
def delete_user_role(
    user_id: int,
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return {"message": "", "data": remove_role(user_id, role_id, db, actor=current_user), "status": True}


@router.post("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: UserResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return {"message": "", "data": reset_password(user_id, payload, db, actor=current_user), "status": True}

