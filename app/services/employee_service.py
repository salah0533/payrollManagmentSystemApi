from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import utc_now
from app.exceptions.base_exception import ForbiddenException
from app.models.auth import User
from app.models.attendance_payroll import EmployeeCompensation
from app.models.employee_reference import Department, Position
from app.models.employees import Employees
from app.schemas.user import EmployeeCompensationRead, EmployeeCreateRequest, EmployeeRead, EmployeeUpdateRequest, UserCreateRequest
from app.services.auto_attendance_service import resolve_auto_attendance_effective_from
from app.services.audit_service import save_audit_log, serialize_model
from app.services.policy_service import SALARY_TYPE_MAP, get_default_work_schedule, get_or_create_payroll_policy
from app.services.user_service import ResourceConflictException, get_resource_or_404, verify_admin_password_or_raise
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
    employee = get_resource_or_404(
        db.scalar(select(Employees).options(_employee_query()).where(Employees.id == id, Employees.deleted_at.is_(None))),
        resource_name="Employee",
    )
    return serialize_employee(employee)


def _get_department_or_404(department_id: int, db: Session) -> Department:
    return get_resource_or_404(
        db.scalar(select(Department).where(Department.id == department_id, Department.is_active.is_(True))),
        resource_name="Department",
        identifier=department_id,
    )


def _get_position_or_404(position_id: int, db: Session) -> Position:
    return get_resource_or_404(
        db.scalar(select(Position).where(Position.id == position_id, Position.is_active.is_(True))),
        resource_name="Position",
        identifier=position_id,
    )


def _legacy_attendance_defaults(db: Session) -> dict[str, Decimal | int]:
    schedule = get_default_work_schedule(db)
    policy = get_or_create_payroll_policy(db)
    scheduled_minutes = max(
        0,
        (
            (schedule.end_time.hour * 60 + schedule.end_time.minute)
            - (schedule.start_time.hour * 60 + schedule.start_time.minute)
            - int(schedule.break_minutes or 0)
        ),
    )
    daily_work_hours = max(1, scheduled_minutes // 60) if scheduled_minutes else 8
    return {
        "daily_work_hours": daily_work_hours,
        "allowed_late": Decimal(str(max(0, int(policy.allowed_late_minutes or 0)))),
        "min_extraTime": Decimal(str(max(0, int(policy.minimum_overtime_minutes or 0)))),
    }


def _normalize_employee_compensation_prices(employee: Employees) -> None:
    salary_type = SALARY_TYPE_MAP.get(employee.salary_type, "monthly")
    if salary_type == "monthly":
        employee.day_price = Decimal("0.00")
        employee.hour_price = Decimal("0.00")
    elif salary_type == "daily":
        employee.monthly_price = Decimal("0.00")
        employee.hour_price = Decimal("0.00")
    elif salary_type == "hourly":
        employee.monthly_price = Decimal("0.00")
        employee.day_price = Decimal("0.00")


def _sync_employee_fields(employee: Employees, payload: EmployeeCreateRequest | EmployeeUpdateRequest, db: Session) -> None:
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
        if data["department_id"] is not None:
            _get_department_or_404(data["department_id"], db)
        employee.department_id = data["department_id"]
    if "position_id" in data:
        if data["position_id"] is not None:
            position = _get_position_or_404(data["position_id"], db)
            employee.position = position.name
            employee.job_title = position.name
        elif "position" in data:
            employee.position = data["position"]
            if data["position"] is not None:
                employee.job_title = data["position"]
        employee.position_id = data["position_id"]
    if "position" in data and "position_id" not in data:
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
        "vacation_days",
    )
    for field_name in numeric_fields:
        if field_name in data and data[field_name] is not None:
            setattr(employee, field_name, data[field_name])

    _normalize_employee_compensation_prices(employee)


def _sync_employee_auto_attendance(
    employee: Employees,
    payload: EmployeeCreateRequest | EmployeeUpdateRequest,
    db: Session,
) -> None:
    data = payload.model_dump(exclude_unset=True, by_alias=False)
    if "auto_attendance_enabled" in data and data["auto_attendance_enabled"] is not None:
        employee.auto_attendance_enabled = bool(data["auto_attendance_enabled"])

    if not employee.auto_attendance_enabled or not employee.is_active:
        employee.auto_attendance_effective_from = None
        return

    if "auto_attendance_enabled" in data or employee.auto_attendance_effective_from is None:
        employee.auto_attendance_effective_from = resolve_auto_attendance_effective_from(employee.id, db)


