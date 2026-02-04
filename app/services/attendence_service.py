from fastapi import Depends
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.session import get_db
from sqlalchemy.exc import SQLAlchemyError
from app.models.settings import Settings
from app.models.employees import Employees
from app.models.attendence import Attendence
from app.models.vacation import Vacation
from app.schemas.attendenceBaseModel import AttendenceBaseModel
from app.exceptions.db_exceptions.noEntryTimeFound import NoEntryTimeFound
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from datetime import datetime,time,timedelta,date
from enum import IntEnum


class AttendanceType(IntEnum):
    Presnt = 0
    LATE = 1
    Absent=2
    OVERTIME = 3
    PAID_VACATION = 4
    Not_PAID_VACATION = 5
    Sick_Leave = 6


def get_attendence(emp_id,date,db:Session=Depends(get_db)):

    att = db.scalars(
        select(Attendence)
        .where(
            Attendence.employee_id==emp_id,
            Attendence.date==date
        )
    ).one_or_none()
    return att



def get_attendance_type(
    emp_id: int,
    entry_time: time,
    exit_time: time | None,
    attendence_type:int,
    db: Session = Depends(get_db)
):
    
    if attendence_type in [AttendanceType.Absent,AttendanceType.Sick_Leave] :
        return attendence_type
    
    emp = db.get(Employees, emp_id)
    if not emp:
        raise EmployeeNotFound("employee not found")

    today = date.today()

    vacation = db.execute(
        select(Vacation)
        .where(Vacation.employee_id == emp_id)
        .order_by(Vacation.end_date.desc())
        .limit(1)
    ).scalar_one_or_none()

    if vacation and vacation.is_paid:
        if vacation.start_date <= today <= vacation.end_date:
            return AttendanceType.PAID_VACATION  # PAID_VACATION

    if exit_time:
        entry_dt = datetime.combine(today, entry_time)
        exit_dt = datetime.combine(today, exit_time)

        worked_time = exit_dt - entry_dt
        expected_work  = timedelta(hours=emp.daily_work_hours)
        diff = worked_time - expected_work  # timedelta

        if diff > emp.min_extraTime:
            return AttendanceType.OVERTIME  # OVERTIME

        if diff < timedelta(0) and abs(diff) > emp.allowed_late:
            return AttendanceType.LATE  # LATE

    return AttendanceType.Presnt  # Presnt


def update_attendence(att:Attendence,data:AttendenceBaseModel,db:Session=Depends(get_db)):
        
        for key,val in data.model_dump():
            setattr(Attendence,key,val)

        db.commit()
        db.refresh(att)

def add_new_attendence(data:AttendenceBaseModel,db:Session=Depends(get_db)):

    new_att = Attendence(employee_id=data.employee_id,entry_time=data.entry_time,exit_time=data.exit_time,date=date,attendence_type=data.attendence_type)
    db.add(new_att)
    db.commit()
    db.refresh(new_att)

def get_employee_attendence(id:int,start:date,end:date,db:Session=Depends(get_db)):
    return db.scalars(
        select(Attendence).where(
            Attendence.employee_id==id,
            Attendence.date >= start,
            Attendence.date <= end )
    ).all()

def get_employees_attendence(d:date,db:Session=Depends(get_db)):
    return db.scalars(
        select(Attendence).where(
            Attendence.date==d )
    ).all()


def delete_attendence(id:int,db:Session=Depends(get_db)):
    att = db.get(Attendence,id)
    if att:
        db.delete(att)
        db.commit()
        db.refresh(att)



