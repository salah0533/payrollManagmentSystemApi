from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.models.employees import Employees
from app.models.attendence import Attendence
from app.models.vacation import Vacation
from app.services.policy_service import get_employee_schedule, get_or_create_payroll_policy
from app.services.settings import get_settings
from app.schemas.attendenceBaseModel import AttendenceBaseModel
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from app.models.types.attendenceTypes import AttendanceType
from datetime import datetime,time,timedelta,date



def get_attendence(emp_id,date,db:Session):

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
    attendence_type:int | None,
    att_date:date,
    db: Session
):
    
    if attendence_type in [AttendanceType.Absent,AttendanceType.Sick_Leave] :
        return attendence_type
    
    emp = db.get(Employees, emp_id)
    if not emp:
        raise EmployeeNotFound("employee not found")

    vacation = db.execute(
        select(Vacation)
        .where(
            Vacation.employee_id == emp_id,
            Vacation.start_date <= att_date,
            Vacation.end_date >= att_date
        )
    ).scalar_one_or_none()

    if vacation:
        if vacation.is_paid and vacation.vacation_status==1:
            return AttendanceType.PAID_VACATION
        else:
            return AttendanceType.Not_PAID_VACATION

    today = date.today()
    if exit_time:
        entry_dt = datetime.combine(today, entry_time)
        exit_dt = datetime.combine(today, exit_time)

        worked_time = exit_dt - entry_dt
        schedule = get_employee_schedule(emp_id, att_date, db)
        policy = get_or_create_payroll_policy(db)
        scheduled_minutes = max(
            0,
            int((datetime.combine(today, schedule.end_time) - datetime.combine(today, schedule.start_time)).total_seconds() // 60)
            - int(schedule.break_minutes or 0),
        )
        expected_work  = timedelta(minutes=scheduled_minutes)
        minimum_overtime = timedelta(minutes=max(0, int(policy.minimum_overtime_minutes or 0)))
        allowed_late = timedelta(minutes=max(0, int(policy.allowed_late_minutes or 0)))
        
        if worked_time > expected_work + minimum_overtime:
            return AttendanceType.OVERTIME  # OVERTIME

        if worked_time < expected_work - allowed_late:
            return AttendanceType.LATE  # LATE

    return AttendanceType.Presnt  # Presnt


def update_attendence(att:Attendence,data:AttendenceBaseModel,db:Session):
        
        for key,val in data.model_dump(exclude_unset=True).items():
            setattr(att,key,val)

        db.commit()
        db.refresh(att)

def add_new_attendence(data:AttendenceBaseModel,db:Session):

    new_att = Attendence(
        employee_id=data.employee_id,
        entry_time=data.entry_time,
        exit_time=data.exit_time,
        date=data.date,
        attendence_type=data.attendence_type or  AttendanceType.Presnt,
    )
    db.add(new_att)
    db.commit()
    db.refresh(new_att)


def mark_all_emp_present(db: Session):
    emps = db.scalars(
        select(Employees.id)
        .where(Employees.is_active.is_(True))
    ).all()

    if not emps:
        return {"updated": 0, "created": 0}

    today = date.today()

    # Get today's attendance only (IMPORTANT ⚠️)
    att = db.scalars(
        select(Attendence)
        .where(
            Attendence.employee_id.in_(emps),
            Attendence.date == today
        )
    ).all()

    sett = get_settings(db)

    # Update existing records
    for a in att:
        a.attendence_type = AttendanceType.Presnt
        if a.employee_id in emps:
            emps.remove(a.employee_id)

    # Create missing records
    atts = []
    for emp in emps:
        atts.append(
            Attendence(
                employee_id=emp,  # ✅ FIXED
                entry_time=sett.entry_time,
                exit_time=sett.exit_time,
                date=today,
                attendence_type=AttendanceType.Presnt,
            )
        )

    db.add_all(atts)   # ✅ IMPORTANT
    db.commit()

    return {"updated": len(att), "created": len(atts)}

def get_employee_attendence_by_date(id:int,start:date,end:date,db:Session):
    return db.scalars(
        select(Attendence).where(
            Attendence.employee_id==id,
            Attendence.date >= start,
            Attendence.date <= end )
    ).all()

def get_attendence_by_date(start:date,end:date,db:Session):
    return db.scalars(
        select(Attendence).where(
            Attendence.date >= start,
            Attendence.date <= end )
    ).all()

def get_employee_attendence(id:int,db:Session):
    return db.scalars(
        select(Attendence).where(
            Attendence.employee_id==id)
    ).all()

def get_employees_attendence(d:date,db:Session):
    return db.scalars(
        select(Attendence).where(
            Attendence.date==d )
    ).all()


def delete_attendence(id:int,db:Session):
    att = db.get(Attendence,id)
    if att:
        db.delete(att)
        db.commit()



