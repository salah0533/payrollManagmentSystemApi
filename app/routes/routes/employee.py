from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.dependencies.auth import require_permissions
from app.db.session import get_db
from app.models.auth import User
from app.schemas.user import EmployeeCreateRequest, EmployeeUpdateRequest
from app.services.employee_service import (
    add_employee,
    delete_employee,
    get_employee,
    get_employee_compensation_history,
    get_employees,
    update_employee,
)


router = APIRouter()

@router.get("/")
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.read")),
):
    return api_success(get_employees(db))

@router.get("/{id}")
def get_employee_by_id(
    id:int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.read")),
):
    return api_success(get_employee(id,db))


@router.get("/{id}/compensation-history")
def get_employee_compensation_timeline(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.read")),
):
    return api_success(get_employee_compensation_history(id, db))

@router.post("/")
def create_employee(
    emp: EmployeeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.create")),
):
    return api_success(add_employee(emp,db, actor=current_user), status_code=201)

@router.delete("/{id}")
def delete_employee_by_id(
    id:int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.delete")),
):
    delete_employee(id,db, actor=current_user)
    return api_success()

@router.put("/{id}")
def update_employee_by_id(
    id: int,
    emp: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.update")),
):
    return api_success(update_employee(id,emp,db, actor=current_user))

