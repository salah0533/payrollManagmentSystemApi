from fastapi import APIRouter, Depends
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_permissions
from app.models.attendance_payroll import AuditLog
from app.models.auth import Role, User, UserRole
from app.models.employees import Employees
from app.schemas.attendance_payroll import AuditLogPageRead, AuditLogRead


router = APIRouter()


def _audit_user_load_options():
    return (
        joinedload(AuditLog.user).joinedload(User.employee),
        joinedload(AuditLog.user).selectinload(User.user_roles).joinedload(UserRole.role),
    )


def _user_load_options():
    return (
        joinedload(User.employee),
        selectinload(User.user_roles).joinedload(UserRole.role),
    )


def _serialize_audit_user(user: User | None) -> dict | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "employee_id": user.employee_id,
        "employee_name": user.employee.fullname if user.employee else None,
        "roles": sorted({item.role.code for item in user.user_roles if item.role is not None}),
    }


def _serialize_audit_employee(employee: Employees | None) -> dict | None:
    if employee is None:
        return None
    return {
        "id": employee.id,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "full_name": employee.fullname,
        "email": employee.email,
        "phone": employee.phone,
        "position": employee.position or employee.job_title,
        "status": employee.status,
        "user_id": employee.user_account.id if employee.user_account else None,
    }


def _build_entity_label(entity_type: str, entity_id: int | None, entity_user: User | None, entity_employee: Employees | None) -> str | None:
    if entity_employee is not None:
        return entity_employee.fullname
    if entity_user is not None:
        return entity_user.employee.fullname if entity_user.employee else entity_user.username
    if entity_id is None:
        return None
    return f"{entity_type} #{entity_id}"


def _user_search_clause(search_pattern: str):
    return or_(
        cast(User.id, String).like(search_pattern),
        cast(User.employee_id, String).like(search_pattern),
        func.lower(func.coalesce(User.username, "")).like(search_pattern),
        func.lower(func.coalesce(User.email, "")).like(search_pattern),
        User.employee.has(
            or_(
                func.lower(func.coalesce(Employees.fullname, "")).like(search_pattern),
                func.lower(func.coalesce(Employees.first_name, "")).like(search_pattern),
                func.lower(func.coalesce(Employees.last_name, "")).like(search_pattern),
                func.lower(func.coalesce(Employees.email, "")).like(search_pattern),
                func.lower(func.coalesce(Employees.phone, "")).like(search_pattern),
                func.lower(func.coalesce(Employees.position, "")).like(search_pattern),
                func.lower(func.coalesce(Employees.job_title, "")).like(search_pattern),
            )
        ),
    )


def _employee_search_clause(search_pattern: str):
    return or_(
        cast(Employees.id, String).like(search_pattern),
        func.lower(func.coalesce(Employees.fullname, "")).like(search_pattern),
        func.lower(func.coalesce(Employees.first_name, "")).like(search_pattern),
        func.lower(func.coalesce(Employees.last_name, "")).like(search_pattern),
        func.lower(func.coalesce(Employees.email, "")).like(search_pattern),
        func.lower(func.coalesce(Employees.phone, "")).like(search_pattern),
        func.lower(func.coalesce(Employees.position, "")).like(search_pattern),
        func.lower(func.coalesce(Employees.job_title, "")).like(search_pattern),
    )


def _build_search_filter(search: str):
    search_pattern = f"%{search.strip().lower()}%"
    matching_user_ids = select(User.id).where(_user_search_clause(search_pattern))
    matching_employee_ids = select(Employees.id).where(_employee_search_clause(search_pattern))
    return or_(
        cast(AuditLog.id, String).like(search_pattern),
        cast(AuditLog.user_id, String).like(search_pattern),
        cast(AuditLog.entity_id, String).like(search_pattern),
        func.lower(func.coalesce(AuditLog.action, "")).like(search_pattern),
        func.lower(func.coalesce(AuditLog.entity_type, "")).like(search_pattern),
        func.lower(func.coalesce(AuditLog.ip_address, "")).like(search_pattern),
        func.lower(cast(AuditLog.old_data_json, String)).like(search_pattern),
        func.lower(cast(AuditLog.new_data_json, String)).like(search_pattern),
        AuditLog.user.has(_user_search_clause(search_pattern)),
        and_(func.lower(AuditLog.entity_type) == "user", AuditLog.entity_id.in_(matching_user_ids)),
        and_(func.lower(AuditLog.entity_type) == "employee", AuditLog.entity_id.in_(matching_employee_ids)),
    )


