from __future__ import annotations

from datetime import time
from decimal import Decimal

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.attendance_payroll import PayrollPolicy, WorkSchedule
from app.models.attendence_types import AttendenceTypes
from app.models.auth import Permission, Role, RolePermission, User, UserRole
from app.models.payment_types import PaymentTypes
from app.models.salary_type import SalaryType
from app.models.settings import Settings
from app.models.vacation_status import VacationStatus
from app.models.vacation_types import VacationTypes
from app.utility.reference_codes import (
    ATTENDANCE_EVENT_TYPE_CODES,
    ATTENDANCE_STATUS_CODES,
    DEFAULT_ROLE_PERMISSIONS,
    EMPLOYEE_PAYROLL_STATUS_CODES,
    PAYMENT_TYPE_CODES,
    PAYROLL_ADJUSTMENT_TYPE_CODES,
    PAYROLL_DISCREPANCY_STATUS_CODES,
    PAYROLL_DISCREPANCY_TYPE_CODES,
    PAYROLL_PERIOD_STATUS_CODES,
    PERMISSION_DEFINITIONS,
    ROLE_DEFINITIONS,
    SALARY_TYPE_CODES,
    VACATION_STATUS_CODES,
    VACATION_TYPE_CODES,
)


def _table_exists(db: Session, table_name: str) -> bool:
    return inspect(db.bind).has_table(table_name)


def _upsert_model(db: Session, model, lookup: dict, defaults: dict | None = None):
    defaults = defaults or {}
    instance = db.scalar(select(model).filter_by(**lookup))
    created = False
    updated = False
    if instance is None:
        instance = model(**{**lookup, **defaults})
        db.add(instance)
        db.flush()
        created = True
        print(f"created {model.__tablename__}: {lookup}")
        return instance, created, updated

    changed = []
    for key, value in defaults.items():
        if getattr(instance, key, None) != value:
            setattr(instance, key, value)
            changed.append(key)
    if changed:
        db.add(instance)
        db.flush()
        updated = True
        print(f"updated {model.__tablename__}: {lookup} ({', '.join(changed)})")
    else:
        print(f"exists {model.__tablename__}: {lookup}")
    return instance, created, updated


def _report_constant_codes(group_name: str, codes: tuple[str, ...] | list[str]):
    print(f"constants {group_name}: {', '.join(codes)}")


def seed_roles(db: Session) -> dict[str, Role]:
    if not _table_exists(db, "roles"):
        print("roles table not found; skipped role seeding")
        return {}
    roles: dict[str, Role] = {}
    for row in ROLE_DEFINITIONS:
        role, _, _ = _upsert_model(
            db,
            Role,
            {"code": row["code"]},
            {
                "name": row["name"],
                "description": row["description"],
                "is_system_role": row["is_system_role"],
            },
        )
        roles[row["code"]] = role
    return roles


def seed_permissions(db: Session) -> dict[str, Permission]:
    if not _table_exists(db, "permissions"):
        print("permissions table not found; skipped permission seeding")
        return {}
    permissions: dict[str, Permission] = {}
    for row in PERMISSION_DEFINITIONS:
        permission, _, _ = _upsert_model(
            db,
            Permission,
            {"code": row["code"]},
            {
                "name": row["name"],
                "description": row["description"],
                "module": row["module"],
            },
        )
        permissions[row["code"]] = permission
    return permissions


def seed_role_permissions(db: Session, roles: dict[str, Role], permissions: dict[str, Permission]) -> None:
    if not roles or not permissions or not _table_exists(db, "role_permissions"):
        print("role_permissions table not found or no roles/permissions available; skipped role permission seeding")
        return

    for role_code, permission_codes in DEFAULT_ROLE_PERMISSIONS.items():
        role = roles[role_code]
        for permission_code in permission_codes:
            permission = permissions[permission_code]
            existing = db.scalar(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == permission.id,
                )
            )
            if existing:
                continue
            db.add(RolePermission(role_id=role.id, permission_id=permission.id))
            db.flush()
            print(f"created role_permissions: role={role_code}, permission={permission_code}")


def seed_salary_types(db: Session):
    if not _table_exists(db, "salary_type"):
        print("salary_type table not found; skipped salary type seeding")
        return
    rows = [
        {"id": 0, "code": "monthly", "salary_type": "monthly"},
        {"id": 1, "code": "daily", "salary_type": "daily"},
        {"id": 2, "code": "hourly", "salary_type": "hourly"},
    ]
    for row in rows:
        _upsert_model(db, SalaryType, {"code": row["code"]}, {"id": row["id"], "salary_type": row["salary_type"]})


