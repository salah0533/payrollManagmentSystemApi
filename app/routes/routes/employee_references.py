from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_permissions
from app.models.auth import User
from app.schemas.user import EmployeeReferenceCreateRequest
from app.services.employee_reference_service import (
    create_department,
    create_position,
    list_departments,
    list_positions,
)


router = APIRouter()


@router.get("/departments")
def get_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.read")),
):
    return api_success(list_departments(db))


@router.post("/departments")
def add_department(
    payload: EmployeeReferenceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.create")),
):
    return api_success(create_department(payload, db), status_code=201)


@router.get("/positions")
def get_positions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.read")),
):
    return api_success(list_positions(db))


@router.post("/positions")
def add_position(
    payload: EmployeeReferenceCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.create")),
):
    return api_success(create_position(payload, db), status_code=201)
