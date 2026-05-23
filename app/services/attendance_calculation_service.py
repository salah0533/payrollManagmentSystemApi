from datetime import date, datetime, time, timedelta, timezone, tzinfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions.base_exception import BadRequestException, ForbiddenException, ResourceNotFoundException
from app.models.attendance_payroll import AttendanceCorrection, AttendanceDay, AttendanceEvent
from app.models.employees import Employees
from app.models.types.vacationStatus import VacationStatuses
from app.models.types.vacationTypes import VacationTypes
from app.models.vacation import Vacation
from app.services.notification_service import NotificationService
from app.services.policy_service import (
    WEEKDAY_NAMES,
    get_employee_schedule,
    get_local_day_bounds,
    get_or_create_payroll_policy,
    get_schedule_timezone,
    save_audit_log,
)
from app.services.vacation_types_services import HOLIDAY_VACATION_TYPE_CODE, get_vacation_type_ids_by_codes


ATTENDANCE_EVENT_FIELD_MAP = {
    "check_in": "check_in_time",
    "break_start": "break_start_time",
    "break_end": "break_end_time",
    "check_out": "check_out_time",
}
MANUAL_TIME_FIELDS = ("check_in_time", "break_start_time", "break_end_time", "check_out_time")
ATTENDANCE_REMINDER_MESSAGES = {
    "attendance_missing_checkin": (
        "Missing check-in",
        "Your attendance for {work_date} is missing a check-in.",
    ),
    "attendance_missing_break_start": (
        "Missing break start",
        "Your attendance for {work_date} is missing a break start.",
    ),
    "attendance_missing_break_end": (
        "Missing break end",
        "Your attendance for {work_date} is missing a break end.",
    ),
    "attendance_missing_checkout": (
        "Missing check-out",
        "Your attendance for {work_date} is missing a check-out.",
    ),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_event_time(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _as_day(value: datetime | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _minutes_between(start_value: time, end_value: time) -> int:
    start_dt = datetime.combine(date.today(), start_value)
    end_dt = datetime.combine(date.today(), end_value)
    return max(0, int((end_dt - start_dt).total_seconds() // 60))


def _overlap_minutes(
    window_start: time,
    window_end: time,
    range_start: time,
    range_end: time,
) -> int:
    overlap_start = max(window_start, range_start)
    overlap_end = min(window_end, range_end)
    if overlap_end <= overlap_start:
        return 0
    return _minutes_between(overlap_start, overlap_end)


def _day_bounds(work_date: date, schedule_timezone: tzinfo) -> tuple[datetime, datetime]:
    start_local = datetime.combine(work_date, time.min, tzinfo=schedule_timezone)
    end_local = datetime.combine(work_date, time.max, tzinfo=schedule_timezone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _datetime_for_work_time(work_date: date, work_time: time, schedule_timezone: tzinfo) -> datetime:
    return datetime.combine(work_date, work_time, tzinfo=schedule_timezone).astimezone(timezone.utc)


def _event_time_for_schedule(event_time: datetime, schedule_timezone: tzinfo) -> time:
    return _normalize_event_time(event_time).astimezone(schedule_timezone).time().replace(tzinfo=None)


def _scheduled_break_window(work_date: date, schedule) -> tuple[time | None, time | None]:
    if getattr(schedule, "break_start_time", None) and getattr(schedule, "break_end_time", None):
        return schedule.break_start_time, schedule.break_end_time

    break_minutes = int(schedule.break_minutes or 0)
    if break_minutes <= 0:
        return None, None

    scheduled_minutes = _minutes_between(schedule.start_time, schedule.end_time)
    if scheduled_minutes <= break_minutes:
        return None, None

    break_start_offset = max(0, (scheduled_minutes - break_minutes) // 2)
    break_start = datetime.combine(work_date, schedule.start_time) + timedelta(minutes=break_start_offset)
    break_end = break_start + timedelta(minutes=break_minutes)
    return break_start.time(), break_end.time()


def _scheduled_break_events(work_date: date, schedule) -> list[tuple[str, datetime]]:
    schedule_timezone = get_schedule_timezone(schedule)
    break_start_time, break_end_time = _scheduled_break_window(work_date, schedule)
    if not break_start_time or not break_end_time:
        return []
    return [
        ("break_start", _datetime_for_work_time(work_date, break_start_time, schedule_timezone)),
        ("break_end", _datetime_for_work_time(work_date, break_end_time, schedule_timezone)),
    ]


def _get_employee(employee_id: int, db: Session) -> Employees:
    employee = db.get(Employees, employee_id)
    if not employee:
        raise ResourceNotFoundException("Employee")
    if not employee.is_active:
        raise BadRequestException("Inactive employees cannot create attendance", message_key="errors.inactive_employee_attendance")
    return employee


def _resolve_work_date(employee_id: int, event_time: datetime, db: Session) -> tuple[date, object]:
    normalized_time = _normalize_event_time(event_time)
    tentative_date = normalized_time.date()
    schedule = get_employee_schedule(employee_id, tentative_date, db)
    local_date = normalized_time.astimezone(get_schedule_timezone(schedule)).date()
    if local_date != tentative_date:
        schedule = get_employee_schedule(employee_id, local_date, db)
    return local_date, schedule


def _maybe_notify_attendance_issue(
    *,
    employee: Employees,
    day: AttendanceDay,
    previous_status: str | None,
    db: Session,
) -> None:
    user = employee.user_account
    if not user or user.deleted_at is not None or not user.is_active:
        return

    service = NotificationService(db)
    work_date = day.work_date.isoformat()

    if day.status == "late" and previous_status != "late":
        if service.notification_exists(
            notification_type="attendance_late",
            entity_type="attendance_day",
            entity_id=day.id,
            user_id=user.id,
        ):
            return
        service.notify_user(
            user_id=user.id,
            notification_type="attendance_late",
            title="Late attendance",
            message=f"Your check-in on {work_date} was marked as late.",
            title_key="notifications.attendance_late_title",
            message_key="notifications.attendance_late_message",
            translation_params={"work_date": work_date},
            is_system_content=True,
            entity_type="attendance_day",
            entity_id=day.id,
            priority="normal",
        )


def _local_now_for_schedule(schedule, now: datetime | None = None) -> datetime:
    current = _normalize_event_time(now) if now else _utc_now()
    return current.astimezone(get_schedule_timezone(schedule))


def _is_reminder_due(*, work_date: date, trigger_time: time, schedule, now: datetime | None = None) -> bool:
    local_now = _local_now_for_schedule(schedule, now)
    if work_date < local_now.date():
        return True
    if work_date > local_now.date():
        return False
    return local_now.time().replace(tzinfo=None) >= trigger_time


def _get_due_attendance_reminder(day: AttendanceDay, schedule, now: datetime | None = None) -> str | None:
    if day.status != "incomplete":
        return None

    break_start_time, break_end_time = _scheduled_break_window(day.work_date, schedule)

    if (
        day.check_in_time
        and break_start_time
        and not day.break_start_time
        and not day.check_out_time
        and _is_reminder_due(work_date=day.work_date, trigger_time=break_start_time, schedule=schedule, now=now)
    ):
        return "attendance_missing_break_start"

    if (
        day.break_start_time
        and break_end_time
        and not day.break_end_time
        and not day.check_out_time
        and _is_reminder_due(work_date=day.work_date, trigger_time=break_end_time, schedule=schedule, now=now)
    ):
        return "attendance_missing_break_end"

    if (
        day.check_in_time
        and not day.check_out_time
        and _is_reminder_due(work_date=day.work_date, trigger_time=schedule.end_time, schedule=schedule, now=now)
    ):
        return "attendance_missing_checkout"

    if (
        day.check_out_time
        and not day.check_in_time
        and _is_reminder_due(work_date=day.work_date, trigger_time=schedule.end_time, schedule=schedule, now=now)
    ):
        return "attendance_missing_checkin"

    return None


def process_pending_attendance_notifications(db: Session, now: datetime | None = None) -> dict[str, int]:
    service = NotificationService(db)
    days = db.scalars(
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.employee).selectinload(Employees.user_account))
        .where(AttendanceDay.status == "incomplete")
        .order_by(AttendanceDay.work_date.asc(), AttendanceDay.id.asc())
    ).all()

    counts = {
        "checked": len(days),
        "sent": 0,
    }

    for day in days:
        employee = day.employee
        if not employee or not employee.is_active:
            continue

        user = employee.user_account
        if not user or user.deleted_at is not None or not user.is_active:
            continue

        schedule = get_employee_schedule(employee.id, day.work_date, db)
        notification_type = _get_due_attendance_reminder(day, schedule, now=now)
        if not notification_type:
            continue
        if service.notification_exists(
            notification_type=notification_type,
            entity_type="attendance_day",
            entity_id=day.id,
            user_id=user.id,
        ):
            continue

        title, message_template = ATTENDANCE_REMINDER_MESSAGES[notification_type]
        service.notify_user(
            user_id=user.id,
            notification_type=notification_type,
            title=title,
            message=message_template.format(work_date=day.work_date.isoformat()),
            title_key=f"notifications.{notification_type}_title",
            message_key=f"notifications.{notification_type}_message",
            translation_params={"work_date": day.work_date.isoformat()},
            is_system_content=True,
            entity_type="attendance_day",
            entity_id=day.id,
            priority="normal",
        )
        counts["sent"] += 1

    return counts


def _get_vacation(employee_id: int, work_date: date, db: Session) -> Vacation | None:
    return db.scalar(
        select(Vacation).where(
            Vacation.employee_id == employee_id,
            Vacation.start_date <= work_date,
            Vacation.end_date >= work_date,
            Vacation.vacation_status == int(VacationStatuses.approved),
        )
    )


def _is_weekly_off_date(schedule, work_date: date) -> bool:
    weekly_off_days = {item.lower() for item in (schedule.weekly_off_days or [])}
    return WEEKDAY_NAMES[work_date.weekday()] in weekly_off_days


def _materialize_weekly_off_rows(
    employee_ids: list[int],
    start_date: date,
    end_date: date,
    db: Session,
) -> int:
    if not employee_ids or start_date > end_date:
        return 0

    existing_days = db.scalars(
        select(AttendanceDay).where(
            AttendanceDay.employee_id.in_(employee_ids),
            AttendanceDay.work_date >= start_date,
            AttendanceDay.work_date <= end_date,
        )
    ).all()
    existing_keys = {(day.employee_id, day.work_date) for day in existing_days}

    created = 0
    current = start_date
    while current <= end_date:
        for employee_id in employee_ids:
            key = (employee_id, current)
            if key in existing_keys:
                continue

            schedule = get_employee_schedule(employee_id, current, db)
            if not _is_weekly_off_date(schedule, current):
                continue

            reviewed_at = _utc_now()
            day = AttendanceDay(
                employee_id=employee_id,
                work_date=current,
                work_schedule_id=schedule.id,
                expected_work_minutes=0,
                actual_work_minutes=0,
                break_minutes=0,
                normal_paid_minutes=0,
                late_minutes=0,
                early_leave_minutes=0,
                late_makeup_minutes=0,
                overtime_minutes=0,
                absence_minutes=0,
                unpaid_minutes=0,
                status="weekly_off",
                review_status="approved",
                reviewed_at=reviewed_at,
                reviewed_by=None,
                locked_at=None,
                is_manually_corrected=False,
                calculated_at=reviewed_at,
            )
            db.add(day)
            existing_keys.add(key)
            created += 1
        current += timedelta(days=1)

    if created:
        db.commit()
    return created


def _materialize_weekly_off_rows_for_employee(employee_id: int, start_date: date, end_date: date, db: Session) -> int:
    employee = db.get(Employees, employee_id)
    if not employee or not employee.is_active:
        return 0
    return _materialize_weekly_off_rows([employee_id], start_date, end_date, db)


def _materialize_weekly_off_rows_for_active_employees(start_date: date, end_date: date, db: Session) -> int:
    employee_ids = db.scalars(
        select(Employees.id).where(Employees.is_active.is_(True)).order_by(Employees.id.asc())
    ).all()
    return _materialize_weekly_off_rows(employee_ids, start_date, end_date, db)


def _get_or_create_attendance_day(employee_id: int, work_date: date, db: Session) -> AttendanceDay:
    day = db.scalar(
        select(AttendanceDay).where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date == work_date,
        )
    )
    if day:
        return day

    schedule = get_employee_schedule(employee_id, work_date, db)
    day = AttendanceDay(
        employee_id=employee_id,
        work_date=work_date,
        work_schedule_id=schedule.id,
        status="absent",
        calculated_at=_utc_now(),
    )
    db.add(day)
    db.flush()
    return day


def validate_attendance_event(employee_id: int, event_type: str, event_time: datetime, db: Session):
    event_time = _normalize_event_time(event_time)
    employee = _get_employee(employee_id, db)
    work_date, schedule = _resolve_work_date(employee_id, event_time, db)
    vacation = _get_vacation(employee_id, work_date, db)

    if vacation:
        raise ForbiddenException(
            "Employee is on approved vacation",
            code="employee_on_approved_vacation",
            message_key="errors.employee_on_approved_vacation",
        )

    schedule_timezone = get_schedule_timezone(schedule)
    day_start, day_end = _day_bounds(work_date, schedule_timezone)
    existing_events = db.scalars(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.event_time >= day_start,
            AttendanceEvent.event_time <= day_end,
        )
        .order_by(AttendanceEvent.event_time.asc(), AttendanceEvent.id.asc())
    ).all()

    by_type = {item.event_type for item in existing_events}
    if event_type == "check_in" and "check_in" in by_type:
        raise BadRequestException("Duplicate check-in is not allowed", message_key="errors.duplicate_check_in")
    if event_type == "break_start" and "break_start" in by_type:
        raise BadRequestException("Duplicate break_start is not allowed", message_key="errors.duplicate_break_start")
    if event_type == "break_start" and "check_in" not in by_type:
        raise BadRequestException("Cannot start break before check-in", message_key="errors.cannot_break_before_check_in")
    if event_type == "break_end" and "break_end" in by_type:
        raise BadRequestException("Duplicate break_end is not allowed", message_key="errors.duplicate_break_end")
    if event_type == "break_end" and "break_start" not in by_type:
        raise BadRequestException("Cannot end break before break_start", message_key="errors.cannot_end_break_before_start")
    if event_type == "break_end":
        break_start_event = next((item for item in existing_events if item.event_type == "break_start"), None)
        break_start_time = _normalize_event_time(break_start_event.event_time) if break_start_event else None
        if break_start_time and event_time <= break_start_time:
            raise BadRequestException("break_end cannot be before break_start", message_key="errors.break_end_before_break_start")
    if event_type == "check_out" and "check_in" not in by_type:
        raise BadRequestException("Cannot check out before check-in", message_key="errors.cannot_check_out_before_check_in")
    if event_type == "check_out" and "check_out" in by_type:
        raise BadRequestException("Duplicate check_out is not allowed", message_key="errors.duplicate_check_out")
    if event_type == "check_out":
        check_in_event = next((item for item in existing_events if item.event_type == "check_in"), None)
        check_in_time = _normalize_event_time(check_in_event.event_time) if check_in_event else None
        if check_in_time and event_time <= check_in_time:
            raise BadRequestException("check_out cannot be before check_in", message_key="errors.check_out_before_check_in")

    warning = None
    if WEEKDAY_NAMES[work_date.weekday()] in {day.lower() for day in (schedule.weekly_off_days or [])}:
        warning = "Attendance created on a weekly off day"

    return {"warning": warning, "employee": employee, "work_date": work_date, "schedule": schedule}


def create_attendance_event(
    employee_id: int,
    event_type: str,
    event_time: datetime,
    db: Session,
    source: str = "system",
    note: str | None = None,
    created_by: int | None = None,
):
    event_time = _normalize_event_time(event_time)
    if event_type not in ATTENDANCE_EVENT_FIELD_MAP and event_type != "manual_event":
        raise BadRequestException("Invalid attendance event type", message_key="errors.invalid_attendance_event_type")

    validation = validate_attendance_event(employee_id, event_type, event_time, db)
    event = AttendanceEvent(
        employee_id=employee_id,
        event_type=event_type,
        event_time=event_time,
        source=source,
        note=note,
        created_by=created_by,
    )
    db.add(event)
    db.flush()

    day = calculate_attendance_day(employee_id, validation["work_date"], db, trigger_reason=f"attendance_event:{event_type}")
    save_audit_log(
        db,
        action=f"attendance_{event_type}",
        entity_type="AttendanceEvent",
        entity_id=event.id,
        new_data_json={"employee_id": employee_id, "event_type": event_type, "event_time": event_time.isoformat()},
        user_id=created_by,
    )
    db.commit()
    db.refresh(event)
    db.refresh(day)
    return event, day


def _apply_corrections(day: AttendanceDay, db: Session) -> set[str]:
    corrections = db.scalars(
        select(AttendanceCorrection)
        .where(AttendanceCorrection.attendance_day_id == day.id)
        .order_by(AttendanceCorrection.corrected_at.asc(), AttendanceCorrection.id.asc())
    ).all()

    def _override_values(correction: AttendanceCorrection) -> dict[str, str | None]:
        options = correction.options_json or {}
        if correction.correction_type == "field":
            requested_values = options.get("requested_values")
            if isinstance(requested_values, dict):
                return requested_values
        if correction.correction_type == "smart_status":
            generated_values = options.get("generated_values")
            if isinstance(generated_values, dict):
                return generated_values
        if correction.new_values_json:
            return correction.new_values_json
        if correction.field_changed in {
            "check_in_time",
            "break_start_time",
            "break_end_time",
            "check_out_time",
            "status",
        }:
            return {correction.field_changed: correction.new_value}
        return {}

    applied_fields: set[str] = set()
    latest_values: dict[str, tuple[str | None, int]] = {}
    for correction in corrections:
        for field_name, field_value in _override_values(correction).items():
            if field_name not in {
                "check_in_time",
                "break_start_time",
                "break_end_time",
                "check_out_time",
                "status",
            }:
                continue
            latest_values[field_name] = (field_value, correction.id)

    latest_time_correction_id = 0
    latest_status_correction_id = 0
    for field_name, (field_value, correction_id) in latest_values.items():
        if field_name == "status":
            latest_status_correction_id = max(latest_status_correction_id, correction_id)
            continue
        parsed_value = time.fromisoformat(field_value) if field_value else None
        setattr(day, field_name, parsed_value)
        applied_fields.add(field_name)
        latest_time_correction_id = max(latest_time_correction_id, correction_id)

    if "status" in latest_values and latest_status_correction_id >= latest_time_correction_id:
        status_value, _ = latest_values["status"]
        setattr(day, "status", status_value)
        applied_fields.add("status")

    day.is_manually_corrected = bool(corrections)
    return applied_fields


def _parse_optional_time_value(value) -> time | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return time.fromisoformat(normalized)


def _requested_time_updates(payload) -> dict[str, str | None]:
    updates: dict[str, str | None] = {}
    for field_name, field_value in (getattr(payload, "new_values_json", None) or {}).items():
        if field_name in MANUAL_TIME_FIELDS:
            updates[field_name] = field_value

    field_changed = getattr(payload, "field_changed", None)
    if field_changed in MANUAL_TIME_FIELDS:
        updates[field_changed] = getattr(payload, "new_value", None)

    return updates


def _cap_break_minutes(raw_work_minutes: int, break_minutes: int) -> int:
    return max(0, min(break_minutes, raw_work_minutes))


def _requires_minimum_attendance_review(
    *,
    status: str,
    actual_work_minutes: int,
    minimum_auto_pay_minutes: int,
) -> bool:
    if minimum_auto_pay_minutes <= 0:
        return False
    if status not in {"present", "late"}:
        return False
    return 0 < actual_work_minutes < minimum_auto_pay_minutes


def _apply_allowed_late_grace(raw_late_minutes: int, allowed_late_minutes: int) -> tuple[int, int]:
    raw_late_minutes = max(0, int(raw_late_minutes or 0))
    capped_allowed_late = max(0, int(allowed_late_minutes or 0))
    if raw_late_minutes <= capped_allowed_late:
        return raw_late_minutes, 0

    # Once the employee crosses the grace limit, the grace is lost and the
    # entire lateness from schedule start becomes unpaid/late.
    return 0, raw_late_minutes


def _resolve_review_status(
    *,
    existing_status: str | None,
    has_attendance_time: bool,
    status: str,
    actual_work_minutes: int,
    minimum_auto_pay_minutes: int,
    check_in_time: time | None,
    check_out_time: time | None,
    corrected_fields: set[str],
    trigger_reason: str,
) -> str:
    if existing_status == "locked":
        return "locked"
    if status == "incomplete" or (has_attendance_time and (not check_in_time or not check_out_time)):
        return "needs_review"
    if trigger_reason in {"attendance_correction", "smart_status_correction", "mark_all_present", "legacy_migration", "auto_attendance"}:
        return "approved"
    if corrected_fields:
        return "approved"
    if _requires_minimum_attendance_review(
        status=status,
        actual_work_minutes=actual_work_minutes,
        minimum_auto_pay_minutes=minimum_auto_pay_minutes,
    ):
        return "needs_review"
    if has_attendance_time:
        return "draft"
    return existing_status or "draft"


def calculate_attendance_day(employee_id: int, work_date: date, db: Session, trigger_reason: str = "recalculation") -> AttendanceDay:
    schedule = get_employee_schedule(employee_id, work_date, db)
    policy = get_or_create_payroll_policy(db)
    vacation = _get_vacation(employee_id, work_date, db)
    day = _get_or_create_attendance_day(employee_id, work_date, db)
    employee = _get_employee(employee_id, db)
    previous_status = day.status
    previous_review_status = day.review_status
    day.work_schedule_id = schedule.id

    schedule_timezone = get_schedule_timezone(schedule)
    day_start, day_end = _day_bounds(work_date, schedule_timezone)
    events = db.scalars(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.event_time >= day_start,
            AttendanceEvent.event_time <= day_end,
        )
        .order_by(AttendanceEvent.event_time.asc(), AttendanceEvent.id.asc())
    ).all()

    event_times: dict[str, datetime] = {}
    for event in events:
        if event.event_type == "check_in" and "check_in" not in event_times:
            event_times["check_in"] = event.event_time
        elif event.event_type == "break_start" and "break_start" not in event_times:
            event_times["break_start"] = event.event_time
        elif event.event_type == "break_end":
            event_times["break_end"] = event.event_time
        elif event.event_type == "check_out":
            event_times["check_out"] = event.event_time

    day.check_in_time = _event_time_for_schedule(event_times["check_in"], schedule_timezone) if event_times.get("check_in") else None
    day.break_start_time = _event_time_for_schedule(event_times["break_start"], schedule_timezone) if event_times.get("break_start") else None
    day.break_end_time = _event_time_for_schedule(event_times["break_end"], schedule_timezone) if event_times.get("break_end") else None
    day.check_out_time = _event_time_for_schedule(event_times["check_out"], schedule_timezone) if event_times.get("check_out") else None
    corrected_fields = _apply_corrections(day, db)
    manual_status = day.status if "status" in corrected_fields else None

    scheduled_minutes = _minutes_between(schedule.start_time, schedule.end_time)
    expected_work_minutes = max(0, scheduled_minutes - int(schedule.break_minutes or 0))
    day.expected_work_minutes = expected_work_minutes
    day.break_minutes = int(schedule.break_minutes or 0)
    day.actual_work_minutes = 0
    day.normal_paid_minutes = 0
    day.late_minutes = 0
    day.early_leave_minutes = 0
    day.late_makeup_minutes = 0
    day.overtime_minutes = 0
    day.absence_minutes = 0
    day.unpaid_minutes = 0
    day.status = "absent"

    weekly_off = WEEKDAY_NAMES[work_date.weekday()] in {item.lower() for item in (schedule.weekly_off_days or [])}
    has_attendance_time = bool(day.check_in_time or day.break_start_time or day.break_end_time or day.check_out_time)
    if not has_attendance_time and weekly_off:
        day.status = "weekly_off"
        day.expected_work_minutes = 0
    elif vacation and not has_attendance_time:
        if _is_holiday_vacation(vacation, db):
            day.status = "holiday"
            day.normal_paid_minutes = expected_work_minutes
            day.unpaid_minutes = 0
        elif vacation.vacation_type == int(VacationTypes.sick):
            day.status = "sick_leave"
            day.normal_paid_minutes = expected_work_minutes if vacation.is_paid else 0
            day.unpaid_minutes = 0 if vacation.is_paid else expected_work_minutes
        elif vacation.is_paid:
            day.status = "paid_vacation"
            day.normal_paid_minutes = expected_work_minutes
        else:
            day.status = "unpaid_vacation"
            day.unpaid_minutes = expected_work_minutes
    elif not has_attendance_time:
        day.status = "absent"
        day.absence_minutes = expected_work_minutes
        day.unpaid_minutes = expected_work_minutes
    elif not day.check_in_time or not day.check_out_time:
        day.status = "incomplete"
        day.unpaid_minutes = expected_work_minutes
        day.absence_minutes = expected_work_minutes
    else:
        raw_work_minutes = _minutes_between(day.check_in_time, day.check_out_time)
        actual_break = 0
        if day.break_start_time and day.break_end_time:
            actual_break = _cap_break_minutes(raw_work_minutes, _minutes_between(day.break_start_time, day.break_end_time))
        else:
            scheduled_break_start, scheduled_break_end = _scheduled_break_window(work_date, schedule)
            if scheduled_break_start and scheduled_break_end:
                scheduled_break_overlap = _overlap_minutes(
                    scheduled_break_start,
                    scheduled_break_end,
                    day.check_in_time,
                    day.check_out_time,
                )
                actual_break = _cap_break_minutes(raw_work_minutes, scheduled_break_overlap)

        actual_work_minutes = max(0, raw_work_minutes - actual_break)
        day.actual_work_minutes = actual_work_minutes
        day.break_minutes = actual_break
        raw_late_minutes = max(0, _minutes_between(schedule.start_time, day.check_in_time)) if day.check_in_time > schedule.start_time else 0
        forgiven_late_minutes, excess_late_minutes = _apply_allowed_late_grace(
            raw_late_minutes,
            int(policy.allowed_late_minutes or 0),
        )
        day.late_minutes = excess_late_minutes
        day.early_leave_minutes = max(0, _minutes_between(day.check_out_time, schedule.end_time)) if day.check_out_time < schedule.end_time else 0

        extra_after_end = _minutes_between(schedule.end_time, day.check_out_time) if day.check_out_time > schedule.end_time else 0
        day.late_makeup_minutes = min(extra_after_end, day.late_minutes + day.early_leave_minutes)
        paid_minutes_before_makeup = min(expected_work_minutes, actual_work_minutes + forgiven_late_minutes)
        recovered_minutes = min(day.late_makeup_minutes, max(0, expected_work_minutes - paid_minutes_before_makeup))
        day.normal_paid_minutes = min(expected_work_minutes, paid_minutes_before_makeup + recovered_minutes)
        day.unpaid_minutes = max(0, expected_work_minutes - day.normal_paid_minutes)
        day.overtime_minutes = max(0, actual_work_minutes - expected_work_minutes)
        day.absence_minutes = expected_work_minutes if day.status in {"absent", "unpaid_vacation"} else 0
        day.status = "late" if day.late_minutes > 0 or day.early_leave_minutes > 0 else "present"

        if weekly_off:
            day.status = "present"
            day.expected_work_minutes = 0
            day.normal_paid_minutes = 0
            day.unpaid_minutes = 0
            day.absence_minutes = 0
            day.overtime_minutes = actual_work_minutes

        if vacation:
            day.is_manually_corrected = True

    if manual_status:
        day.status = manual_status

    if day.status == "absent":
        day.absence_minutes = expected_work_minutes
        day.unpaid_minutes = expected_work_minutes
        day.normal_paid_minutes = 0
    elif day.status == "unpaid_vacation":
        day.absence_minutes = expected_work_minutes
        day.unpaid_minutes = expected_work_minutes
    elif day.status == "unpaid":
        day.expected_work_minutes = expected_work_minutes
        day.absence_minutes = 0
        day.unpaid_minutes = expected_work_minutes
        day.normal_paid_minutes = 0
        day.overtime_minutes = 0
    elif day.status in {"paid_vacation", "sick_leave", "weekly_off", "holiday"}:
        day.absence_minutes = 0
        if day.status in {"weekly_off", "holiday"}:
            day.unpaid_minutes = 0

    day.review_status = _resolve_review_status(
        existing_status=previous_review_status,
        has_attendance_time=has_attendance_time,
        status=day.status,
        actual_work_minutes=day.actual_work_minutes,
        minimum_auto_pay_minutes=max(0, int(getattr(policy, "minimum_auto_pay_minutes", 0) or 0)),
        check_in_time=day.check_in_time,
        check_out_time=day.check_out_time,
        corrected_fields=corrected_fields,
        trigger_reason=trigger_reason,
    )
    if day.review_status == "approved":
        day.reviewed_at = _utc_now()
    elif day.review_status != "locked":
        day.reviewed_at = None
        day.reviewed_by = None

    day.calculated_at = _utc_now()
    db.add(day)
    db.flush()

    for event in events:
        event.attendance_day_id = day.id
        db.add(event)

    _maybe_notify_attendance_issue(employee=employee, day=day, previous_status=previous_status, db=db)
    _sync_payroll_after_attendance_change(day, db, trigger_reason)
    return day


def recalculate_attendance_for_employee(employee_id: int, start_date: date, end_date: date, db: Session) -> list[AttendanceDay]:
    _get_employee(employee_id, db)
    if start_date > end_date:
        raise BadRequestException("start_date must be before end_date", message_key="errors.start_before_end")

    current = start_date
    days: list[AttendanceDay] = []
    while current <= end_date:
        days.append(calculate_attendance_day(employee_id, current, db, trigger_reason="manual_recalculation"))
        current += timedelta(days=1)

    db.commit()
    for day in days:
        db.refresh(day)
    return days


def mark_all_employees_present(work_date: date, db: Session, created_by: int | None = None) -> dict[str, int]:
    employee_ids = db.scalars(
        select(Employees.id).where(Employees.is_active.is_(True)).order_by(Employees.id.asc())
    ).all()

    if not employee_ids:
        return {"updated": 0, "created": 0}

    created = 0
    updated = 0

    for employee_id in employee_ids:
        existing_day = db.scalar(
            select(AttendanceDay).where(
                AttendanceDay.employee_id == employee_id,
                AttendanceDay.work_date == work_date,
            )
        )
        if existing_day:
            updated += 1
        else:
            created += 1

        schedule = get_employee_schedule(employee_id, work_date, db)
        schedule_timezone = get_schedule_timezone(schedule)
        day_start, day_end = _day_bounds(work_date, schedule_timezone)
        desired_events = [
            ("check_in", _datetime_for_work_time(work_date, schedule.start_time, schedule_timezone)),
            *_scheduled_break_events(work_date, schedule),
            ("check_out", _datetime_for_work_time(work_date, schedule.end_time, schedule_timezone)),
        ]
        existing_types = set(
            db.scalars(
                select(AttendanceEvent.event_type).where(
                    AttendanceEvent.employee_id == employee_id,
                    AttendanceEvent.event_time >= day_start,
                    AttendanceEvent.event_time <= day_end,
                )
            ).all()
        )

        for event_type, event_time in desired_events:
            if event_type in existing_types:
                continue
            db.add(
                AttendanceEvent(
                    employee_id=employee_id,
                    event_type=event_type,
                    event_time=event_time,
                    source="admin",
                    note="Marked present by HR/Admin",
                    created_by=created_by,
                )
            )
            existing_types.add(event_type)

        day = calculate_attendance_day(employee_id, work_date, db, trigger_reason="mark_all_present")
        save_audit_log(
            db,
            action="attendance_mark_present",
            entity_type="AttendanceDay",
            entity_id=day.id,
            new_data_json={"employee_id": employee_id, "work_date": work_date.isoformat()},
            user_id=created_by,
        )

    db.commit()
    return {"updated": updated, "created": created}


def _serialize_day_values(day: AttendanceDay) -> dict[str, str | None]:
    return {
        "check_in_time": day.check_in_time.isoformat() if day.check_in_time else None,
        "break_start_time": day.break_start_time.isoformat() if day.break_start_time else None,
        "break_end_time": day.break_end_time.isoformat() if day.break_end_time else None,
        "check_out_time": day.check_out_time.isoformat() if day.check_out_time else None,
        "expected_work_minutes": str(day.expected_work_minutes),
        "actual_work_minutes": str(day.actual_work_minutes),
        "break_minutes": str(day.break_minutes),
        "normal_paid_minutes": str(day.normal_paid_minutes),
        "late_minutes": str(day.late_minutes),
        "early_leave_minutes": str(day.early_leave_minutes),
        "late_makeup_minutes": str(day.late_makeup_minutes),
        "overtime_minutes": str(day.overtime_minutes),
        "absence_minutes": str(day.absence_minutes),
        "unpaid_minutes": str(day.unpaid_minutes),
        "status": day.status,
        "review_status": day.review_status,
        "is_manually_corrected": str(bool(day.is_manually_corrected)).lower(),
    }


def _smart_override_time(options: dict, field_name: str) -> time | None:
    value = options.get(field_name)
    if value in (None, ""):
        return None
    return time.fromisoformat(str(value))


def _smart_status_time_values(
    *,
    work_date: date,
    schedule,
    options: dict,
    default_check_in: time,
    default_check_out: time,
) -> dict[str, str | None]:
    check_in_time = _smart_override_time(options, "check_in_time") or default_check_in
    check_out_time = _smart_override_time(options, "check_out_time") or default_check_out
    if check_in_time >= check_out_time:
        raise BadRequestException("Check-in must be before check-out", message_key="errors.check_in_before_check_out")

    break_start_time, break_end_time = _scheduled_break_window(work_date, schedule)
    if not (
        break_start_time
        and break_end_time
        and check_in_time < break_start_time < break_end_time < check_out_time
    ):
        break_start_time = None
        break_end_time = None

    return {
        "check_in_time": check_in_time.isoformat(),
        "break_start_time": break_start_time.isoformat() if break_start_time else None,
        "break_end_time": break_end_time.isoformat() if break_end_time else None,
        "check_out_time": check_out_time.isoformat(),
    }


def _smart_status_values(employee_id: int, work_date: date, target_status: str, options: dict, db: Session) -> dict[str, str | None]:
    schedule = get_employee_schedule(employee_id, work_date, db)
    policy = get_or_create_payroll_policy(db)
    target_status = target_status.strip().lower()
    is_weekly_off_day = _is_weekly_off_date(schedule, work_date)

    if target_status == "present":
        return {
            **_smart_status_time_values(
                work_date=work_date,
                schedule=schedule,
                options=options,
                default_check_in=schedule.start_time,
                default_check_out=schedule.end_time,
            ),
            "status": "present",
        }
    if target_status == "late":
        late_check_in = _smart_override_time(options, "check_in_time")
        if not late_check_in:
            late_minutes = int(options.get("late_minutes") or max(int(policy.allowed_late_minutes or 0) + 1, 15))
            late_check_in = (datetime.combine(work_date, schedule.start_time) + timedelta(minutes=late_minutes)).time()
        return {
            **_smart_status_time_values(
                work_date=work_date,
                schedule=schedule,
                options=options,
                default_check_in=late_check_in,
                default_check_out=schedule.end_time,
            ),
            "status": "late",
        }
    if target_status == "absent":
        if is_weekly_off_day:
            raise BadRequestException(
                "Weekly off days cannot be changed to absent",
                message_key="errors.weekly_off_cannot_be_absent",
            )
        return {
            "check_in_time": None,
            "break_start_time": None,
            "break_end_time": None,
            "check_out_time": None,
            "status": "absent",
        }
    if target_status == "paid_vacation":
        return {
            "check_in_time": None,
            "break_start_time": None,
            "break_end_time": None,
            "check_out_time": None,
            "status": "paid_vacation",
        }
    if target_status == "unpaid_vacation":
        return {
            "check_in_time": None,
            "break_start_time": None,
            "break_end_time": None,
            "check_out_time": None,
            "status": "unpaid_vacation",
        }
    if target_status == "unpaid":
        return {
            "check_in_time": None,
            "break_start_time": None,
            "break_end_time": None,
            "check_out_time": None,
            "status": "unpaid",
        }
    if target_status == "sick_leave":
        return {
            "check_in_time": None,
            "break_start_time": None,
            "break_end_time": None,
            "check_out_time": None,
            "status": "sick_leave",
        }
    if target_status == "weekly_off":
        if not is_weekly_off_day:
            raise BadRequestException("This date is not a weekly off day in the assigned work schedule", message_key="errors.weekly_off_only")
        return {
            "check_in_time": None,
            "break_start_time": None,
            "break_end_time": None,
            "check_out_time": None,
            "status": "weekly_off",
        }
    raise BadRequestException("Unsupported smart attendance target status", message_key="errors.unsupported_smart_target_status")


def apply_smart_attendance_status_correction(employee_id: int, work_date: date, target_status: str, corrected_by: int | None, reason: str, options: dict | None, db: Session):
    day = _get_or_create_attendance_day(employee_id, work_date, db)
    old_snapshot = _serialize_day_values(day)
    merged_options = {"source": "hr_correction", **(options or {})}
    target_values = _smart_status_values(employee_id, work_date, target_status, merged_options, db)
    correction = AttendanceCorrection(
        attendance_day_id=day.id,
        employee_id=employee_id,
        field_changed="status",
        correction_type="smart_status",
        target_status=target_status,
        old_value=day.status,
        new_value=target_status,
        old_values_json=old_snapshot,
        new_values_json=target_values,
        options_json={**merged_options, "generated_values": target_values},
        reason=reason,
        corrected_by=corrected_by,
    )
    db.add(correction)
    db.flush()

    updated_day = calculate_attendance_day(employee_id, work_date, db, trigger_reason="smart_status_correction")
    updated_day.review_status = "approved"
    updated_day.reviewed_at = _utc_now()
    updated_day.reviewed_by = corrected_by
    resulting_day_values = _serialize_day_values(updated_day)
    correction.options_json = {**(correction.options_json or {}), "resulting_day_values": resulting_day_values}
    db.add(updated_day)
    db.add(correction)
    save_audit_log(
        db,
        action="attendance_smart_status_correction",
        entity_type="AttendanceCorrection",
        entity_id=correction.id,
        old_data_json=correction.old_values_json,
        new_data_json={
            "target_status": target_status,
            "generated_values": target_values,
            "updated_attendance_day": resulting_day_values,
            "options": merged_options,
            "reason": reason,
        },
        user_id=corrected_by,
    )
    db.commit()
    db.refresh(correction)
    db.refresh(updated_day)
    return correction, updated_day


def _is_holiday_vacation(vacation: Vacation, db: Session) -> bool:
    return int(vacation.vacation_type) in get_vacation_type_ids_by_codes(db, HOLIDAY_VACATION_TYPE_CODE)


def create_attendance_correction(payload, db: Session):
    if payload.correction_type == "smart_status" or payload.field_changed == "status":
        return apply_smart_attendance_status_correction(
            payload.employee_id,
            payload.work_date,
            payload.target_status or payload.new_value or payload.field_changed or "present",
            payload.corrected_by,
            payload.reason,
            payload.options,
            db,
        )
    day = _get_or_create_attendance_day(payload.employee_id, payload.work_date, db)
    requested_updates = _requested_time_updates(payload)
    _validate_attendance_correction(day, payload)
    correction_field = payload.field_changed if len(requested_updates) == 1 and payload.field_changed in requested_updates else "multiple_fields"
    current_value = getattr(day, payload.field_changed, None) if payload.field_changed in MANUAL_TIME_FIELDS else None
    old_snapshot = _serialize_day_values(day)
    correction = AttendanceCorrection(
        attendance_day_id=day.id,
        employee_id=payload.employee_id,
        original_event_id=payload.original_event_id,
        field_changed=correction_field,
        correction_type=payload.correction_type,
        old_value=current_value.isoformat() if isinstance(current_value, time) else (str(current_value) if current_value is not None else None),
        new_value=payload.new_value if correction_field != "multiple_fields" else None,
        old_values_json=old_snapshot,
        new_values_json=requested_updates,
        options_json={"source": "field_correction", **(payload.options or {}), "requested_values": requested_updates},
        reason=payload.reason,
        corrected_by=payload.corrected_by,
    )
    db.add(correction)
    db.flush()

    updated_day = calculate_attendance_day(payload.employee_id, payload.work_date, db, trigger_reason="attendance_correction")
    resulting_day_values = _serialize_day_values(updated_day)
    correction.options_json = {**(correction.options_json or {}), "resulting_day_values": resulting_day_values}
    db.add(correction)
    save_audit_log(
        db,
        action="attendance_correction",
        entity_type="AttendanceCorrection",
        entity_id=correction.id,
        old_data_json=correction.old_values_json,
        new_data_json={
            "field_changed": correction_field,
            "requested_values": requested_updates,
            "updated_attendance_day": resulting_day_values,
            "reason": payload.reason,
        },
        user_id=payload.corrected_by,
    )
    db.commit()
    db.refresh(correction)
    db.refresh(updated_day)
    return correction, updated_day


def _validate_attendance_correction(day: AttendanceDay, payload) -> None:
    if payload.correction_type != "field":
        return
    updates = _requested_time_updates(payload)
    if not updates:
        raise BadRequestException("Provide at least one attendance time field to correct", message_key="errors.attendance_correction_missing_fields")

    merged_times = {field_name: getattr(day, field_name) for field_name in MANUAL_TIME_FIELDS}
    for field_name, field_value in updates.items():
        merged_times[field_name] = _parse_optional_time_value(field_value)

    check_in_time = merged_times["check_in_time"]
    break_start_time = merged_times["break_start_time"]
    break_end_time = merged_times["break_end_time"]
    check_out_time = merged_times["check_out_time"]

    if break_start_time and not check_in_time:
        raise BadRequestException("Set check-in before setting break start", message_key="errors.set_check_in_first_break_start")
    if break_end_time and not break_start_time:
        raise BadRequestException("Set break start before setting break end", message_key="errors.set_break_start_first_break_end")
    if check_out_time and not check_in_time:
        raise BadRequestException("Set check-in before setting check-out", message_key="errors.set_check_in_first_check_out")
    if check_out_time and break_start_time and not break_end_time:
        raise BadRequestException("Set break end before setting check-out", message_key="errors.set_break_end_first_check_out")

    if check_in_time and break_start_time and check_in_time >= break_start_time:
        raise BadRequestException("Check-in must be before break start", message_key="errors.check_in_before_break_start")
    if check_in_time and check_out_time and check_in_time >= check_out_time:
        raise BadRequestException("Check-in must be before check-out", message_key="errors.check_in_before_check_out")
    if break_start_time and break_end_time and break_start_time >= break_end_time:
        raise BadRequestException("Break start must be before break end", message_key="errors.break_start_before_break_end")
    if break_start_time and check_out_time and break_start_time >= check_out_time:
        raise BadRequestException("Break start must be before check-out", message_key="errors.break_start_before_check_out")
    if break_end_time and check_out_time and break_end_time >= check_out_time:
        raise BadRequestException("Break end must be before check-out", message_key="errors.break_end_before_check_out")


def delete_attendance_day(employee_id: int, work_date: date, db: Session, deleted_by: int | None = None) -> dict[str, int]:
    day = db.scalar(
        select(AttendanceDay).where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date == work_date,
        )
    )
    if not day:
        raise ResourceNotFoundException("Attendance day")

    schedule = get_employee_schedule(employee_id, work_date, db)
    day_start, day_end = _day_bounds(work_date, get_schedule_timezone(schedule))
    db.execute(
        delete(AttendanceCorrection)
        .where(AttendanceCorrection.attendance_day_id == day.id)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        delete(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.event_time >= day_start,
            AttendanceEvent.event_time <= day_end,
        )
        .execution_options(synchronize_session=False)
    )
    save_audit_log(
        db,
        action="attendance_delete_day",
        entity_type="AttendanceDay",
        entity_id=day.id,
        old_data_json={"employee_id": employee_id, "work_date": work_date.isoformat(), "status": day.status},
        user_id=deleted_by,
    )
    db.delete(day)
    db.flush()
    from app.services.payroll_calculation_service import sync_payroll_after_attendance_delete

    payroll_sync = sync_payroll_after_attendance_delete(employee_id, work_date, db, deleted_by=deleted_by)
    db.commit()
    return {"deleted": 1, "payroll_sync_status": payroll_sync.get("status")}


def review_attendance_day(employee_id: int, work_date: date, review_status: str, reviewed_by: int | None, note: str | None, db: Session) -> AttendanceDay:
    day = _get_or_create_attendance_day(employee_id, work_date, db)
    previous_review_status = day.review_status
    day.review_status = review_status
    day.reviewed_by = reviewed_by
    day.reviewed_at = _utc_now() if review_status in {"approved", "locked"} else None
    day.locked_at = _utc_now() if review_status == "locked" else None
    db.add(day)
    save_audit_log(
        db,
        action="attendance_review_status_updated",
        entity_type="AttendanceDay",
        entity_id=day.id,
        old_data_json={"review_status": previous_review_status},
        new_data_json={"review_status": review_status, "note": note},
        user_id=reviewed_by,
    )
    from app.services.payroll_calculation_service import sync_payroll_with_attendance_review

    sync_payroll_with_attendance_review(employee_id, work_date, db)
    db.commit()
    db.refresh(day)
    return day


def get_attendance_day(employee_id: int, work_date: date, db: Session) -> AttendanceDay | None:
    _materialize_weekly_off_rows_for_employee(employee_id, work_date, work_date, db)
    return db.scalar(
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events))
        .where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date == work_date,
        )
    )