def seed_attendance_types_or_statuses(db: Session):
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
        _upsert_model(db, AttendenceTypes, {"code": row["code"]}, {"id": row["id"], "attendence_type": row["attendence_type"]})


def seed_payroll_reference_data(db: Session):
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
            _upsert_model(db, PaymentTypes, {"code": row["code"]}, {"id": row["id"], "payment_type": row["payment_type"]})
    else:
        print("payment_types table not found; skipped legacy payment type seeding")

    if _table_exists(db, "payroll_policy"):
        _upsert_model(
            db,
            PayrollPolicy,
            {"name": "default"},
            {
                "payroll_cycle": "monthly",
                "minimum_overtime_minutes": 30,
                "minimum_auto_pay_minutes": 0,
                "allowed_late_minutes": 0,
                "default_currency": "DZD",
                "significant_change_threshold": Decimal("1.00"),
                "paid_vacation_counts_for_daily": True,
                "overtime_enabled": True,
                "late_makeup_enabled": True,
                "late_deduction_enabled": False,
                "auto_recalculate_draft_payroll": True,
                "lock_payroll_after_payment": True,
                "holidays_json": [],
                "annual_vacation_days_by_year": {},
                "allow_vacation_carryover": True,
                "max_vacation_carryover_days": None,
                "carryover_expiry_month": None,
                "carryover_expiry_day": None,
                "reserve_vacation_days_on_pending": False,
            },
        )
    else:
        print("payroll_policy table not found; skipped payroll policy seeding")


def seed_vacation_reference_data(db: Session):
    if _table_exists(db, "vacation_types"):
        rows = [
            {"id": 0, "code": "paid", "vacation_type": "paid"},
            {"id": 1, "code": "unpaid", "vacation_type": "unpaid"},
            {"id": 2, "code": "sick", "vacation_type": "sick"},
            {"id": 3, "code": "emergency", "vacation_type": "emergency"},
        ]
        for row in rows:
            _upsert_model(db, VacationTypes, {"code": row["code"]}, {"id": row["id"], "vacation_type": row["vacation_type"]})
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
            _upsert_model(db, VacationStatus, {"code": row["code"]}, {"id": row["id"], "vacation_status": row["vacation_status"]})
    else:
        print("vacation_status table not found; skipped vacation status seeding")

    _report_constant_codes("vacation_type_codes", VACATION_TYPE_CODES)
    _report_constant_codes("vacation_status_codes", VACATION_STATUS_CODES)


def seed_default_settings_or_schedule(db: Session):
    if _table_exists(db, "settings"):
        _upsert_model(
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
        existing_default = db.scalar(select(WorkSchedule).where(WorkSchedule.is_default.is_(True)).order_by(WorkSchedule.id))
        lookup = {"id": existing_default.id} if existing_default else {"name": "Default Schedule"}
        _upsert_model(
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


def seed_default_admin(db: Session, roles: dict[str, Role]) -> None:
    if not roles or not _table_exists(db, "users") or not _table_exists(db, "user_roles"):
        print("user auth tables not found; skipped default admin seeding")
        return

    admin_role = roles["admin"]
    existing_admin = db.scalar(
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .where(
            User.deleted_at.is_(None),
            UserRole.role_id == admin_role.id,
        )
        .order_by(User.id.asc())
    )
    if existing_admin:
        print("admin user already exists; skipped default admin creation")
        return

    candidate = db.scalar(
        select(User).where(
            User.deleted_at.is_(None),
            (User.username == settings.default_admin_username) | (User.email == settings.default_admin_email),
        )
    )
    if candidate:
        print(f"promoting existing user {candidate.username} to admin")
        candidate.is_active = True
        candidate.must_change_password = True
        db.add(candidate)
        db.flush()
        if not db.scalar(select(UserRole).where(UserRole.user_id == candidate.id, UserRole.role_id == admin_role.id)):
            db.add(UserRole(user_id=candidate.id, role_id=admin_role.id))
            db.flush()
        return

    password = settings.default_admin_password
    user = User(
        username=settings.default_admin_username,
        email=settings.default_admin_email,
        password_hash=get_password_hash(password),
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=admin_role.id))
    db.flush()
    print("created default admin account")
    if password == "admin":
        print("WARNING: Default admin password is 'admin'. Change it immediately after first login.")


def main():
    db = SessionLocal()
    try:
        roles = seed_roles(db)
        permissions = seed_permissions(db)
        seed_role_permissions(db, roles, permissions)
        seed_salary_types(db)
        seed_attendance_types_or_statuses(db)
        seed_payroll_reference_data(db)
        seed_vacation_reference_data(db)
        seed_default_settings_or_schedule(db)
        seed_default_admin(db, roles)
        db.commit()
        print("seed completed successfully")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
