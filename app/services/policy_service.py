from datetime import date, datetime, time, timedelta, timezone, tzinfo
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil import tz
from sqlalchemy import and_, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.exceptions.base_exception import BadRequestException, ResourceNotFoundException
from app.models.attendance_payroll import EmployeeCompensation, PayrollPolicy, WorkSchedule
from app.models.attendance_payroll import (
    DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE,
    MONTHLY_PAYROLL_CALCULATION_MODES,
)
from app.models.employees import Employees
from app.models.settings import Settings
from app.models.types.vacationStatus import VacationStatuses
from app.models.vacation import Vacation
from app.services.audit_service import save_audit_log
from app.services.vacation_types_services import HOLIDAY_VACATION_TYPE_CODE, get_vacation_type_ids_by_codes


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


def _normalize_monthly_payroll_calculation_mode(value: str | None) -> str:
    normalized = (value or DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE).strip().lower()
    if normalized not in MONTHLY_PAYROLL_CALCULATION_MODES:
        return DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE
    return normalized


def _minutes_between_times(start_value: time, end_value: time) -> int:
    start_dt = datetime.combine(date.today(), start_value)
    end_dt = datetime.combine(date.today(), end_value)
    return max(0, int((end_dt - start_dt).total_seconds() // 60))


def _derive_break_window(start_time: time, end_time: time, break_minutes: int) -> tuple[time | None, time | None]:
    minutes = max(0, int(break_minutes or 0))
    if minutes <= 0:
        return None, None

    scheduled_minutes = _minutes_between_times(start_time, end_time)
    if scheduled_minutes <= minutes:
        return None, None

    break_start_offset = max(0, (scheduled_minutes - minutes) // 2)
    break_start = datetime.combine(date.today(), start_time) + timedelta(minutes=break_start_offset)
    break_end = break_start + timedelta(minutes=minutes)
    return break_start.time(), break_end.time()


def _ensure_work_schedule_schema(db: Session) -> None:
    inspector = inspect(db.connection())
    if not inspector.has_table("work_schedule"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("work_schedule")}
    if "break_start_time" not in existing_columns:
        db.execute(text("ALTER TABLE work_schedule ADD COLUMN break_start_time TIME"))
    if "break_end_time" not in existing_columns:
        db.execute(text("ALTER TABLE work_schedule ADD COLUMN break_end_time TIME"))
    db.flush()

    schedules = db.scalars(select(WorkSchedule)).all()
    for schedule in schedules:
        if schedule.break_start_time or schedule.break_end_time:
            continue
        break_start_time, break_end_time = _derive_break_window(
            schedule.start_time,
            schedule.end_time,
            int(schedule.break_minutes or 0),
        )
        if break_start_time and break_end_time:
            schedule.break_start_time = break_start_time
            schedule.break_end_time = break_end_time
            db.add(schedule)
    db.flush()


def _ensure_payroll_policy_schema(db: Session) -> None:
    inspector = inspect(db.connection())
    if not inspector.has_table("payroll_policy"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("payroll_policy")}
    if "minimum_auto_pay_minutes" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN minimum_auto_pay_minutes INTEGER NOT NULL DEFAULT 0"
            )
        )
    if "annual_vacation_days_by_year" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN annual_vacation_days_by_year JSON NOT NULL DEFAULT '{}'"
            )
        )
    if "allow_vacation_carryover" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN allow_vacation_carryover BOOLEAN NOT NULL DEFAULT TRUE"
            )
        )
    if "max_vacation_carryover_days" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN max_vacation_carryover_days INTEGER"
            )
        )
    if "carryover_expiry_month" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN carryover_expiry_month INTEGER"
            )
        )
    if "carryover_expiry_day" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN carryover_expiry_day INTEGER"
            )
        )
    if "reserve_vacation_days_on_pending" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN reserve_vacation_days_on_pending BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
    if "monthly_payroll_calculation_mode" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE payroll_policy "
                "ADD COLUMN monthly_payroll_calculation_mode VARCHAR(20) NOT NULL DEFAULT 'calendar_days'"
            )
        )


def get_schedule_timezone(schedule: WorkSchedule) -> tzinfo:
    timezone_name = (schedule.timezone or "UTC").strip() or "UTC"
    if timezone_name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        fallback_timezone = tz.gettz(timezone_name)
        return fallback_timezone or timezone.utc