def get_attendance_days(employee_id: int, start_date: date, end_date: date, db: Session) -> list[AttendanceDay]:
    _materialize_weekly_off_rows_for_employee(employee_id, start_date, end_date, db)
    return db.scalars(
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events))
        .where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date >= start_date,
            AttendanceDay.work_date <= end_date,
        )
        .order_by(AttendanceDay.work_date.asc())
    ).all()


def get_attendance_days_by_date(work_date: date, db: Session) -> list[AttendanceDay]:
    _materialize_weekly_off_rows_for_active_employees(work_date, work_date, db)
    return db.scalars(
        select(AttendanceDay)
        .join(Employees, AttendanceDay.employee_id == Employees.id)
        .options(selectinload(AttendanceDay.events))
        .where(
            Employees.deleted_at.is_(None),
            AttendanceDay.work_date == work_date,
        )
        .order_by(AttendanceDay.employee_id.asc())
    ).all()


def get_attendance_days_in_range(start_date: date, end_date: date, db: Session) -> list[AttendanceDay]:
    _materialize_weekly_off_rows_for_active_employees(start_date, end_date, db)
    return db.scalars(
        select(AttendanceDay)
        .join(Employees, AttendanceDay.employee_id == Employees.id)
        .options(selectinload(AttendanceDay.events))
        .where(
            Employees.deleted_at.is_(None),
            AttendanceDay.work_date >= start_date,
            AttendanceDay.work_date <= end_date,
        )
        .order_by(AttendanceDay.work_date.asc(), AttendanceDay.employee_id.asc())
    ).all()


def _sync_payroll_after_attendance_change(day: AttendanceDay, db: Session, trigger_reason: str):
    from app.services.payroll_calculation_service import sync_payroll_with_attendance_day

    sync_payroll_with_attendance_day(day, db, trigger_reason=trigger_reason)
