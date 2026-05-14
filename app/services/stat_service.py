from sqlalchemy.orm import Session
from sqlalchemy import or_, select, func, extract
from app.models.attendence import Attendence
from app.models.types.attendenceTypes import AttendanceType
from app.services.vacation_service import get_all_current_vacations, get_emp_all_vacations
from app.utility.helper import hours_between , dates_between_skip_friday
from app.models.employees import Employees
from app.models.auth import Role, User, UserRole
from app.models.attendance_payroll import EmployeePayroll, PayrollPeriod
from app.models.payments import Payments
from app.models.types.vacationStatus import VacationStatuses
from app.models.vacation import Vacation
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from datetime import datetime,date
from dateutil.relativedelta import relativedelta
import calendar

def att_stat(emp_id,start,end,db:Session):
    emp = db.get(Employees,emp_id)
    if not emp :
        raise EmployeeNotFound("employee not found")
    salary_type = emp.salary_type
    diff = relativedelta(end,start)
    att = {
        "salary_type":emp.salary_type_tab.salary_type,
        "month_price":emp.monthly_price,
        "day_price":emp.day_price,
        "hour_price":emp.hour_price,
        "overtime_price":emp.extra_hours_price,
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
                if salary_type in [0,1]:
                    att["attendance"]["days"]  +=1
                elif salary_type==2:
                    entry_time = datetime.combine(date.today(),a.entry_time)
                    exit_time = datetime.combine(date.today(),a.exit_time)
                    att["attendance"]["hours"] +=  (exit_time - entry_time).total_seconds() / 3600
            elif a.attendence_type == AttendanceType.Absent:
                att["absent"] +=1
            elif a.attendence_type == AttendanceType.LATE:
                att["late"] += expected_work -  hours_between(a.entry_time , a.exit_time)
                att["present"] += 1
                if salary_type in [0,1]:
                    att["attendance"]["days"]  +=1
            elif a.attendence_type == AttendanceType.OVERTIME:
                att["overtime"] += hours_between(a.entry_time , a.exit_time) - expected_work
                att["present"] += 1
                if salary_type in [0,1]:
                    att["attendance"]["days"]  +=1
            elif a.attendence_type == AttendanceType.PAID_VACATION:
                att["paid_vacation"] +=1
                if salary_type in [0,1]:
                    att["attendance"]["days"] +=1
                elif salary_type==2:
                    att["attendance"]["hours"] += expected_work
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

def dashbord_card_stat(db: Session):
    total_emps = db.scalar(
        select(func.count(Employees.id))
    )

    total_active_emps = db.scalar(
        select(func.count(Employees.id))
        .where(Employees.is_active.is_(True))
    )

    today = date.today()
    day = date.today().day
    month = today.month
    year = today.year

    total_att = db.scalar(
        select(func.count(Attendence.id))
        .where(
            Attendence.attendence_type == AttendanceType.Presnt,
            extract("month", Attendence.date) == month,
            extract("year", Attendence.date) == year
        )
    )
    total_possible = total_active_emps * day

    if total_possible == 0:
        total_att_percent = 0
    else:
        total_att_percent = (total_att * 100) / total_possible

    total_vacation = len(get_all_current_vacations(db))

    return total_emps, total_active_emps, total_att_percent,total_vacation


def dashboard_overview(db: Session):
    today = date.today()
    month_start = today.replace(day=1)
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])

    total_employees = int(
        db.scalar(select(func.count(Employees.id)).where(Employees.deleted_at.is_(None))) or 0
    )
    active_employees = int(
        db.scalar(
            select(func.count(Employees.id)).where(
                Employees.deleted_at.is_(None),
                Employees.is_active.is_(True),
            )
        )
        or 0
    )
    hr_users = int(
        db.scalar(
            select(func.count(func.distinct(User.id)))
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                User.deleted_at.is_(None),
                User.is_active.is_(True),
                Role.code == "hr",
            )
        )
        or 0
    )
    pending_leave_requests = int(
        db.scalar(
            select(func.count(Vacation.id)).where(
                Vacation.vacation_status == int(VacationStatuses.pending)
            )
        )
        or 0
    )

    current_period = db.scalar(
        select(PayrollPeriod).where(
            PayrollPeriod.start_date == month_start,
            PayrollPeriod.end_date == month_end,
        )
    )
    payroll_status = current_period.status if current_period else "not_generated"
    payroll_status_counts: dict[str, int] = {}
    monthly_payroll_amount = 0.0
    if current_period:
        payroll_rows = db.scalars(
            select(EmployeePayroll).where(EmployeePayroll.payroll_period_id == current_period.id)
        ).all()
        for payroll in payroll_rows:
            payroll_status_counts[payroll.status] = payroll_status_counts.get(payroll.status, 0) + 1
            monthly_payroll_amount += float(payroll.net_salary or 0)
    else:
        monthly_payroll_amount = float(
            db.scalar(
                select(func.coalesce(func.sum(Payments.amount), 0)).where(
                    Payments.date >= month_start,
                    Payments.date <= month_end,
                    Payments.payment_type.in_([0, 3]),
                )
            )
            or 0
        )

    attendance_rows = db.scalars(select(Attendence).where(Attendence.date == today)).all()
    attendance_summary = {
        "present": 0,
        "late": 0,
        "absent": 0,
        "vacation": 0,
        "other": 0,
    }
    for row in attendance_rows:
        if row.attendence_type == AttendanceType.Presnt:
            attendance_summary["present"] += 1
        elif row.attendence_type == AttendanceType.LATE:
            attendance_summary["late"] += 1
        elif row.attendence_type == AttendanceType.Absent:
            attendance_summary["absent"] += 1
        elif row.attendence_type in (AttendanceType.PAID_VACATION, AttendanceType.Not_PAID_VACATION):
            attendance_summary["vacation"] += 1
        else:
            attendance_summary["other"] += 1

    expected_attendance_count = max(active_employees, 1)
    attendance_percent = round(
        ((attendance_summary["present"] + attendance_summary["late"]) * 100) / expected_attendance_count,
        2,
    )

    missing_salary_count = int(
        db.scalar(
            select(func.count(Employees.id)).where(
                Employees.deleted_at.is_(None),
                Employees.is_active.is_(True),
                or_(
                    Employees.monthly_price <= 0,
                    Employees.day_price <= 0,
                    Employees.hour_price <= 0,
                ),
            )
        )
        or 0
    )
    incomplete_profile_count = int(
        db.scalar(
            select(func.count(Employees.id)).where(
                Employees.deleted_at.is_(None),
                or_(Employees.email.is_(None), Employees.position.is_(None), Employees.hire_date.is_(None)),
            )
        )
        or 0
    )

    alerts = []
    if missing_salary_count:
        alerts.append({"type": "salary", "message": f"{missing_salary_count} employees have incomplete salary setup"})
    if incomplete_profile_count:
        alerts.append({"type": "profile", "message": f"{incomplete_profile_count} employee profiles need more details"})
    if pending_leave_requests:
        alerts.append({"type": "leave", "message": f"{pending_leave_requests} leave requests are waiting for review"})

    return {
        "total_employees": total_employees,
        "active_employees": active_employees,
        "hr_users": hr_users,
        "pending_leave_requests": pending_leave_requests,
        "current_payroll_status": payroll_status,
        "payroll_status_counts": payroll_status_counts,
        "monthly_payroll_amount": monthly_payroll_amount,
        "attendance_percent": attendance_percent,
        "attendance_summary": attendance_summary,
        "employees_on_leave": len(get_all_current_vacations(db)),
        "alerts": alerts,
    }