def get_or_create_payroll_policy(db: Session) -> PayrollPolicy:
    _ensure_payroll_policy_schema(db)
    policy = db.scalar(select(PayrollPolicy).order_by(PayrollPolicy.id))
    if policy:
        normalized_mode = _normalize_monthly_payroll_calculation_mode(
            getattr(policy, "monthly_payroll_calculation_mode", None)
        )
        if getattr(policy, "monthly_payroll_calculation_mode", None) != normalized_mode:
            policy.monthly_payroll_calculation_mode = normalized_mode
            policy.updated_at = _utc_now()
            db.add(policy)
            db.flush()
        return policy

    policy = PayrollPolicy(
        name="default",
        payroll_cycle="monthly",
        minimum_overtime_minutes=30,
        minimum_auto_pay_minutes=0,
        allowed_late_minutes=0,
        default_currency="DZD",
        significant_change_threshold=Decimal("1.00"),
        paid_vacation_counts_for_daily=True,
        overtime_enabled=True,
        monthly_payroll_calculation_mode=DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE,
        auto_recalculate_draft_payroll=True,
        lock_payroll_after_payment=True,
        holidays_json=[],
        annual_vacation_days_by_year={},
        allow_vacation_carryover=True,
        max_vacation_carryover_days=None,
        carryover_expiry_month=None,
        carryover_expiry_day=None,
        reserve_vacation_days_on_pending=False,
    )
    db.add(policy)
    db.flush()
    return policy


def update_payroll_policy(db: Session, **values) -> PayrollPolicy:
    policy = get_or_create_payroll_policy(db)
    if "monthly_payroll_calculation_mode" in values:
        values["monthly_payroll_calculation_mode"] = _normalize_monthly_payroll_calculation_mode(
            values["monthly_payroll_calculation_mode"]
        )
    for key, value in values.items():
        setattr(policy, key, value)
    policy.updated_at = _utc_now()
    db.add(policy)
    db.flush()
    return policy


def get_employee_schedule(employee_id: int, target_date: date, db: Session) -> WorkSchedule:
    _ensure_work_schedule_schema(db)
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
        break_start_time=None,
        break_end_time=None,
        break_minutes=60,
        weekly_off_days=["friday", "saturday"],
        timezone="Africa/Algiers",
        is_default=True,
    )
    schedule.break_start_time, schedule.break_end_time = _derive_break_window(
        schedule.start_time,
        schedule.end_time,
        schedule.break_minutes,
    )
    db.add(schedule)
    db.flush()
    return schedule


def get_default_work_schedule(db: Session) -> WorkSchedule:
    _ensure_work_schedule_schema(db)
    return get_employee_schedule(0, date.today(), db)


def list_work_schedules(db: Session) -> list[WorkSchedule]:
    _ensure_work_schedule_schema(db)
    get_default_work_schedule(db)
    return db.scalars(
        select(WorkSchedule).order_by(WorkSchedule.is_default.desc(), WorkSchedule.id.asc())
    ).all()


def get_work_schedule(schedule_id: int, db: Session) -> WorkSchedule:
    _ensure_work_schedule_schema(db)
    schedule = db.get(WorkSchedule, schedule_id)
    if not schedule:
        raise ResourceNotFoundException("Work schedule", schedule_id)
    return schedule