def _build_employee_compensation_values(employee: Employees, db: Session) -> dict[str, Decimal | str | date | bool | int | None]:
    policy = get_or_create_payroll_policy(db)
    salary_type = SALARY_TYPE_MAP.get(employee.salary_type, "monthly")
    monthly_price = Decimal(str(employee.monthly_price or 0))
    day_price = Decimal(str(employee.day_price or 0))
    hour_price = Decimal(str(employee.hour_price or 0))
    extra_hours_price = Decimal(str(employee.extra_hours_price or 0))

    if salary_type == "monthly":
        daily_rate = Decimal("0.00")
        hourly_rate = Decimal("0.00")
        late_deduction_rate = Decimal("0.00")
    else:
        daily_rate = day_price
        hourly_rate = hour_price
        late_deduction_rate = (hour_price / Decimal("60")) if hour_price else Decimal("0.00")

    return {
        "employee_id": employee.id,
        "salary_type": salary_type,
        "base_monthly_salary": monthly_price,
        "daily_rate": daily_rate,
        "hourly_rate": hourly_rate,
        "overtime_rate": extra_hours_price,
        "late_deduction_rate": late_deduction_rate,
        "daily_rate_override": None,
        "hourly_rate_override": None,
        "overtime_rate_override": None,
        "late_deduction_rate_override": None,
        "currency": policy.default_currency,
        "effective_from": employee.hire_date or employee.joined or date.today(),
        "effective_to": None,
        "is_active": True,
    }


def _compensation_fields_equal(compensation: EmployeeCompensation, values: dict[str, Decimal | str | date | bool | int | None]) -> bool:
    comparable_fields = (
        "salary_type",
        "base_monthly_salary",
        "daily_rate",
        "hourly_rate",
        "overtime_rate",
        "late_deduction_rate",
        "daily_rate_override",
        "hourly_rate_override",
        "overtime_rate_override",
        "late_deduction_rate_override",
        "currency",
    )
    for field_name in comparable_fields:
        if getattr(compensation, field_name) != values[field_name]:
            return False
    return True


def _sync_employee_compensation_record(
    employee: Employees,
    db: Session,
    *,
    actor: User | None = None,
    effective_from: date | None = None,
) -> EmployeeCompensation:
    values = _build_employee_compensation_values(employee, db)
    effective_date = effective_from or date.today()
    values["effective_from"] = effective_date

    latest = db.scalar(
        select(EmployeeCompensation)
        .where(EmployeeCompensation.employee_id == employee.id)
        .order_by(EmployeeCompensation.effective_from.desc(), EmployeeCompensation.id.desc())
    )

    if latest and _compensation_fields_equal(latest, values):
        if latest.effective_to is None or latest.effective_to >= effective_date:
            latest.is_active = True
        db.add(latest)
        db.flush()
        return latest

    if latest and latest.effective_from == effective_date:
        old_data = serialize_model(latest)
        for key, value in values.items():
            setattr(latest, key, value)
        latest.created_by = actor.id if actor else latest.created_by
        db.add(latest)
        db.flush()
        save_audit_log(
            db,
            action="employee_compensation_updated",
            entity_type="EmployeeCompensation",
            entity_id=latest.id,
            old_data_json=old_data,
            new_data_json=serialize_model(latest),
            user_id=actor.id if actor else None,
        )
        return latest

    if latest and latest.effective_to is None and latest.effective_from < effective_date:
        latest.effective_to = effective_date - timedelta(days=1)
        latest.is_active = False
        db.add(latest)

    compensation = EmployeeCompensation(
        **values,
        created_at=utc_now(),
        created_by=actor.id if actor else None,
    )
    db.add(compensation)
    db.flush()
    save_audit_log(
        db,
        action="employee_compensation_created",
        entity_type="EmployeeCompensation",
        entity_id=compensation.id,
        new_data_json=serialize_model(compensation),
        user_id=actor.id if actor else None,
    )
    return compensation


