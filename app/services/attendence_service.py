from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.session import get_db
from sqlalchemy.exc import SQLAlchemyError
from app.models.settings import Settings
from app.models.employees import Employees
from app.models.attendence import Attendence
from app.models.vacation import Vacation
from app.exceptions.db_exceptions.noEntryTimeFound import NoEntryTimeFound
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from datetime import datetime


def add_new_attendence(emp_id,entry_time,exit_time,date,type_id,db:Session=Depends(get_db)):
    try:
        new_att = Attendence(employee_id=emp_id,entry_time=entry_time,exit_time=exit_time,date=date,attendence_type=type_id)
        db.add(new_att)
        db.commit()
        db.refresh(new_att)

    except SQLAlchemyError as e:
        raise e
    
def update_exit_attendence(att,exit_time,db:Session=Depends(get_db)):
    try:
        att.exit_time = exit_time
        db.commit()
        db.refresh(att)
    except Exception as e:
        raise e

def update_entry_attendence(att,entry_time,type_id,db:Session=Depends(get_db)):
    try:
        att.entry_time = entry_time
        att.attendence_type = type_id
        db.commit()
        db.refresh(att)
    except Exception as e:
        raise e
    
def add_entry_attendence(emp_id,entry_time,date,type_id:int,db:Session=Depends(get_db)):
    try:
        new_att = Attendence(employee_id=emp_id,entry_time=entry_time,date=date,attendence_type=type_id)
        db.add(new_att)
        db.commit()
        db.refresh(new_att)

    except SQLAlchemyError as e:
        raise e

def auto_attendence(date,emp_id,standar_entry,standar_exist,db:Session=Depends(get_db)):
    try:
        emp_att = db.scalars(
            select(Attendence).where(
                Attendence.id==emp_id,
                Attendence.date==date
            )
        ).one_or_none()
        if not emp_att:
            new_att = Attendence(employee_id=emp_id,entry_time=standar_entry,exit_time=standar_exist,date=date,attendence_type=1)
            db.add(new_att)
            db.commit()
            db.refresh(new_att)

    except SQLAlchemyError as e:
        raise e
    
def get_attendence_type(emp_id:int,db:Session=Depends(get_db)):
    try:
        emp = db.get(Employees,emp_id)
        if not emp:
            raise EmployeeNotFound("employee not found")

        vacation = db.execute(
            select(Vacation)
                .where(Vacation.employee_id==emp_id)
                .order_by(Vacation.end_date.desc())
                .limit(1)
        ).scalar_one_or_none()
        
        if vacation:
            if vacation.end_date <= datetime.now().date():
                return 2
        elif emp.auto_attendence:
            return 1
        else:
            return 0
        
    except Exception as e:
        raise e

def get_attendence(emp_id,date,db:Session=Depends(get_db)):
    try:
        att = db.scalars(
            select(Attendence)
            .where(
                Attendence.employee_id==emp_id,
                Attendence.date==date
            )
        ).one_or_none()
        return att
    except Exception as e:
        raise e