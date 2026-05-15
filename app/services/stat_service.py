from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.attendance_payroll import AttendanceDay
from app.models.employees import Employees
from app.models.types.vacationStatus import VacationStatuses
from app.models.vacation import Vacation
from app.services.policy_service import get_default_work_schedule, get_working_days, get_or_create_payroll_policy, parse_holidays


def dashboard_attendance_stats(db: Session) -> dict[str, int | float]:
    total_emps = db.scalar(select(func.count(Employees.id))) or 0
    total_active_emps = db.scalar(select(func.count(Employees.id)).where(Employees.is_active.is_(True))) or 0

    today = date.today()
    month_start = today.replace(day=1)
    schedule = get_default_work_schedule(db)
    policy = get_or_create_payroll_policy(db)
    holidays = parse_holidays(policy.holidays_json)
    workdays_so_far = [item for item in get_working_days(month_start, today, schedule, holidays) if item <= today]

    monthly_days = db.scalars(
        select(AttendanceDay).where(
            AttendanceDay.work_date >= month_start,
            AttendanceDay.work_date <= today,
        )
    ).all()

    status_counts = {
        "present_days": 0,
        "late_days": 0,
        "absent_days": 0,
        "vacation_days": 0,
        "weekly_off_days": 0,
        "incomplete_days": 0,
        "needs_review_days": 0,
        "total_paid_minutes": 0,
        "total_unpaid_minutes": 0,
        "overtime_minutes": 0,
    }

    attendance_credit_statuses = {"present", "late", "paid_vacation", "sick_leave"}
    credited_days = 0

    for day in monthly_days:
        if day.status == "present":
            status_counts["present_days"] += 1
        elif day.status == "late":
            status_counts["late_days"] += 1
        elif day.status == "absent":
            status_counts["absent_days"] += 1
        elif day.status in {"paid_vacation", "unpaid_vacation", "sick_leave"}:
            status_counts["vacation_days"] += 1
        elif day.status == "weekly_off":
            status_counts["weekly_off_days"] += 1
        elif day.status == "incomplete":
            status_counts["incomplete_days"] += 1

        if day.review_status == "needs_review":
            status_counts["needs_review_days"] += 1

        status_counts["total_paid_minutes"] += int(day.normal_paid_minutes or 0)
        status_counts["total_unpaid_minutes"] += int(day.unpaid_minutes or 0)
        status_counts["overtime_minutes"] += int(day.overtime_minutes or 0)

        if day.status in attendance_credit_statuses:
            credited_days += 1

    total_possible = total_active_emps * len(workdays_so_far)
    total_att_percent = (credited_days * 100 / total_possible) if total_possible else 0
    total_vacation = db.scalar(
        select(func.count(Vacation.id)).where(
            Vacation.vacation_status == int(VacationStatuses.approved),
            Vacation.start_date <= today,
            Vacation.end_date >= today,
        )
    ) or 0

    return {
        "total_emps": total_emps,
        "total_active_emps": total_active_emps,
        "total_att_percent": total_att_percent,
        "total_vacation": total_vacation,
        **status_counts,
    }
