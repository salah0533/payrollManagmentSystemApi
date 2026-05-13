from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies.auth import require_permissions
from app.db.session import get_db
from app.models.auth import User
from app.schemas.user import EmployeeCreateRequest, EmployeeUpdateRequest
from app.services.employee_service import add_employee, delete_employee, get_employee, get_employees, update_employee


router = APIRouter()

@router.get("/")
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.read")),
):
    return {"message":"","data":get_employees(db),"status":True}

@router.get("/{id}")
def get_employee_by_id(
    id:int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.read")),
):
    return {"message":"","data":get_employee(id,db),"status":True}

@router.post("/")
def create_employee(
    emp: EmployeeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.create")),
):
    return {"message":"","data":add_employee(emp,db, actor=current_user),"status":True}

@router.delete("/{id}")
def delete_employee_by_id(
    id:int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.delete")),
):
    delete_employee(id,db, actor=current_user)
    return {"message":"","data":None,"status":True} 

@router.put("/{id}")
def update_employee_by_id(
    id: int,
    emp: EmployeeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("employees.update")),
):
    return {"message":"","data":update_employee(id,emp,db, actor=current_user),"status":True} 

