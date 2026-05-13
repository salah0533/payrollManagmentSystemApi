from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.attendance_payroll import AttendanceCorrection, AttendanceDay, AttendanceEvent
from app.models.employees import Employees
from app.models.types.vacationStatus import VacationStatuses
from app.models.types.vacationTypes import VacationTypes
from app.models.vacation import Vacation
from app.services.policy_service import WEEKDAY_NAMES, get_employee_schedule, save_audit_log


ATTENDANCE_EVENT_FIELD_MAP = {
    "check_in": "check_in_time",
    "break_start": "break_start_time",
    "break_end": "break_end_time",
    "check_out": "check_out_time",
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


def _day_bounds(work_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(work_date, time.min).replace(tzinfo=timezone.utc),
        datetime.combine(work_date, time.max).replace(tzinfo=timezone.utc),
    )


def _get_employee(employee_id: int, db: Session) -> Employees:
    employee = db.get(Employees, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")
    if not employee.is_active:
        raise HTTPException(status_code=400, detail="Inactive employees cannot create attendance")
    return employee


def _get_vacation(employee_id: int, work_date: date, db: Session) -> Vacation | None:
    return db.scalar(
        select(Vacation).where(
            Vacation.employee_id == employee_id,
            Vacation.start_date <= work_date,
            Vacation.end_date >= work_date,
            Vacation.vacation_status == int(VacationStatuses.approved),
        )
    )


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
    work_date = event_time.date()
    schedule = get_employee_schedule(employee_id, work_date, db)
    vacation = _get_vacation(employee_id, work_date, db)

    if vacation:
        raise HTTPException(status_code=400, detail="Employee is on approved vacation")

    day_start, day_end = _day_bounds(work_date)
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
        raise HTTPException(status_code=400, detail="Duplicate check-in is not allowed")
    if event_type == "break_start" and "break_start" in by_type:
        raise HTTPException(status_code=400, detail="Duplicate break_start is not allowed")
    if event_type == "break_start" and "check_in" not in by_type:
        raise HTTPException(status_code=400, detail="Cannot start break before check-in")
    if event_type == "break_end" and "break_end" in by_type:
        raise HTTPException(status_code=400, detail="Duplicate break_end is not allowed")
    if event_type == "break_end" and "break_start" not in by_type:
        raise HTTPException(status_code=400, detail="Cannot end break before break_start")
    if event_type == "break_end":
        break_start_event = next((item for item in existing_events if item.event_type == "break_start"), None)
        if break_start_event and event_time <= break_start_event.event_time:
            raise HTTPException(status_code=400, detail="break_end cannot be before break_start")
    if event_type == "check_out" and "check_in" not in by_type:
        raise HTTPException(status_code=400, detail="Cannot check out before check-in")
    if event_type == "check_out" and "check_out" in by_type:
        raise HTTPException(status_code=400, detail="Duplicate check_out is not allowed")
    if event_type == "check_out":
        check_in_event = next((item for item in existing_events if item.event_type == "check_in"), None)
        if check_in_event and event_time <= check_in_event.event_time:
            raise HTTPException(status_code=400, detail="check_out cannot be before check_in")

    if WEEKDAY_NAMES[work_date.weekday()] in {day.lower() for day in (schedule.weekly_off_days or [])}:
        return {"warning": "Attendance created on a weekly off day"}

    return {"warning": None, "employee": employee}


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
        raise HTTPException(status_code=400, detail="Invalid attendance event type")

    validate_attendance_event(employee_id, event_type, event_time, db)
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

    day = calculate_attendance_day(employee_id, event_time.date(), db, trigger_reason=f"attendance_event:{event_type}")
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


def _apply_corrections(day: AttendanceDay, db: Session):
    corrections = db.scalars(
        select(AttendanceCorrection)
        .where(AttendanceCorrection.attendance_day_id == day.id)
        .order_by(AttendanceCorrection.corrected_at.asc(), AttendanceCorrection.id.asc())
    ).all()

    for correction in corrections:
        if correction.field_changed not in {
            "check_in_time",
            "break_start_time",
            "break_end_time",
            "check_out_time",
            "status",
        }:
            continue
        parsed_value = correction.new_value
        if correction.field_changed.endswith("_time"):
            parsed_value = time.fromisoformat(correction.new_value) if correction.new_value else None
        setattr(day, correction.field_changed, parsed_value)

    day.is_manually_corrected = bool(corrections)


def calculate_attendance_day(employee_id: int, work_date: date, db: Session, trigger_reason: str = "recalculation") -> AttendanceDay:
    schedule = get_employee_schedule(employee_id, work_date, db)
    vacation = _get_vacation(employee_id, work_date, db)
    day = _get_or_create_attendance_day(employee_id, work_date, db)
    day.work_schedule_id = schedule.id

    day_start, day_end = _day_bounds(work_date)
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

    day.check_in_time = event_times.get("check_in").time() if event_times.get("check_in") else None
    day.break_start_time = event_times.get("break_start").time() if event_times.get("break_start") else None
    day.break_end_time = event_times.get("break_end").time() if event_times.get("break_end") else None
    day.check_out_time = event_times.get("check_out").time() if event_times.get("check_out") else None
    _apply_corrections(day, db)

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
    if not events and weekly_off:
        day.status = "weekly_off"
        day.expected_work_minutes = 0
    elif vacation and not events:
        if vacation.vacation_type == int(VacationTypes.sick):
            day.status = "sick_leave"
            day.normal_paid_minutes = expected_work_minutes if vacation.is_paid else 0
            day.unpaid_minutes = 0 if vacation.is_paid else expected_work_minutes
        elif vacation.is_paid:
            day.status = "paid_vacation"
            day.normal_paid_minutes = expected_work_minutes
        else:
            day.status = "unpaid_vacation"
            day.unpaid_minutes = expected_work_minutes
    elif not events:
        day.status = "absent"
        day.absence_minutes = expected_work_minutes
        day.unpaid_minutes = expected_work_minutes
    elif not day.check_in_time or not day.check_out_time:
        day.status = "incomplete"
        day.unpaid_minutes = expected_work_minutes
    else:
        actual_break = int(schedule.break_minutes or 0)
        if day.break_start_time and day.break_end_time:
            actual_break = _minutes_between(day.break_start_time, day.break_end_time)

        actual_work_minutes = max(0, _minutes_between(day.check_in_time, day.check_out_time) - actual_break)
        day.actual_work_minutes = actual_work_minutes
        day.break_minutes = actual_break
        day.late_minutes = max(0, _minutes_between(schedule.start_time, day.check_in_time)) if day.check_in_time > schedule.start_time else 0
        day.early_leave_minutes = max(0, _minutes_between(day.check_out_time, schedule.end_time)) if day.check_out_time < schedule.end_time else 0

        extra_after_end = _minutes_between(schedule.end_time, day.check_out_time) if day.check_out_time > schedule.end_time else 0
        day.late_makeup_minutes = min(extra_after_end, day.late_minutes + day.early_leave_minutes)
        day.normal_paid_minutes = min(expected_work_minutes, actual_work_minutes)
        day.unpaid_minutes = max(0, expected_work_minutes - actual_work_minutes)
        day.overtime_minutes = max(0, actual_work_minutes - expected_work_minutes)
        day.absence_minutes = day.unpaid_minutes
        day.status = "late" if day.late_minutes > 0 else "present"

        if weekly_off:
            day.status = "present"
            day.expected_work_minutes = 0
            day.normal_paid_minutes = 0
            day.unpaid_minutes = 0
            day.absence_minutes = 0
            day.overtime_minutes = actual_work_minutes

        if vacation:
            day.is_manually_corrected = True

    day.calculated_at = _utc_now()
    db.add(day)
    db.flush()

    for event in events:
        event.attendance_day_id = day.id
        db.add(event)

    _sync_payroll_after_attendance_change(day, db, trigger_reason)
    return day


def recalculate_attendance_for_employee(employee_id: int, start_date: date, end_date: date, db: Session) -> list[AttendanceDay]:
    _get_employee(employee_id, db)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    current = start_date
    days: list[AttendanceDay] = []
    while current <= end_date:
        days.append(calculate_attendance_day(employee_id, current, db, trigger_reason="manual_recalculation"))
        current += timedelta(days=1)

    db.commit()
    for day in days:
        db.refresh(day)
    return days


def create_attendance_correction(payload, db: Session):
    day = _get_or_create_attendance_day(payload.employee_id, payload.work_date, db)
    current_value = getattr(day, payload.field_changed, None)
    correction = AttendanceCorrection(
        attendance_day_id=day.id,
        employee_id=payload.employee_id,
        original_event_id=payload.original_event_id,
        field_changed=payload.field_changed,
        old_value=current_value.isoformat() if isinstance(current_value, time) else (str(current_value) if current_value is not None else None),
        new_value=payload.new_value,
        reason=payload.reason,
        corrected_by=payload.corrected_by,
    )
    db.add(correction)
    db.flush()

    updated_day = calculate_attendance_day(payload.employee_id, payload.work_date, db, trigger_reason="attendance_correction")
    save_audit_log(
        db,
        action="attendance_correction",
        entity_type="AttendanceCorrection",
        entity_id=correction.id,
        old_data_json={"field_changed": payload.field_changed, "old_value": correction.old_value},
        new_data_json={"new_value": payload.new_value, "reason": payload.reason},
        user_id=payload.corrected_by,
    )
    db.commit()
    db.refresh(correction)
    db.refresh(updated_day)
    return correction, updated_day


def get_attendance_day(employee_id: int, work_date: date, db: Session) -> AttendanceDay | None:
    return db.scalar(
        select(AttendanceDay)
        .options(selectinload(AttendanceDay.events))
        .where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date == work_date,
        )
    )


def get_attendance_days(employee_id: int, start_date: date, end_date: date, db: Session) -> list[AttendanceDay]:
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


def _sync_payroll_after_attendance_change(day: AttendanceDay, db: Session, trigger_reason: str):
    from app.services.payroll_calculation_service import sync_payroll_with_attendance_day

    sync_payroll_with_attendance_day(day, db, trigger_reason=trigger_reason)
