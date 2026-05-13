from __future__ import annotations

from datetime import time
from decimal import Decimal

from sqlalchemy import inspect, select

from app.db.session import SessionLocal
from app.models.attendance_payroll import PayrollPolicy, WorkSchedule
from app.models.attendence_types import AttendenceTypes
from app.models.payment_types import PaymentTypes
from app.models.salary_type import SalaryType
from app.models.settings import Settings
from app.models.vacation_status import VacationStatus
from app.models.vacation_types import VacationTypes
from app.utility.reference_codes import (
    ATTENDANCE_EVENT_TYPE_CODES,
    ATTENDANCE_STATUS_CODES,
    DEFAULT_ROLE_CODES,
    EMPLOYEE_PAYROLL_STATUS_CODES,
    PAYMENT_TYPE_CODES,
    PAYROLL_ADJUSTMENT_TYPE_CODES,
    PAYROLL_DISCREPANCY_STATUS_CODES,
    PAYROLL_DISCREPANCY_TYPE_CODES,
    PAYROLL_PERIOD_STATUS_CODES,
    SALARY_TYPE_CODES,
    VACATION_STATUS_CODES,
    VACATION_TYPE_CODES,
)


def _table_exists(db, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def _label_for(model) -> str:
    return getattr(model, "__tablename__", model.__name__)


def _describe(instance, lookup: dict) -> str:
    if hasattr(instance, "code") and getattr(instance, "code", None):
        return getattr(instance, "code")
    if "code" in lookup:
        return str(lookup["code"])
    if "id" in lookup:
        return f"id={lookup['id']}"
    return ", ".join(f"{key}={value}" for key, value in lookup.items())


def get_or_create(db, model, lookup: dict, defaults: dict | None = None):
    defaults = defaults or {}
    instance = db.scalar(select(model).filter_by(**lookup))
    created = False
    updated = False

    if instance is None and "code" in lookup and hasattr(model, "code"):
        instance = db.scalar(select(model).filter_by(code=lookup["code"]))
    if instance is None and "id" in lookup:
        instance = db.get(model, lookup["id"])
    if instance is None and "id" in defaults:
        instance = db.get(model, defaults["id"])
    if instance is None:
        for field_name in (
            "salary_type",
            "attendence_type",
            "payment_type",
            "vacation_type",
            "vacation_status",
            "name",
        ):
            if field_name in defaults and hasattr(model, field_name):
                instance = db.scalar(select(model).filter_by(**{field_name: defaults[field_name]}))
                if instance is not None:
                    break

    if instance is None:
        instance = model(**{**lookup, **defaults})
        db.add(instance)
        db.flush()
        created = True
        print(f"created {_label_for(model)}: {_describe(instance, lookup)}")
        return instance, created, updated

    changed_fields = []
    for key, value in {**lookup, **defaults}.items():
        if key == "id":
            continue
        if getattr(instance, key, None) != value:
            setattr(instance, key, value)
            changed_fields.append(key)
    if changed_fields:
        db.add(instance)
        db.flush()
        updated = True
        print(f"updated {_label_for(model)}: {_describe(instance, lookup)} ({', '.join(changed_fields)})")
    else:
        print(f"exists {_label_for(model)}: {_describe(instance, lookup)}")
    return instance, created, updated


def _report_constant_codes(group_name: str, codes: tuple[str, ...] | list[str]):
    print(f"constants {group_name}: {', '.join(codes)}")


def seed_roles(db):
    print("roles table not present; keeping role codes in application constants")
    _report_constant_codes("roles", DEFAULT_ROLE_CODES)


def seed_salary_types(db):
    if not _table_exists(db, "salary_type"):
        print("salary_type table not found; skipped salary type seeding")
        return

    rows = [
        {"id": 0, "code": "monthly", "salary_type": "monthly"},
        {"id": 1, "code": "daily", "salary_type": "daily"},
        {"id": 2, "code": "hourly", "salary_type": "hourly"},
    ]
    for row in rows:
        lookup = {"code": row["code"]}
        defaults = {"id": row["id"], "salary_type": row["salary_type"]}
        get_or_create(db, SalaryType, lookup, defaults)


def seed_attendance_types_or_statuses(db):
    _report_constant_codes("attendance_event_types", ATTENDANCE_EVENT_TYPE_CODES)
    _report_constant_codes("attendance_status_codes", ATTENDANCE_STATUS_CODES)

    if not _table_exists(db, "attendence_types"):
        print("attendence_types table not found; skipped attendance lookup seeding")
        return

    rows = [
        {"id": 0, "code": "present", "attendence_type": "present"},
        {"id": 1, "code": "late", "attendence_type": "late"},
        {"id": 2, "code": "absent", "attendence_type": "absent"},
        {"id": 3, "code": "overtime", "attendence_type": "overtime"},
        {"id": 4, "code": "paid_vacation", "attendence_type": "paid_vacation"},
        {"id": 5, "code": "unpaid_vacation", "attendence_type": "unpaid_vacation"},
        {"id": 6, "code": "sick_leave", "attendence_type": "sick_leave"},
        {"id": 7, "code": "incomplete", "attendence_type": "incomplete"},
        {"id": 8, "code": "weekly_off", "attendence_type": "weekly_off"},
        {"id": 9, "code": "holiday", "attendence_type": "holiday"},
        {"id": 10, "code": "manually_corrected", "attendence_type": "manually_corrected"},
    ]
    for row in rows:
        lookup = {"code": row["code"]}
        defaults = {"id": row["id"], "attendence_type": row["attendence_type"]}
        get_or_create(db, AttendenceTypes, lookup, defaults)


def seed_payroll_reference_data(db):
    _report_constant_codes("payroll_period_status_codes", PAYROLL_PERIOD_STATUS_CODES)
    _report_constant_codes("employee_payroll_status_codes", EMPLOYEE_PAYROLL_STATUS_CODES)
    _report_constant_codes("payroll_adjustment_type_codes", PAYROLL_ADJUSTMENT_TYPE_CODES)
    _report_constant_codes("payroll_discrepancy_type_codes", PAYROLL_DISCREPANCY_TYPE_CODES)
    _report_constant_codes("payroll_discrepancy_status_codes", PAYROLL_DISCREPANCY_STATUS_CODES)

    if _table_exists(db, "payment_types"):
        rows = [
            {"id": 0, "code": "payment", "payment_type": "payment"},
            {"id": 1, "code": "bonus", "payment_type": "bonus"},
            {"id": 2, "code": "deduction", "payment_type": "deduction"},
            {"id": 3, "code": "attendance", "payment_type": "attendance"},
        ]
        for row in rows:
            lookup = {"code": row["code"]}
            defaults = {"id": row["id"], "payment_type": row["payment_type"]}
            get_or_create(db, PaymentTypes, lookup, defaults)
    else:
        print("payment_types table not found; skipped legacy payment type seeding")

    if _table_exists(db, "payroll_policy"):
        get_or_create(
            db,
            PayrollPolicy,
            {"name": "default"},
            {
                "payroll_cycle": "monthly",
                "minimum_overtime_minutes": 30,
                "allowed_late_minutes": 0,
                "default_currency": "USD",
                "significant_change_threshold": Decimal("1.00"),
                "paid_vacation_counts_for_daily": True,
                "overtime_enabled": True,
                "late_makeup_enabled": True,
                "late_deduction_enabled": True,
                "auto_recalculate_draft_payroll": True,
                "lock_payroll_after_payment": True,
                "holidays_json": [],
            },
        )
    else:
        print("payroll_policy table not found; skipped payroll policy seeding")


def seed_vacation_reference_data(db):
    if _table_exists(db, "vacation_types"):
        rows = [
            {"id": 0, "code": "paid", "vacation_type": "paid"},
            {"id": 1, "code": "unpaid", "vacation_type": "unpaid"},
            {"id": 2, "code": "sick", "vacation_type": "sick"},
            {"id": 3, "code": "emergency", "vacation_type": "emergency"},
        ]
        for row in rows:
            lookup = {"code": row["code"]}
            defaults = {"id": row["id"], "vacation_type": row["vacation_type"]}
            get_or_create(db, VacationTypes, lookup, defaults)
    else:
        print("vacation_types table not found; skipped vacation type seeding")

    if _table_exists(db, "vacation_status"):
        rows = [
            {"id": 0, "code": "pending", "vacation_status": "pending"},
            {"id": 1, "code": "approved", "vacation_status": "approved"},
            {"id": 2, "code": "cancelled", "vacation_status": "cancelled"},
            {"id": 3, "code": "rejected", "vacation_status": "rejected"},
        ]
        for row in rows:
            lookup = {"code": row["code"]}
            defaults = {"id": row["id"], "vacation_status": row["vacation_status"]}
            get_or_create(db, VacationStatus, lookup, defaults)
    else:
        print("vacation_status table not found; skipped vacation status seeding")

    _report_constant_codes("vacation_type_codes", VACATION_TYPE_CODES)
    _report_constant_codes("vacation_status_codes", VACATION_STATUS_CODES)


def seed_default_settings_or_schedule(db):
    if _table_exists(db, "settings"):
        get_or_create(
            db,
            Settings,
            {"id": 1},
            {
                "entry_time": time(hour=8, minute=0),
                "exit_time": time(hour=17, minute=0),
            },
        )
    else:
        print("settings table not found; skipped legacy settings seeding")

    if _table_exists(db, "work_schedule"):
        existing_default = db.scalar(
            select(WorkSchedule).where(WorkSchedule.is_default.is_(True)).order_by(WorkSchedule.id)
        )
        lookup = {"id": existing_default.id} if existing_default else {"name": "Default Schedule"}
        get_or_create(
            db,
            WorkSchedule,
            lookup,
            {
                "name": "Default Schedule",
                "start_time": time(hour=8, minute=0),
                "end_time": time(hour=17, minute=0),
                "break_minutes": 60,
                "weekly_off_days": ["friday", "saturday"],
                "timezone": "Africa/Algiers",
                "is_default": True,
            },
        )
    else:
        print("work_schedule table not found; skipped work schedule seeding")


def main():
    db = SessionLocal()
    try:
        seed_roles(db)
        seed_salary_types(db)
        seed_attendance_types_or_statuses(db)
        seed_payroll_reference_data(db)
        seed_vacation_reference_data(db)
        seed_default_settings_or_schedule(db)
        db.commit()
        print("seed completed successfully")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
