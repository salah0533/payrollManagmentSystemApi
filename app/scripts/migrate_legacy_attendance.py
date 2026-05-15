from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.attendence import Attendence
from app.models.attendance_payroll import AttendanceDay, AttendanceEvent
from app.models.types.attendenceTypes import AttendanceType
from app.services.attendance_calculation_service import (
    apply_smart_attendance_status_correction,
    calculate_attendance_day,
)
from app.services.policy_service import get_employee_schedule, get_schedule_timezone


def _event_exists(employee_id: int, event_type: str, event_time: datetime, db) -> bool:
    return db.scalar(
        select(AttendanceEvent.id).where(
            AttendanceEvent.employee_id == employee_id,
            AttendanceEvent.event_type == event_type,
            AttendanceEvent.event_time == event_time,
        )
    ) is not None


def migrate_legacy_attendance() -> dict[str, int]:
    db = SessionLocal()
    migrated = 0
    skipped = 0
    try:
        rows = db.scalars(select(Attendence).order_by(Attendence.date.asc(), Attendence.id.asc())).all()
        for row in rows:
            existing_day = db.scalar(
                select(AttendanceDay.id).where(
                    AttendanceDay.employee_id == row.employee_id,
                    AttendanceDay.work_date == row.date,
                )
            )
            if existing_day:
                skipped += 1
                continue

            if row.attendence_type in {AttendanceType.Absent, AttendanceType.PAID_VACATION, AttendanceType.Not_PAID_VACATION, AttendanceType.Sick_Leave}:
                target_status = {
                    AttendanceType.Absent: "absent",
                    AttendanceType.PAID_VACATION: "paid_vacation",
                    AttendanceType.Not_PAID_VACATION: "unpaid_vacation",
                    AttendanceType.Sick_Leave: "sick_leave",
                }[AttendanceType(row.attendence_type)]
                apply_smart_attendance_status_correction(
                    row.employee_id,
                    row.date,
                    target_status,
                    corrected_by=None,
                    reason=f"Legacy attendance migration from attendence#{row.id}",
                    options={"source": "legacy_migration", "legacy_attendance_id": row.id},
                    db=db,
                )
                migrated += 1
                continue

            schedule = get_employee_schedule(row.employee_id, row.date, db)
            schedule_timezone = get_schedule_timezone(schedule)
            if row.entry_time:
                check_in_at = datetime.combine(row.date, row.entry_time, tzinfo=schedule_timezone).astimezone(timezone.utc)
                if not _event_exists(row.employee_id, "check_in", check_in_at, db):
                    db.add(
                        AttendanceEvent(
                            employee_id=row.employee_id,
                            event_type="check_in",
                            event_time=check_in_at,
                            source="legacy_migration",
                            note=f"Migrated from attendence#{row.id}",
                        )
                    )
            if row.exit_time:
                check_out_at = datetime.combine(row.date, row.exit_time, tzinfo=schedule_timezone).astimezone(timezone.utc)
                if not _event_exists(row.employee_id, "check_out", check_out_at, db):
                    db.add(
                        AttendanceEvent(
                            employee_id=row.employee_id,
                            event_type="check_out",
                            event_time=check_out_at,
                            source="legacy_migration",
                            note=f"Migrated from attendence#{row.id}",
                        )
                    )
            db.flush()
            calculate_attendance_day(row.employee_id, row.date, db, trigger_reason="legacy_migration")
            db.commit()
            migrated += 1

        return {"migrated": migrated, "skipped": skipped}
    finally:
        db.close()


if __name__ == "__main__":
    result = migrate_legacy_attendance()
    print(result)
