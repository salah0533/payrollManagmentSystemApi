from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_authenticated_user
from app.models.auth import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LogoutResponse, RefreshTokenRequest, UpdateLanguageRequest
from app.services.auth_service import change_password, get_me, login, refresh_access_token, update_language


router = APIRouter()


@router.post("/login")
def login_user(payload: LoginRequest, db: Session = Depends(get_db)):
    token = login(payload.identifier, payload.password, db)
    return api_success(token)


@router.post("/refresh")
def refresh_user_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    token = refresh_access_token(payload.refresh_token, db)
    return api_success(token)


@router.get("/me")
def auth_me(current_user: User = Depends(get_current_user)):
    return api_success(get_me(current_user))


@router.patch("/language")
def auth_update_language(
    payload: UpdateLanguageRequest,
    current_user: User = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
):
    return api_success(update_language(current_user, payload, db))


@router.post("/change-password")
def auth_change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    change_password(current_user, payload, db)
    return api_success(message="Password changed successfully")


@router.post("/logout")
def auth_logout(current_user: User = Depends(get_current_user)):
    response = LogoutResponse(message="Logout is stateless; discard the access and refresh tokens on the client.")
    return api_success(response)
