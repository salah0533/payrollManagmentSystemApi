from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.attendence import Attendence
from app.models.types.attendenceTypes import AttendanceType
from app.services.vacation_service import get_emp_all_vacations
from app.utility.helper import hours_between , dates_between_skip_friday
from app.models.employees import Employees
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from datetime import datetime,date
from dateutil.relativedelta import relativedelta

def att_stat(emp_id,start,end,db:Session):
    emp = db.get(Employees,emp_id)
    if not emp :
        raise EmployeeNotFound("employee not found")
    
    salary_type = emp.salary_type
    diff = relativedelta(end,start)
    att = {
        "month_price":emp.monthly_price,
        "day_price":emp.day_price,
        "hour_price":emp.hour_price,
        "salaryType":emp.salary_type,
        "duration":{
            "months":diff.months,
            "days":diff.days,
        },"attendance":{
            "days":0,
            "hours":0
        },"present":0,
        "absent":0,
        "late":0,
        "overtime":0,
        "paid_vacation":0,
        "not_paid_vacation":0,
        "not_selected":0,
    }


    res = db.scalars(
        select(Attendence)
            .where(
                Attendence.employee_id == emp_id,
                Attendence.date <= end,
                Attendence.date >= start 
            )
        ).all()
    expected_work = float(emp.daily_work_hours)
    all_days = dates_between_skip_friday(start,end)
    all_vac = get_emp_all_vacations(emp_id,db)
    for a in res:
        b = True
        if a.date in all_days:

            if a.attendence_type == AttendanceType.Presnt:
                att["present"] +=1
                if salary_type==1:
                    att["attendance"]["days"]  +=1
                elif salary_type==2:
                    entry_time = datetime.combine(date.today(),a.entry_time)
                    exit_time = datetime.combine(date.today(),a.exit_time)
                    att["attendance"]["hours"] +=  (exit_time - entry_time).total_seconds() / 3600

            elif a.attendence_type == AttendanceType.Absent:
                att["absent"] +=1
            elif a.attendence_type == AttendanceType.LATE:
                att["late"] += expected_work -  hours_between(a.entry_time , a.exit_time)
                if salary_type==1:
                    att["attendance"]["days"]  +=1

            elif a.attendence_type == AttendanceType.OVERTIME:
                att["overtime"] += hours_between(a.entry_time , a.exit_time) - expected_work
                if salary_type==1:
                    att["attendance"]["days"]  +=1
            elif a.attendence_type == AttendanceType.PAID_VACATION:
                att["paid_vacation"] +=1
            elif a.attendence_type == AttendanceType.Not_PAID_VACATION:
                att["not_paid_vacation"] +=1
            all_days.remove(a.date)

        else:
            for vac in all_vac:
                if  a.date >= vac.start_date and a.date <= vac.end_date:
                    if vac.is_paid:
                        att["paid_vacation"] +=1
                        b = False
                    else:
                        att["not_paid_vacation"] +=1
                        b = False
            if b:
                att["not_selected"] +=1
    return att