def get_employee_compensation_history(employee_id: int, db: Session) -> list[EmployeeCompensationRead]:
    employee = get_resource_or_404(
        db.scalar(select(Employees).where(Employees.id == employee_id, Employees.deleted_at.is_(None))),
        resource_name="Employee",
        identifier=employee_id,
    )

    if not db.scalar(select(EmployeeCompensation.id).where(EmployeeCompensation.employee_id == employee_id)):
        _sync_employee_compensation_record(
            employee,
            db,
            effective_from=employee.hire_date or employee.joined or date.today(),
        )
        db.commit()

    rows = db.scalars(
        select(EmployeeCompensation)
        .where(EmployeeCompensation.employee_id == employee_id)
        .order_by(EmployeeCompensation.effective_from.desc(), EmployeeCompensation.id.desc())
    ).all()
    return [EmployeeCompensationRead.model_validate(row) for row in rows]


def add_employee(payload: EmployeeCreateRequest, db: Session, *, actor: User | None = None) -> EmployeeRead:
    legacy_defaults = _legacy_attendance_defaults(db)
    employee = Employees(
        first_name=payload.first_name,
        last_name=payload.last_name,
        fullname="",
        job_title=payload.position or "Employee",
        phone=payload.phone,
        email=payload.email,
        department_id=payload.department_id,
        position_id=payload.position_id,
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
        auto_attendance_enabled=False,
        auto_attendance_effective_from=None,
        daily_work_hours=int(legacy_defaults["daily_work_hours"]),
        is_active=payload.status.value == "active",
        allowed_late=legacy_defaults["allowed_late"],
        min_extraTime=legacy_defaults["min_extraTime"],
        joined=payload.hire_date or payload.joined or date.today(),
    )
    _sync_employee_fields(employee, payload, db)
    db.add(employee)
    db.flush()
    _sync_employee_auto_attendance(employee, payload, db)
    _sync_employee_compensation_record(
        employee,
        db,
        actor=actor,
        effective_from=employee.hire_date or employee.joined or date.today(),
    )
    db.flush()

    if payload.create_user_account:
        if actor is None or "admin" not in set(actor.active_role_codes):
            raise ForbiddenException("Only admins can create linked user accounts", message_key="errors.forbidden")
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
    employee = get_resource_or_404(
        db.scalar(select(Employees).options(_employee_query()).where(Employees.id == employee_id, Employees.deleted_at.is_(None))),
        resource_name="Employee",
        identifier=employee_id,
    )

    old_data = serialize_model(employee)
    previous_due_balance = employee.dues
    previous_compensation_state = {
        "salary_type": employee.salary_type,
        "monthly_price": employee.monthly_price,
        "day_price": employee.day_price,
        "hour_price": employee.hour_price,
        "extra_hours_price": employee.extra_hours_price,
    }
    _sync_employee_fields(employee, payload, db)
    _sync_employee_auto_attendance(employee, payload, db)
    db.add(employee)
    db.flush()
    compensation_changed = any(
        getattr(employee, key) != previous_compensation_state[key]
        for key in previous_compensation_state
    )
    if compensation_changed:
        _sync_employee_compensation_record(employee, db, actor=actor, effective_from=date.today())
        from app.services.payroll_calculation_service import reconcile_existing_payrolls_for_employee_compensation_change

        reconcile_existing_payrolls_for_employee_compensation_change(
            employee.id,
            db,
            reason="employee_compensation_updated",
            created_by=actor.id if actor else None,
        )
    if employee.dues != previous_due_balance:
        from app.services.payroll_calculation_service import reconcile_existing_payrolls_for_employee_due_change

        reconcile_existing_payrolls_for_employee_due_change(
            employee.id,
            db,
            reason="employee_due_balance_updated",
            created_by=actor.id if actor else None,
        )
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


def delete_employee(id: int, db: Session, *, admin_password: str | None = None, actor: User | None = None) -> None:
    verify_admin_password_or_raise(actor, admin_password)
    employee = get_resource_or_404(
        db.scalar(select(Employees).options(_employee_query()).where(Employees.id == id, Employees.deleted_at.is_(None))),
        resource_name="Employee",
        identifier=id,
    )
    linked_user = employee.user_account
    if linked_user and linked_user.deleted_at is None:
        raise ResourceConflictException(
            "Employee has a linked user account. Delete or unlink the account before deleting the employee.",
            code="employee_has_linked_user_account",
            message_key="errors.employee_already_linked",
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
