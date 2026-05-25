from __future__ import annotations
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session, selectinload

from app.models.attendance_payroll import AuditLog
from app.models.auth import Role, User, UserRole
from app.models.employees import Employees
from app.schemas.attendance_payroll import AuditEmployeeSummaryRead, AuditLogPageRead, AuditLogRead, AuditUserSummaryRead


def serialize_model(instance, *, fields: Iterable[str] | None = None) -> dict:
    mapper = sa_inspect(instance.__class__)
    allowed = set(fields) if fields else None
    payload: dict = {}
    for column in mapper.columns:
        if allowed is not None and column.key not in allowed:
            continue
        value = getattr(instance, column.key)
        if isinstance(value, Decimal):
            payload[column.key] = str(value)
        elif hasattr(value, "value"):
            payload[column.key] = value.value
        elif hasattr(value, "isoformat"):
            payload[column.key] = value.isoformat()
        else:
            payload[column.key] = value
    return payload


def save_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_data_json: dict | None = None,
    new_data_json: dict | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_data_json=old_data_json,
        new_data_json=new_data_json,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.flush()
    return log


def _serialize_audit_user(user: User | None) -> AuditUserSummaryRead | None:
    if user is None:
        return None

    return AuditUserSummaryRead(
        id=user.id,
        username=user.username,
        email=user.email,
        employee_id=user.employee_id,
        employee_name=user.employee.fullname if user.employee else None,
        roles=sorted(user.active_role_codes),
    )


def _serialize_audit_employee(employee: Employees | None) -> AuditEmployeeSummaryRead | None:
    if employee is None:
        return None

    return AuditEmployeeSummaryRead(
        id=employee.id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        full_name=employee.fullname,
        email=employee.email,
        phone=employee.phone,
        position=employee.position,
        status=employee.status,
        user_id=employee.user_account.id if employee.user_account else None,
    )


def _snapshot_entity_label(log: AuditLog) -> str | None:
    snapshots = [log.new_data_json, log.old_data_json]
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        for key in ("fullname", "full_name", "username", "name", "title"):
            value = snapshot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if log.entity_id is not None:
        return f"{log.entity_type} #{log.entity_id}"
    return log.entity_type


def _snapshot_employee(log: AuditLog) -> AuditEmployeeSummaryRead | None:
    snapshots = [log.new_data_json, log.old_data_json]
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        full_name = snapshot.get("fullname") or snapshot.get("full_name")
        first_name = snapshot.get("first_name")
        last_name = snapshot.get("last_name")
        employee_id = snapshot.get("id", log.entity_id)
        if employee_id is None:
            continue
        return AuditEmployeeSummaryRead(
            id=int(employee_id),
            first_name=str(first_name) if first_name is not None else None,
            last_name=str(last_name) if last_name is not None else None,
            full_name=str(full_name).strip() if isinstance(full_name, str) and full_name.strip() else None,
            email=str(snapshot.get("email")).strip() if isinstance(snapshot.get("email"), str) and str(snapshot.get("email")).strip() else None,
            phone=str(snapshot.get("phone")).strip() if isinstance(snapshot.get("phone"), str) and str(snapshot.get("phone")).strip() else None,
            position=str(snapshot.get("position")).strip() if isinstance(snapshot.get("position"), str) and str(snapshot.get("position")).strip() else None,
            status=str(snapshot.get("status")).strip() if isinstance(snapshot.get("status"), str) and str(snapshot.get("status")).strip() else None,
            user_id=int(snapshot["user_id"]) if snapshot.get("user_id") is not None else None,
        )
    return None


def _snapshot_user(log: AuditLog) -> AuditUserSummaryRead | None:
    snapshots = [log.new_data_json, log.old_data_json]
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        username = snapshot.get("username")
        user_id = snapshot.get("id", log.entity_id)
        if user_id is None or not isinstance(username, str) or not username.strip():
            continue
        roles_value = snapshot.get("roles")
        roles = sorted(str(role).strip() for role in roles_value if str(role).strip()) if isinstance(roles_value, list) else []
        return AuditUserSummaryRead(
            id=int(user_id),
            username=username.strip(),
            email=str(snapshot.get("email")).strip() if isinstance(snapshot.get("email"), str) and str(snapshot.get("email")).strip() else None,
            employee_id=int(snapshot["employee_id"]) if snapshot.get("employee_id") is not None else None,
            employee_name=None,
            roles=roles,
        )
    return None


def _load_employee_map(db: Session, employee_ids: set[int]) -> dict[int, Employees]:
    if not employee_ids:
        return {}
    rows = db.scalars(
        select(Employees)
        .options(selectinload(Employees.user_account))
        .where(Employees.id.in_(employee_ids))
    ).all()
    return {employee.id: employee for employee in rows}


