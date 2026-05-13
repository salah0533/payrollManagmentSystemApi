from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LogoutResponse, RefreshTokenRequest
from app.services.auth_service import change_password, get_me, login, refresh_access_token


router = APIRouter()


@router.post("/login")
def login_user(payload: LoginRequest, db: Session = Depends(get_db)):
    token = login(payload.identifier, payload.password, db)
    return {"message": "", "data": token, "status": True}


@router.post("/refresh")
def refresh_user_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    token = refresh_access_token(payload.refresh_token, db)
    return {"message": "", "data": token, "status": True}


@router.get("/me")
def auth_me(current_user: User = Depends(get_current_user)):
    return {"message": "", "data": get_me(current_user), "status": True}


@router.post("/change-password")
def auth_change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    change_password(current_user, payload, db)
    return {"message": "Password changed successfully", "data": None, "status": True}


@router.post("/logout")
def auth_logout(current_user: User = Depends(get_current_user)):
    response = LogoutResponse(message="Logout is stateless; discard the access and refresh tokens on the client.")
    return {"message": "", "data": response, "status": True}

