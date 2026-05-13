from app.schemas.vacationBaseModel import VacationBaseModel,UpdateVacationBaseModel
from app.models.vacation import Vacation
from sqlalchemy.orm import Session
from app.exceptions.db_exceptions.noVacationFound import NoVacationFound
from sqlalchemy import select,extract
from datetime import date
from app.models.types.vacationStatus import VacationStatuses
from app.services.payroll_calculation_service import sync_vacation_with_payroll

def get_all_vacations(year:int,db:Session):
    return db.scalars(
        select(Vacation)
        .where(extract("year",Vacation.start_date)==year)
    ).all()

def get_all_current_vacations(db: Session):
    today = date.today()

    return db.scalars(
        select(Vacation)
        .where(
            Vacation.start_date <= today,
            Vacation.end_date >= today
        )
    ).all()

def get_employee_vacations(id:int,start,end,db:Session):

    return db.scalars(
        select(Vacation)
        .where(Vacation.employee_id==id,
               Vacation.start_date >= start,
               Vacation.end_date <= end
               )
    ).all()

def overlab_check(id:int,start,end,db:Session):
    return db.scalars(
    select(Vacation)
    .where(
        Vacation.employee_id == id,
        Vacation.start_date <= end,
        Vacation.end_date >= start
    )).all()

def get_emp_all_vacations(emp_id:int,db:Session):

    return db.scalars(
        select(Vacation)
        .where(Vacation.employee_id==emp_id)
    ).all()

    
def add_vacation(vac:VacationBaseModel,db:Session):
    new_vac = Vacation(
        employee_id=vac.employee_id,
        start_date=vac.start_date,
        end_date=vac.end_date,
        vacation_type=vac.vacation_type,
        vacation_status=vac.vacation_status,
        is_paid=vac.is_paid,
    )
    db.add(new_vac)
    db.flush()
    if vac.vacation_status == int(VacationStatuses.approved):
        sync_vacation_with_payroll(vac.employee_id, vac.start_date, vac.end_date, db, reason="vacation_approved")
    db.commit()
    db.refresh(new_vac)
    
def update_vacation(updated_vac:UpdateVacationBaseModel,db:Session):
    vac = db.get(Vacation,updated_vac.id)
    if not vac:
        raise NoVacationFound(f"No vacation found with this id {updated_vac.id}")
    old_start = vac.start_date
    old_end = vac.end_date
    old_status = vac.vacation_status

    for key,val in updated_vac.model_dump(exclude_unset=True).items():
        if val is None or key == "id":
            continue
        setattr(vac,key,val)
    db.flush()
    if vac.vacation_status == int(VacationStatuses.approved):
        sync_vacation_with_payroll(vac.employee_id, vac.start_date, vac.end_date, db, reason="vacation_approved")
    elif old_status == int(VacationStatuses.approved):
        sync_vacation_with_payroll(vac.employee_id, old_start, old_end, db, reason="vacation_rejected")
    db.commit()
    db.refresh(vac)

def delete_vacation(id:int,db:Session):
    vac = db.get(Vacation,id)
    if not vac :
        raise NoVacationFound()
    employee_id = vac.employee_id
    start_date = vac.start_date
    end_date = vac.end_date
    db.delete(vac)
    db.flush()
    sync_vacation_with_payroll(employee_id, start_date, end_date, db, reason="vacation_rejected")
    db.commit()
    
    