def get_local_day_bounds(target_date: date, schedule: WorkSchedule) -> tuple[datetime, datetime]:
    tz = get_schedule_timezone(schedule)
    start_local = datetime.combine(target_date, time.min, tzinfo=tz)
    end_local = datetime.combine(target_date, time.max, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _apply_work_schedule_values(schedule: WorkSchedule, values: dict[str, object]) -> WorkSchedule:
    for key, value in values.items():
        setattr(schedule, key, value)
    if schedule.break_start_time and schedule.break_end_time:
        schedule.break_minutes = _minutes_between_times(schedule.break_start_time, schedule.break_end_time)
    elif not schedule.break_start_time and not schedule.break_end_time:
        schedule.break_start_time, schedule.break_end_time = _derive_break_window(
            schedule.start_time,
            schedule.end_time,
            int(schedule.break_minutes or 0),
        )
    schedule.updated_at = _utc_now()
    return schedule


def _set_default_schedule(schedule: WorkSchedule, db: Session) -> None:
    other_schedules = db.scalars(
        select(WorkSchedule).where(
            WorkSchedule.id != schedule.id,
            WorkSchedule.is_default.is_(True),
        )
    ).all()
    for item in other_schedules:
        item.is_default = False
        item.updated_at = _utc_now()
        db.add(item)
    schedule.is_default = True


def create_work_schedule(db: Session, **values) -> WorkSchedule:
    _ensure_work_schedule_schema(db)
    existing_schedules = db.scalars(select(WorkSchedule).order_by(WorkSchedule.id.asc())).all()
    make_default = bool(values.get("is_default", False)) or not existing_schedules
    schedule = WorkSchedule(
        name=str(values["name"]),
        start_time=values["start_time"],
        end_time=values["end_time"],
        break_start_time=values.get("break_start_time"),
        break_end_time=values.get("break_end_time"),
        break_minutes=int(values.get("break_minutes", 0) or 0),
        weekly_off_days=list(values.get("weekly_off_days") or []),
        timezone=str(values["timezone"]),
        is_default=make_default,
    )
    schedule = _apply_work_schedule_values(schedule, {})
    db.add(schedule)
    db.flush()
    if make_default:
        _set_default_schedule(schedule, db)
        db.add(schedule)
        db.flush()
    return schedule


def update_default_work_schedule(db: Session, **values) -> WorkSchedule:
    schedule = get_default_work_schedule(db)
    return update_work_schedule(schedule.id, db, **values)


def update_work_schedule(schedule_id: int, db: Session, **values) -> WorkSchedule:
    schedule = get_work_schedule(schedule_id, db)
    make_default = bool(values.get("is_default", schedule.is_default))
    if schedule.is_default and not make_default:
        has_other_default = db.scalar(
            select(WorkSchedule.id).where(
                WorkSchedule.id != schedule.id,
                WorkSchedule.is_default.is_(True),
            ).limit(1)
        ) is not None
        if not has_other_default:
            raise BadRequestException("At least one default work schedule is required")
    if make_default:
        _set_default_schedule(schedule, db)
    schedule = _apply_work_schedule_values(schedule, values)
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
        if compensation.salary_type == "monthly" and _decimal(compensation.overtime_rate) <= Decimal("0.00"):
            employee = db.get(Employees, employee_id)
            configured_overtime_rate = _decimal(employee.extra_hours_price) if employee else Decimal("0.00")
            if configured_overtime_rate > Decimal("0.00"):
                compensation.overtime_rate = configured_overtime_rate
                db.add(compensation)
                db.flush()
        return compensation

    employee = db.get(Employees, employee_id)
    if not employee:
        raise ResourceNotFoundException("Employee")

    salary_type = SALARY_TYPE_MAP.get(employee.salary_type, "monthly")
    compensation_kwargs = {
        "employee_id": employee_id,
        "salary_type": salary_type,
        "base_monthly_salary": _decimal(employee.monthly_price),
        "currency": "DZD",
        "effective_from": employee.joined or target_date,
        "effective_to": None,
        "is_active": True,
        "created_at": _utc_now(),
        "daily_rate_override": None,
        "hourly_rate_override": None,
        "overtime_rate_override": None,
        "late_deduction_rate_override": None,
    }

    if salary_type == "monthly":
        compensation_kwargs.update(
            daily_rate=Decimal("0.00"),
            hourly_rate=Decimal("0.00"),
            overtime_rate=_decimal(employee.extra_hours_price),
            late_deduction_rate=Decimal("0.00"),
        )
    else:
        compensation_kwargs.update(
            daily_rate=_decimal(employee.day_price),
            hourly_rate=_decimal(employee.hour_price),
            overtime_rate=_decimal(employee.extra_hours_price),
            late_deduction_rate=_decimal(employee.hour_price) / Decimal("60") if employee.hour_price else Decimal("0.00"),
        )

    compensation = EmployeeCompensation(**compensation_kwargs)
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


def get_employee_holiday_dates(employee_id: int, start_date: date, end_date: date, db: Session) -> list[date]:
    holiday_type_ids = get_vacation_type_ids_by_codes(db, HOLIDAY_VACATION_TYPE_CODE)
    if not holiday_type_ids:
        return []

    vacations = db.scalars(
        select(Vacation).where(
            Vacation.employee_id == employee_id,
            Vacation.vacation_status == int(VacationStatuses.approved),
            Vacation.vacation_type.in_(holiday_type_ids),
            Vacation.start_date <= end_date,
            Vacation.end_date >= start_date,
        )
    ).all()

    holiday_dates: set[date] = set()
    for vacation in vacations:
        current = max(vacation.start_date, start_date)
        last = min(vacation.end_date, end_date)
        while current <= last:
            holiday_dates.add(current)
            current += timedelta(days=1)

    return sorted(holiday_dates)


def parse_holidays(values: list[str] | None) -> list[date]:
    result: list[date] = []
    for value in values or []:
        try:
            result.append(date.fromisoformat(value))
        except ValueError:
            continue
    return result
