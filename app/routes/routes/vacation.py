from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_hr_or_admin, require_permissions, require_self_or_permission
from app.exceptions.base_exception import ConflictException
from app.models.auth import User
from app.services.vacation_service import overlab_check,get_all_current_vacations,get_all_vacations,get_employee_vacations,add_bulk_vacations,add_vacation,update_vacation,delete_vacation
from app.schemas.vacationBaseModel import BulkVacationCreateModel, VacationBaseModel,UpdateVacationBaseModel
from datetime import date
router = APIRouter()

@router.get("/current")
def get_current_vacations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("vacations.read_all")),
):
    return api_success(get_all_current_vacations(db))

@router.get("/{id}/{start}/{end}")
def get_emp_vacations(
    id:int,
    start:date,
    end:date,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_permission("vacations.read_all", employee_param="id")),
):
    return api_success(get_employee_vacations(id,start,end,db))

@router.put("/")
def add_vacation_by_id(
    vac:VacationBaseModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    if overlab_check(vac.employee_id,vac.start_date,vac.end_date,db) != []:
        raise ConflictException("Vacation already exists in these dates", code="vacation_overlap", message_key="errors.vacation_overlap")
    add_vacation(vac,db, actor=current_user)
    return api_success(status_code=201)


@router.put("/bulk")
def add_bulk_vacation_records(
    payload: BulkVacationCreateModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    for employee_id in payload.employee_ids:
        if overlab_check(employee_id, payload.start_date, payload.end_date, db) != []:
            raise ConflictException("Vacation already exists in these dates", code="vacation_overlap", message_key="errors.vacation_overlap")
    vacations = add_bulk_vacations(payload, db, actor=current_user)
    return api_success(vacations, status_code=201)


@router.get("/{year}")
def get_vacations(
    year:int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("vacations.read_all")),
):
    return api_success(get_all_vacations(year,db))

@router.post("/")
def update_vacation_by_id(
    vac:UpdateVacationBaseModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    update_vacation(vac,db, actor=current_user)
    return api_success()

@router.delete("/{id}")
def delete_vac(
    id:int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    delete_vacation(id,db)
    return api_success()
