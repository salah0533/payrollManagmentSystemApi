from __future__ import annotations

from datetime import date

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import utc_now
from app.models.auth import User
from app.models.employees import Employees
from app.schemas.user import EmployeeCreateRequest, EmployeeRead, EmployeeUpdateRequest, UserCreateRequest
from app.services.audit_service import save_audit_log, serialize_model
from app.services.user_service import create_user, serialize_employee


def _employee_query():
    return selectinload(Employees.user_account)


def get_employees(db: Session) -> list[EmployeeRead]:
    employees = db.scalars(
        select(Employees)
        .options(_employee_query())
        .where(Employees.deleted_at.is_(None))
        .order_by(Employees.created_at.asc(), Employees.id.asc())
    ).all()
    return [serialize_employee(employee) for employee in employees]


def get_employee(id: int, db: Session) -> EmployeeRead:
    employee = db.scalar(
        select(Employees).options(_employee_query()).where(Employees.id == id, Employees.deleted_at.is_(None))
    )
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return serialize_employee(employee)


def _sync_employee_fields(employee: Employees, payload: EmployeeCreateRequest | EmployeeUpdateRequest) -> None:
    data = payload.model_dump(exclude_unset=True, by_alias=False)

    if "first_name" in data and data["first_name"] is not None:
        employee.first_name = data["first_name"]
    if "last_name" in data and data["last_name"] is not None:
        employee.last_name = data["last_name"]

    employee.fullname = f"{employee.first_name} {employee.last_name}".strip()

    if "email" in data:
        employee.email = data["email"]
    if "phone" in data and data["phone"] is not None:
        employee.phone = data["phone"]
    if "department_id" in data:
        employee.department_id = data["department_id"]
    if "position" in data:
        employee.position = data["position"]
        if data["position"] is not None:
            employee.job_title = data["position"]
    elif not employee.position and employee.job_title:
        employee.position = employee.job_title

    if "status" in data and data["status"] is not None:
        employee.status = data["status"].value if hasattr(data["status"], "value") else str(data["status"])
        employee.is_active = employee.status == "active"
    elif not employee.status:
        employee.status = "active" if employee.is_active else "inactive"

    hire_date = data.get("hire_date", data.get("joined"))
    if hire_date is not None:
        employee.hire_date = hire_date
        employee.joined = hire_date
    else:
        employee.hire_date = employee.hire_date or employee.joined or date.today()
        employee.joined = employee.joined or employee.hire_date

    numeric_fields = (
        "dues",
        "salary_type",
        "monthly_price",
        "day_price",
        "hour_price",
        "extra_hours_price",
        "daily_work_hours",
        "vacation_days",
        "allowed_late",
        "min_extraTime",
    )
    for field_name in numeric_fields:
        if field_name in data and data[field_name] is not None:
            setattr(employee, field_name, data[field_name])


def add_employee(payload: EmployeeCreateRequest, db: Session, *, actor: User | None = None) -> EmployeeRead:
    employee = Employees(
        first_name=payload.first_name,
        last_name=payload.last_name,
        fullname="",
        job_title=payload.position or "Employee",
        phone=payload.phone,
        email=payload.email,
        department_id=payload.department_id,
        position=payload.position,
        status=payload.status.value if hasattr(payload.status, "value") else str(payload.status),
        hire_date=payload.hire_date or payload.joined or date.today(),
        dues=payload.dues,
        salary_type=payload.salary_type,
        monthly_price=payload.monthly_price,
        day_price=payload.day_price,
        hour_price=payload.hour_price,
        extra_hours_price=payload.extra_hours_price,
        vacation_days=payload.vacation_days,
        daily_work_hours=payload.daily_work_hours,
        is_active=payload.status.value == "active",
        allowed_late=payload.allowed_late,
        min_extraTime=payload.min_extraTime,
        joined=payload.hire_date or payload.joined or date.today(),
    )
    _sync_employee_fields(employee, payload)
    db.add(employee)
    db.flush()

    if payload.create_user_account:
        if actor is None or "admin" not in set(actor.active_role_codes):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can create linked user accounts")
        create_user(
            UserCreateRequest(
                username=payload.username or "",
                email=payload.user_email or payload.email,
                password=payload.password or "",
                employee_id=employee.id,
                role_ids=payload.role_ids,
                is_active=True,
                must_change_password=True,
            ),
            db,
            actor=actor,
        )

    db.flush()
    save_audit_log(
        db,
        action="employee_created",
        entity_type="Employee",
        entity_id=employee.id,
        new_data_json=serialize_model(employee),
        user_id=actor.id if actor else None,
    )
    db.commit()
    db.refresh(employee)
    return serialize_employee(employee)


def update_employee(employee_id: int, payload: EmployeeUpdateRequest, db: Session, *, actor: User | None = None) -> EmployeeRead:
    employee = db.scalar(select(Employees).options(_employee_query()).where(Employees.id == employee_id, Employees.deleted_at.is_(None)))
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    old_data = serialize_model(employee)
    _sync_employee_fields(employee, payload)
    db.add(employee)
    db.flush()
    save_audit_log(
        db,
        action="employee_updated",
        entity_type="Employee",
        entity_id=employee.id,
        old_data_json=old_data,
        new_data_json=serialize_model(employee),
        user_id=actor.id if actor else None,
    )
    db.commit()
    db.refresh(employee)
    return serialize_employee(employee)


def delete_employee(id: int, db: Session, *, actor: User | None = None) -> None:
    employee = db.scalar(select(Employees).options(_employee_query()).where(Employees.id == id, Employees.deleted_at.is_(None)))
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if employee.user_account and employee.user_account.deleted_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Employee has a linked user account. Disable or unlink the account before deleting the employee.",
        )

    old_data = serialize_model(employee)
    employee.deleted_at = utc_now()
    employee.status = "inactive"
    employee.is_active = False
    db.add(employee)
    db.flush()
    save_audit_log(
        db,
        action="employee_deleted",
        entity_type="Employee",
        entity_id=employee.id,
        old_data_json=old_data,
        new_data_json={"deleted_at": str(employee.deleted_at), "status": employee.status},
        user_id=actor.id if actor else None,
    )
    db.commit()
