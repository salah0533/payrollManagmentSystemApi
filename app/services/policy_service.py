from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.attendance_payroll import EmployeeCompensation, PayrollPolicy, WorkSchedule
from app.models.employees import Employees
from app.models.settings import Settings
from app.services.audit_service import save_audit_log


SALARY_TYPE_MAP = {
    0: "monthly",
    1: "daily",
    2: "hourly",
}

WEEKDAY_NAMES = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


def _decimal(value, default: str = "0.00") -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create_payroll_policy(db: Session) -> PayrollPolicy:
    policy = db.scalar(select(PayrollPolicy).order_by(PayrollPolicy.id))
    if policy:
        return policy

    policy = PayrollPolicy(
        name="default",
        payroll_cycle="monthly",
        minimum_overtime_minutes=30,
        allowed_late_minutes=0,
        default_currency="USD",
        significant_change_threshold=Decimal("1.00"),
        paid_vacation_counts_for_daily=True,
        overtime_enabled=True,
        late_makeup_enabled=True,
        late_deduction_enabled=True,
        auto_recalculate_draft_payroll=True,
        lock_payroll_after_payment=True,
        holidays_json=[],
    )
    db.add(policy)
    db.flush()
    return policy


def update_payroll_policy(db: Session, **values) -> PayrollPolicy:
    policy = get_or_create_payroll_policy(db)
    for key, value in values.items():
        setattr(policy, key, value)
    policy.updated_at = _utc_now()
    db.add(policy)
    db.flush()
    return policy


def get_employee_schedule(employee_id: int, target_date: date, db: Session) -> WorkSchedule:
    schedule = db.scalar(
        select(WorkSchedule)
        .where(WorkSchedule.is_default.is_(True))
        .order_by(WorkSchedule.id)
    )
    if schedule:
        return schedule

    settings = db.scalar(select(Settings).order_by(Settings.id))
    start_time = settings.entry_time if settings and settings.entry_time else datetime.strptime("08:00", "%H:%M").time()
    end_time = settings.exit_time if settings and settings.exit_time else datetime.strptime("17:00", "%H:%M").time()
    schedule = WorkSchedule(
        name="Default Schedule",
        start_time=start_time,
        end_time=end_time,
        break_minutes=60,
        weekly_off_days=["friday", "saturday"],
        timezone="UTC",
        is_default=True,
    )
    db.add(schedule)
    db.flush()
    return schedule


def get_default_work_schedule(db: Session) -> WorkSchedule:
    return get_employee_schedule(0, date.today(), db)


def update_default_work_schedule(db: Session, **values) -> WorkSchedule:
    schedule = get_default_work_schedule(db)
    if values.get("is_default", True):
        other_defaults = db.scalars(
            select(WorkSchedule).where(
                WorkSchedule.id != schedule.id,
                WorkSchedule.is_default.is_(True),
            )
        ).all()
        for item in other_defaults:
            item.is_default = False
            db.add(item)

    for key, value in values.items():
        setattr(schedule, key, value)
    schedule.updated_at = _utc_now()
    db.add(schedule)
    db.flush()
    return schedule


def get_employee_compensation(employee_id: int, target_date: date, db: Session) -> EmployeeCompensation:
    compensation = db.scalar(
        select(EmployeeCompensation).where(
            EmployeeCompensation.employee_id == employee_id,
            EmployeeCompensation.effective_from <= target_date,
            or_(
                EmployeeCompensation.effective_to.is_(None),
                EmployeeCompensation.effective_to >= target_date,
            ),
        ).order_by(EmployeeCompensation.effective_from.desc(), EmployeeCompensation.id.desc())
    )
    if compensation:
        return compensation

    employee = db.get(Employees, employee_id)
    if not employee:
        raise ValueError("employee not found")

    compensation = EmployeeCompensation(
        employee_id=employee_id,
        salary_type=SALARY_TYPE_MAP.get(employee.salary_type, "monthly"),
        base_monthly_salary=_decimal(employee.monthly_price),
        daily_rate=_decimal(employee.day_price),
        hourly_rate=_decimal(employee.hour_price),
        overtime_rate=_decimal(employee.extra_hours_price),
        late_deduction_rate=_decimal(employee.hour_price) / Decimal("60") if employee.hour_price else Decimal("0.00"),
        currency="USD",
        effective_from=employee.joined or target_date,
        effective_to=None,
        is_active=True,
        created_at=_utc_now(),
    )
    db.add(compensation)
    db.flush()
    return compensation


def get_working_days(start_date: date, end_date: date, schedule: WorkSchedule, holidays: list[date] | None = None) -> list[date]:
    holidays = holidays or []
    holiday_set = set(holidays)
    weekly_off = {day.lower() for day in (schedule.weekly_off_days or [])}
    current = start_date
    result: list[date] = []

    while current <= end_date:
        if current not in holiday_set and WEEKDAY_NAMES[current.weekday()] not in weekly_off:
            result.append(current)
        current += timedelta(days=1)

    return result


def parse_holidays(values: list[str] | None) -> list[date]:
    result: list[date] = []
    for value in values or []:
        try:
            result.append(date.fromisoformat(value))
        except ValueError:
            continue
    return result
