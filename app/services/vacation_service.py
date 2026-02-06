from app.db.session import get_db
from app.schemas.vacationBaseModel import VacationBaseModel,UpdateVacationBaseModel
from app.models.vacation import Vacation
from sqlalchemy.orm import Session
from fastapi import Depends
from app.exceptions.db_exceptions.noVacationFound import NoVacationFound
from sqlalchemy import select

def get_all_vacations(db:Session=Depends(get_db)):

    return db.execute(
        select(Vacation)
    ).mappings().all()

def get_all_vacations(id:int,db:Session=Depends(get_db)):

    return db.execute(
        select(Vacation)
        .where(Vacation.employee_id==id)
    ).mappings().all()

def get_emp_all_vacations(emp_id:int,db:Session=Depends(get_db)):

    return db.execute(
        select(Vacation)
        .where(Vacation.employee_id==emp_id)
    ).mappings().all()

    
def add_vacation(vac:VacationBaseModel,db:Session=Depends(get_db)):
    try:
        new_vac = Vacation(employee_id=vac.employee_id,start_date=vac.start_date,end_date=vac.end_date,vacation_type=vac.vacation_type,vacation_status=vac.vacation_status)
        db.add(new_vac)
        db.commit()
        db.refresh(new_vac)
    except Exception as e:
        raise e
    
def update_vacation(updated_vac:UpdateVacationBaseModel,db:Session=Depends(get_db)):
    try:
        vac = db.get(Vacation,vac.id)
        if vac:
            vac.start_date = updated_vac.start_date
            vac.end_date = updated_vac.end_date
            vac.vacation_type = updated_vac.vacation_type
            vac.vacation_status = updated_vac.vacation_status
            db.commit()
            db.refresh(vac)
        else:
            raise NoVacationFound("no vacation found with this id "+vac.id)
    except Exception as e:
        raise e

def delete_vacation(id:int,db:Session=Depends(get_db)):
    try:
        vac = db.get(Vacation,id)
        if not vac :
            raise ValueError("vacation not found")
        db.delete(vac)
        db.commit()
        db.refresh(vac)
    except Exception as e:
        raise e
    