def _load_user_map(db: Session, user_ids: set[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    rows = db.scalars(
        select(User)
        .options(
            selectinload(User.employee),
            selectinload(User.user_roles).selectinload(UserRole.role),
        )
        .where(User.id.in_(user_ids))
    ).all()
    return {user.id: user for user in rows}


def _iter_audit_search_values(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_audit_search_values(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_audit_search_values(item)
        return
    if isinstance(value, Decimal):
        yield str(value)
        return
    if hasattr(value, "isoformat"):
        yield value.isoformat()
        return
    yield str(value)


def _matches_audit_search(row: AuditLogRead, search: str) -> bool:
    haystacks = [
        row.action,
        row.entity_type,
        row.entity_label,
        row.ip_address,
        row.user_agent,
        row.actor.username if row.actor else None,
        row.actor.email if row.actor else None,
        row.actor.employee_name if row.actor else None,
        row.entity_employee.full_name if row.entity_employee else None,
        row.entity_employee.email if row.entity_employee else None,
        row.entity_employee.phone if row.entity_employee else None,
        row.entity_employee.position if row.entity_employee else None,
        row.entity_user.username if row.entity_user else None,
        row.entity_user.email if row.entity_user else None,
        row.entity_user.employee_name if row.entity_user else None,
    ]

    for value in haystacks:
        if isinstance(value, str) and search in value.lower():
            return True

    for payload in (row.old_data_json, row.new_data_json):
        for value in _iter_audit_search_values(payload):
            if search in value.lower():
                return True

    return False


def list_audit_logs(
    db: Session,
    *,
    limit: int | None = 100,
    actions: list[str] | None = None,
    entity_types: list[str] | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    search: str | None = None,
) -> list[AuditLogRead]:
    normalized_actions = [value.strip() for value in (actions or []) if value and value.strip()]
    normalized_entity_types = [value.strip() for value in (entity_types or []) if value and value.strip()]
    normalized_actor_role = actor_role.strip().lower() if actor_role and actor_role.strip() else None
    normalized_search = search.strip().lower() if search and search.strip() else None

    statement = select(AuditLog).options(
        selectinload(AuditLog.user).selectinload(User.employee),
        selectinload(AuditLog.user).selectinload(User.user_roles).selectinload(UserRole.role),
    )

    if normalized_actions:
        statement = statement.where(AuditLog.action.in_(normalized_actions))
    if normalized_entity_types:
        statement = statement.where(AuditLog.entity_type.in_(normalized_entity_types))
    if actor_user_id is not None:
        statement = statement.where(AuditLog.user_id == actor_user_id)
    if normalized_actor_role:
        if normalized_actor_role == "system":
            statement = statement.where(AuditLog.user_id.is_(None))
        else:
            statement = (
                statement.join(AuditLog.user)
                .join(User.user_roles)
                .join(UserRole.role)
                .where(Role.code == normalized_actor_role)
                .distinct()
            )

    ordered_statement = statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if limit is not None:
        ordered_statement = ordered_statement.limit(max(1, min(limit, 500)))

    rows = db.scalars(ordered_statement).all()

    employee_entity_ids = {
        int(row.entity_id)
        for row in rows
        if row.entity_id is not None and str(row.entity_type or "").strip().lower() == "employee"
    }
    user_entity_ids = {
        int(row.entity_id)
        for row in rows
        if row.entity_id is not None and str(row.entity_type or "").strip().lower() == "user"
    }

    employee_map = _load_employee_map(db, employee_entity_ids)
    user_map = _load_user_map(db, user_entity_ids)

    audit_rows: list[AuditLogRead] = []
    for row in rows:
        normalized_entity_type = str(row.entity_type or "").strip().lower()
        entity_employee = (
            _serialize_audit_employee(employee_map.get(int(row.entity_id)))
            if row.entity_id is not None and normalized_entity_type == "employee"
            else None
        )
        entity_user = (
            _serialize_audit_user(user_map.get(int(row.entity_id)))
            if row.entity_id is not None and normalized_entity_type == "user"
            else None
        )
        if entity_employee is None and normalized_entity_type == "employee":
            entity_employee = _snapshot_employee(row)
        if entity_user is None and normalized_entity_type == "user":
            entity_user = _snapshot_user(row)

        entity_label = (
            entity_employee.full_name
            if entity_employee and entity_employee.full_name
            else entity_user.employee_name
            if entity_user and entity_user.employee_name
            else entity_user.username
            if entity_user
            else _snapshot_entity_label(row)
        )

        audit_rows.append(
            AuditLogRead(
                id=row.id,
                user_id=row.user_id,
                action=row.action,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                old_data_json=row.old_data_json if isinstance(row.old_data_json, dict) else row.old_data_json,
                new_data_json=row.new_data_json if isinstance(row.new_data_json, dict) else row.new_data_json,
                ip_address=row.ip_address,
                user_agent=row.user_agent,
                created_at=row.created_at,
                actor=_serialize_audit_user(row.user),
                entity_label=entity_label,
                entity_employee=entity_employee,
                entity_user=entity_user,
            )
        )

    if normalized_search:
        audit_rows = [row for row in audit_rows if _matches_audit_search(row, normalized_search)]

    if limit is not None:
        return audit_rows[: max(1, min(limit, 500))]

    return audit_rows


def get_audit_log_page(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 100,
    actions: list[str] | None = None,
    entity_types: list[str] | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    search: str | None = None,
) -> AuditLogPageRead:
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 100), 500))
    rows = list_audit_logs(
        db,
        limit=None,
        actions=actions,
        entity_types=entity_types,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        search=search,
    )
    total_records = len(rows)
    total_pages = (total_records + safe_page_size - 1) // safe_page_size if total_records else 0
    offset = (safe_page - 1) * safe_page_size if total_records else 0
    return AuditLogPageRead(
        page=safe_page,
        page_size=safe_page_size,
        total_records=total_records,
        total_pages=total_pages,
        items=rows[offset : offset + safe_page_size],
    )
