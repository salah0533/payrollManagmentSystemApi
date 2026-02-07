from app.schemas.vacationBaseModel import VacationBaseModel,UpdateVacationBaseModel
from app.models.vacation import Vacation
from sqlalchemy.orm import Session
from app.exceptions.db_exceptions.noVacationFound import NoVacationFound
from sqlalchemy import select
from datetime import date

def get_all_vacations(db:Session):
    today = date.today()
    return db.scalars(
        select(Vacation)
        .where(Vacation.end_date >= today)
    ).all()

def get_employee_vacations(id:int,db:Session):

    return db.scalars(
        select(Vacation)
        .where(Vacation.employee_id==id)
    ).all()

def get_emp_all_vacations(emp_id:int,db:Session):

    return db.scalars(
        select(Vacation)
        .where(Vacation.employee_id==emp_id)
    ).all()

    
def add_vacation(vac:VacationBaseModel,db:Session):
    try:
        new_vac = Vacation(
            employee_id=vac.employee_id,
            start_date=vac.start_date,
            end_date=vac.end_date,
            vacation_type=vac.vacation_type,
            vacation_status=vac.vacation_status,
            is_paid=vac.is_paid,
        )
        db.add(new_vac)
        db.commit()
        db.refresh(new_vac)
    except Exception as e:
        raise e
    
def update_vacation(updated_vac:UpdateVacationBaseModel,db:Session):
    try:
        vac = db.get(Vacation,updated_vac.id)
        if not vac:
            raise NoVacationFound("no vacation found with this id "+str(updated_vac.id))

        for key,val in updated_vac.model_dump(exclude_unset=True).items():
            if val is None or key == "id":
                continue
            setattr(vac,key,val)
        db.commit()
        db.refresh(vac)
    except Exception as e:
        raise e

def delete_vacation(id:int,db:Session):
    try:
        vac = db.get(Vacation,id)
        if not vac :
            raise NoVacationFound("vacation not found")
        db.delete(vac)
        db.commit()
    except Exception as e:
        raise e
    
    