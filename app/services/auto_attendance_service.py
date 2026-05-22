from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.exceptions.base_exception import ForbiddenException
from app.models.attendance_payroll import AttendanceDay, AttendanceEvent
from app.models.employees import Employees
from app.models.types.vacationStatus import VacationStatuses
from app.models.vacation import Vacation
from app.services.attendance_calculation_service import (
    _day_bounds,
    _datetime_for_work_time,
    _scheduled_break_events,
    calculate_attendance_day,
    process_pending_attendance_notifications,
)
from app.services.audit_service import save_audit_log
from app.services.policy_service import (
    WEEKDAY_NAMES,
    get_default_work_schedule,
    get_employee_holiday_dates,
    get_or_create_payroll_policy,
    get_schedule_timezone,
)


AUTO_ATTENDANCE_INTERVAL_SECONDS = 300
AUTO_ATTENDANCE_SOURCE = "auto_attendance"
logger = logging.getLogger(__name__)


def ensure_employee_auto_attendance_schema(db: Session) -> None:
    inspector = inspect(db.connection())
    if not inspector.has_table("employees"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("employees")}
    if "auto_attendance_enabled" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE employees "
                "ADD COLUMN auto_attendance_enabled BOOLEAN NOT NULL DEFAULT FALSE"
            )
        )
    if "auto_attendance_effective_from" not in existing_columns:
        db.execute(
            text(
                "ALTER TABLE employees "
                "ADD COLUMN auto_attendance_effective_from DATE"
            )
        )
    db.execute(
        text(
            "UPDATE employees "
            "SET auto_attendance_enabled = COALESCE(auto_attendance_enabled, FALSE)"
        )
    )
    db.execute(text("ALTER TABLE employees ALTER COLUMN auto_attendance_enabled SET DEFAULT FALSE"))
    db.execute(text("ALTER TABLE employees ALTER COLUMN auto_attendance_enabled SET NOT NULL"))
    db.flush()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _local_now(schedule, now: datetime | None = None) -> datetime:
    current = now.astimezone(timezone.utc) if now else _utc_now()
    return current.astimezone(get_schedule_timezone(schedule))


def _has_auto_attendance_start_arrived(local_now: datetime, schedule) -> bool:
    return local_now.time().replace(tzinfo=None) >= schedule.start_time


def _is_schedule_workday(work_date: date, schedule, holidays: set[date]) -> bool:
    weekly_off_days = {item.lower() for item in (schedule.weekly_off_days or [])}
    if work_date in holidays:
        return False
    return WEEKDAY_NAMES[work_date.weekday()] not in weekly_off_days


def _has_approved_vacation(employee_id: int, work_date: date, db: Session) -> bool:
    return bool(
        db.scalar(
            select(Vacation.id).where(
                Vacation.employee_id == employee_id,
                Vacation.start_date <= work_date,
                Vacation.end_date >= work_date,
                Vacation.vacation_status == int(VacationStatuses.approved),
            )
        )
    )


def resolve_auto_attendance_effective_from(employee_id: int, db: Session, now: datetime | None = None) -> date:
    schedule = get_default_work_schedule(db)
    local_now = _local_now(schedule, now)
    candidate = local_now.date()
    if _has_auto_attendance_start_arrived(local_now, schedule):
        candidate += timedelta(days=1)

    while True:
        holidays = set(get_employee_holiday_dates(employee_id, candidate, candidate, db))
        if _is_schedule_workday(candidate, schedule, holidays) and not _has_approved_vacation(employee_id, candidate, db):
            return candidate
        candidate += timedelta(days=1)


def _latest_auto_attendance_work_date(schedule, now: datetime | None = None) -> date:
    local_now = _local_now(schedule, now)
    if _has_auto_attendance_start_arrived(local_now, schedule):
        return local_now.date()
    return local_now.date() - timedelta(days=1)


def enforce_self_service_auto_attendance_policy(employee_id: int, db: Session) -> None:
    employee = db.get(Employees, employee_id)
    if employee and bool(getattr(employee, "auto_attendance_enabled", False)):
        raise ForbiddenException(
            "Auto attendance is enabled for this employee. Self-service attendance actions are disabled.",
            code="auto_attendance_enabled",
            message_key="errors.auto_attendance_enabled",
        )


def _get_existing_day(employee_id: int, work_date: date, db: Session) -> AttendanceDay | None:
    return db.scalar(
        select(AttendanceDay).where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date == work_date,
        )
    )