@router.get("/")
def list_audit_logs(
    page: int = 1,
    page_size: int = 150,
    action: list[str] | None = None,
    entity_type: list[str] | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("audit.read")),
):
    resolved_page = max(1, int(page or 1))
    resolved_page_size = max(1, min(int(page_size or 150), 500))
    filters = []

    if action:
        filters.append(AuditLog.action.in_(action))
    if entity_type:
        filters.append(AuditLog.entity_type.in_(entity_type))
    if actor_user_id is not None:
        filters.append(AuditLog.user_id == actor_user_id)
    if actor_role == "system":
        filters.append(AuditLog.user_id.is_(None))
    elif actor_role:
        filters.append(
            AuditLog.user.has(
                User.user_roles.any(
                    UserRole.role.has(Role.code == actor_role)
                )
            )
        )
    if search and search.strip():
        filters.append(_build_search_filter(search))

    total_records = db.scalar(select(func.count()).select_from(AuditLog).where(*filters)) or 0
    total_pages = max(1, (int(total_records) + resolved_page_size - 1) // resolved_page_size)
    if resolved_page > total_pages:
        resolved_page = total_pages

    statement = (
        select(AuditLog)
        .where(*filters)
        .options(*_audit_user_load_options())
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((resolved_page - 1) * resolved_page_size)
        .limit(resolved_page_size)
    )
    rows = db.execute(statement).scalars().all()

    user_entity_ids = sorted(
        {
            row.entity_id
            for row in rows
            if row.entity_id is not None and str(row.entity_type or "").strip().lower() == "user"
        }
    )
    employee_entity_ids = sorted(
        {
            row.entity_id
            for row in rows
            if row.entity_id is not None and str(row.entity_type or "").strip().lower() == "employee"
        }
    )

    entity_users = {
        user.id: user
        for user in db.execute(
            select(User)
            .where(User.id.in_(user_entity_ids))
            .options(*_user_load_options())
        ).scalars().all()
    } if user_entity_ids else {}
    entity_employees = {
        employee.id: employee
        for employee in db.scalars(
            select(Employees)
            .where(Employees.id.in_(employee_entity_ids))
            .options(joinedload(Employees.user_account))
        ).all()
    } if employee_entity_ids else {}

    items = []
    for row in rows:
        normalized_entity_type = str(row.entity_type or "").strip().lower()
        entity_user = entity_users.get(row.entity_id) if normalized_entity_type == "user" and row.entity_id is not None else None
        entity_employee = entity_employees.get(row.entity_id) if normalized_entity_type == "employee" and row.entity_id is not None else None
        items.append(
            AuditLogRead.model_validate(
                {
                    "id": row.id,
                    "user_id": row.user_id,
                    "action": row.action,
                    "entity_type": row.entity_type,
                    "entity_id": row.entity_id,
                    "old_data_json": row.old_data_json,
                    "new_data_json": row.new_data_json,
                    "ip_address": row.ip_address,
                    "user_agent": row.user_agent,
                    "created_at": row.created_at,
                    "actor": _serialize_audit_user(row.user),
                    "entity_label": _build_entity_label(row.entity_type, row.entity_id, entity_user, entity_employee),
                    "entity_employee": _serialize_audit_employee(entity_employee),
                    "entity_user": _serialize_audit_user(entity_user),
                }
            )
        )

    return api_success(
        AuditLogPageRead(
            page=resolved_page,
            page_size=resolved_page_size,
            total_records=int(total_records),
            total_pages=total_pages,
            items=items,
        )
    )
