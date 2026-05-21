from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.auth import User
from app.models.attendance_payroll import AttendanceDay, EmployeePayroll
from app.models.employees import Employees
from app.services.payroll_calculation_service import get_payroll_balance_report


def get_deleted_employee_history_health(db: Session) -> dict[str, int | list[int]]:
    deleted_employee_ids = set(
        db.scalars(select(Employees.id).where(Employees.deleted_at.is_not(None))).all()
    )
    active_report = get_payroll_balance_report(db, include_archived=False)
    active_report_employee_ids = {
        int(row["employee_id"])
        for row in active_report.get("employees", [])
    }

    return {
        "payroll_rows_for_deleted_employees": int(
            db.scalar(
                select(func.count(EmployeePayroll.id))
                .join(Employees, EmployeePayroll.employee_id == Employees.id)
                .where(Employees.deleted_at.is_not(None))
            )
            or 0
        ),
        "attendance_rows_for_deleted_employees": int(
            db.scalar(
                select(func.count(AttendanceDay.id))
                .join(Employees, AttendanceDay.employee_id == Employees.id)
                .where(Employees.deleted_at.is_not(None))
            )
            or 0
        ),
        "active_users_linked_to_deleted_employees": int(
            db.scalar(
                select(func.count(User.id))
                .join(Employees, User.employee_id == Employees.id)
                .where(
                    Employees.deleted_at.is_not(None),
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                )
            )
            or 0
        ),
        "deleted_employees_visible_in_operational_payroll_reports": sorted(
            deleted_employee_ids.intersection(active_report_employee_ids)
        ),
    }


def main() -> None:
    db = SessionLocal()
    try:
        print(json.dumps(get_deleted_employee_history_health(db), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