def _has_existing_events(employee_id: int, work_date: date, schedule, db: Session) -> bool:
    day_start, day_end = _day_bounds(work_date, get_schedule_timezone(schedule))
    return bool(
        db.scalar(
            select(AttendanceEvent.id).where(
                AttendanceEvent.employee_id == employee_id,
                AttendanceEvent.event_time >= day_start,
                AttendanceEvent.event_time <= day_end,
            )
        )
    )


def _seed_auto_attendance_events(employee_id: int, work_date: date, schedule, db: Session) -> None:
    schedule_timezone = get_schedule_timezone(schedule)
    desired_events = [
        ("check_in", _datetime_for_work_time(work_date, schedule.start_time, schedule_timezone)),
        *_scheduled_break_events(work_date, schedule),
        ("check_out", _datetime_for_work_time(work_date, schedule.end_time, schedule_timezone)),
    ]
    for event_type, event_time in desired_events:
        db.add(
            AttendanceEvent(
                employee_id=employee_id,
                event_type=event_type,
                event_time=event_time,
                source=AUTO_ATTENDANCE_SOURCE,
                note="Scheduled auto attendance generated by the system.",
            )
        )
    db.flush()


def apply_auto_attendance_for_day(employee: Employees, work_date: date, schedule, holidays: set[date], db: Session) -> str:
    if not _is_schedule_workday(work_date, schedule, holidays):
        return "skipped_non_workday"
    if _has_approved_vacation(employee.id, work_date, db):
        return "skipped_vacation"

    existing_day = _get_existing_day(employee.id, work_date, db)
    if existing_day and (existing_day.review_status == "locked" or existing_day.locked_at):
        return "skipped_locked"
    if existing_day and existing_day.is_manually_corrected:
        return "skipped_manual"
    if _has_existing_events(employee.id, work_date, schedule, db):
        return "skipped_existing_events"

    _seed_auto_attendance_events(employee.id, work_date, schedule, db)
    day = calculate_attendance_day(employee.id, work_date, db, trigger_reason="auto_attendance")
    day.review_status = "approved"
    day.reviewed_at = _utc_now()
    day.reviewed_by = None
    db.add(day)
    db.flush()
    save_audit_log(
        db,
        action="auto_attendance_generated",
        entity_type="AttendanceDay",
        entity_id=day.id,
        new_data_json={
            "employee_id": employee.id,
            "work_date": work_date.isoformat(),
            "source": AUTO_ATTENDANCE_SOURCE,
        },
    )
    return "updated" if existing_day else "created"


def process_auto_attendance(db: Session, now: datetime | None = None) -> dict[str, int]:
    schedule = get_default_work_schedule(db)
    latest_due = _latest_auto_attendance_work_date(schedule, now)
    employees = db.scalars(
        select(Employees)
        .where(
            Employees.deleted_at.is_(None),
            Employees.is_active.is_(True),
            Employees.auto_attendance_enabled.is_(True),
            Employees.auto_attendance_effective_from.is_not(None),
        )
        .order_by(Employees.id.asc())
    ).all()

    counts = {
        "employees": len(employees),
        "created": 0,
        "updated": 0,
        "skipped_existing_events": 0,
        "skipped_locked": 0,
        "skipped_manual": 0,
        "skipped_non_workday": 0,
        "skipped_vacation": 0,
    }

    for employee in employees:
        cursor = employee.auto_attendance_effective_from
        if cursor is None or cursor > latest_due:
            continue

        while cursor <= latest_due:
            holidays = set(get_employee_holiday_dates(employee.id, cursor, cursor, db))
            result = apply_auto_attendance_for_day(employee, cursor, schedule, holidays, db)
            counts[result] = counts.get(result, 0) + 1
            cursor += timedelta(days=1)

        employee.auto_attendance_effective_from = cursor
        db.add(employee)

    db.commit()
    return counts


async def run_auto_attendance_loop(interval_seconds: int = AUTO_ATTENDANCE_INTERVAL_SECONDS) -> None:
    while True:
        db = SessionLocal()
        try:
            result = process_auto_attendance(db)
            notification_result = process_pending_attendance_notifications(db)
            if notification_result["sent"]:
                db.commit()
            if result["created"] or result["updated"]:
                logger.info(
                    "Auto attendance processed: created=%s updated=%s skipped_existing_events=%s",
                    result["created"],
                    result["updated"],
                    result["skipped_existing_events"],
                )
            if notification_result["sent"]:
                logger.info(
                    "Attendance reminders processed: checked=%s sent=%s",
                    notification_result["checked"],
                    notification_result["sent"],
                )
        except asyncio.CancelledError:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            logger.exception("Auto attendance runner failed")
        finally:
            db.close()

        await asyncio.sleep(interval_seconds)
