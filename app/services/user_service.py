from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_password_hash
from app.exceptions.base_exception import BadRequestException, ConflictException, ResourceNotFoundException
from app.models.auth import Permission, Role, RolePermission, User, UserRole
from app.models.employees import Employees
from app.schemas.auth import AuthMeEmployee, AuthMeResponse
from app.schemas.user import EmployeeRead, PermissionRead, RoleRead, UserCreateRequest, UserRead, UserResetPasswordRequest, UserUpdateRequest
from app.services.audit_service import save_audit_log, serialize_model
from app.services.notification_service import NotificationService


class ResourceConflictException(ConflictException):
    pass


def get_resource_or_404(resource, *, resource_name: str, identifier: int | None = None):
    if not resource:
        raise ResourceNotFoundException(resource_name, identifier)
    return resource


def _user_loader():
    return (
        selectinload(User.employee),
        selectinload(User.user_roles)
        .selectinload(UserRole.role)
        .selectinload(Role.role_permissions)
        .selectinload(RolePermission.permission),
    )


def get_user_or_404(user_id: int, db: Session) -> User:
    return get_resource_or_404(
        db.scalar(select(User).options(*_user_loader()).where(User.id == user_id, User.deleted_at.is_(None))),
        resource_name="User",
        identifier=user_id,
    )


def get_employee_or_404(employee_id: int, db: Session) -> Employees:
    return get_resource_or_404(
        db.scalar(select(Employees).where(Employees.id == employee_id, Employees.deleted_at.is_(None))),
        resource_name="Employee",
        identifier=employee_id,
    )


def get_role_or_404(role_id: int, db: Session) -> Role:
    return get_resource_or_404(
        db.scalar(
        select(Role)
        .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
        .where(Role.id == role_id)
        ),
        resource_name="Role",
        identifier=role_id,
    )


def get_user_by_identifier(identifier: str, db: Session) -> User | None:
    return db.scalar(
        select(User)
        .options(*_user_loader())
        .where(
            User.deleted_at.is_(None),
            or_(func.lower(User.username) == identifier.lower(), func.lower(User.email) == identifier.lower()),
        )
    )


def _ensure_unique_username(username: str, db: Session, *, exclude_user_id: int | None = None) -> None:
    statement = select(User.id).where(func.lower(User.username) == username.lower(), User.deleted_at.is_(None))
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    if db.scalar(statement):
        raise ResourceConflictException("Username already exists", code="username_already_exists")


def _ensure_unique_email(email: str | None, db: Session, *, exclude_user_id: int | None = None) -> None:
    if not email:
        return
    statement = select(User.id).where(func.lower(User.email) == email.lower(), User.deleted_at.is_(None))
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    if db.scalar(statement):
        raise ResourceConflictException("Email already exists", code="email_already_exists")


def _ensure_employee_link_available(employee_id: int | None, db: Session, *, exclude_user_id: int | None = None) -> None:
    if employee_id is None:
        return
    get_employee_or_404(employee_id, db)
    statement = select(User.id).where(
        User.employee_id == employee_id,
        User.deleted_at.is_(None),
    )
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    if db.scalar(statement):
        raise ResourceConflictException(
            "This employee already has an active user account",
            code="employee_already_linked",
        )


def _serialize_permission(permission: Permission) -> PermissionRead:
    return PermissionRead(
        id=permission.id,
        code=permission.code,
        name=permission.name,
        description=permission.description,
        module=permission.module,
    )


def _serialize_role(role: Role) -> RoleRead:
    permissions = sorted(
        (mapping.permission for mapping in role.role_permissions if mapping.permission is not None),
        key=lambda item: item.code,
    )
    return RoleRead(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system_role=role.is_system_role,
        permissions=[_serialize_permission(permission) for permission in permissions],
    )


def serialize_user(user: User) -> UserRead:
    roles = sorted((item.role for item in user.user_roles if item.role is not None), key=lambda role: role.code)
    return UserRead(
        id=user.id,
        employee_id=user.employee_id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
        roles=[_serialize_role(role) for role in roles],
    )


def serialize_employee(employee: Employees) -> EmployeeRead:
    return EmployeeRead(
        id=employee.id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        full_name=employee.fullname,
        email=employee.email,
        phone=employee.phone,
        department_id=employee.department_id,
        position=employee.position,
        status=employee.status,
        hire_date=employee.hire_date,
        dues=employee.dues,
        salary_type=employee.salary_type,
        monthly_price=employee.monthly_price,
        day_price=employee.day_price,
        hour_price=employee.hour_price,
        extra_hours_price=employee.extra_hours_price,
        vacation_days=employee.vacation_days,
        daily_work_hours=employee.daily_work_hours,
        allowed_late=employee.allowed_late,
        min_extraTime=employee.min_extraTime,
        is_active=employee.is_active,
        created_at=employee.created_at,
        updated_at=employee.updated_at,
        user_id=employee.user_account.id if employee.user_account else None,
    )


def serialize_auth_me(user: User) -> AuthMeResponse:
    employee = None
    if user.employee:
        employee = AuthMeEmployee(
            id=user.employee.id,
            first_name=user.employee.first_name,
            last_name=user.employee.last_name,
            full_name=user.employee.fullname,
            email=user.employee.email,
            position=user.employee.position,
            status=user.employee.status,
        )
    return AuthMeResponse(
        id=user.id,
        employee_id=user.employee_id,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        roles=user.active_role_codes,
        permissions=user.active_permission_codes,
        employee=employee,
    )


def list_users(db: Session) -> list[UserRead]:
    users = db.scalars(
        select(User)
        .options(*_user_loader())
        .where(User.deleted_at.is_(None))
        .order_by(User.created_at.asc(), User.id.asc())
    ).all()
    return [serialize_user(user) for user in users]


def _get_role_assignments(role_ids: list[int], db: Session) -> list[Role]:
    roles = [get_role_or_404(role_id, db) for role_id in role_ids]
    if not roles:
        raise BadRequestException("At least one role is required")
    return roles


def _validate_employee_role_policy(employee_id: int | None, roles: list[Role]) -> None:
    if any(role.code == "employee" for role in roles) and employee_id is None:
        raise BadRequestException(
            "employee role requires the user to be linked to an employee profile",
            code="employee_role_requires_profile",
        )


def create_user(payload: UserCreateRequest, db: Session, *, actor: User | None = None) -> UserRead:
    _ensure_unique_username(payload.username, db)
    _ensure_unique_email(payload.email, db)
    _ensure_employee_link_available(payload.employee_id, db)
    roles = _get_role_assignments(payload.role_ids, db)
    _validate_employee_role_policy(payload.employee_id, roles)

    user = User(
        employee_id=payload.employee_id,
        username=payload.username,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        is_active=payload.is_active,
        must_change_password=payload.must_change_password,
    )
    db.add(user)
    db.flush()

    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.flush()
    db.refresh(user)
    user = get_user_or_404(user.id, db)

    save_audit_log(
        db,
        action="user_created",
        entity_type="User",
        entity_id=user.id,
        new_data_json={"username": user.username, "email": user.email, "roles": user.active_role_codes},
        user_id=actor.id if actor else None,
    )
    notification_service = NotificationService(db)
    notification_service.notify_user(
        user_id=user.id,
        notification_type="account_created",
        title="Account created",
        message="Your employee management account is ready to use.",
        entity_type="user",
        entity_id=user.id,
        actor_user_id=actor.id if actor else None,
        priority="normal",
    )
    if user.must_change_password:
        notification_service.notify_user(
            user_id=user.id,
            notification_type="must_change_password",
            title="Password change required",
            message="You must change your password before accessing the rest of the app.",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id if actor else None,
            priority="high",
        )
    db.commit()
    return serialize_user(user)


def update_user(user_id: int, payload: UserUpdateRequest, db: Session, *, actor: User | None = None) -> UserRead:
    user = get_user_or_404(user_id, db)
    old_data = serialize_model(user, fields=("username", "email", "employee_id", "is_active", "must_change_password"))
    old_must_change_password = user.must_change_password
    values = payload.model_dump(exclude_unset=True)

    if "username" in values and values["username"] is not None:
        _ensure_unique_username(values["username"], db, exclude_user_id=user.id)
        user.username = values["username"]
    if "email" in values:
        _ensure_unique_email(values["email"], db, exclude_user_id=user.id)
        user.email = values["email"]
    if "employee_id" in values:
        _ensure_employee_link_available(values["employee_id"], db, exclude_user_id=user.id)
        user.employee_id = values["employee_id"]
    if "must_change_password" in values:
        user.must_change_password = values["must_change_password"]
    if values.get("is_active") is False:
        _ensure_not_last_active_admin(user, db)
    if "is_active" in values and values["is_active"] is not None:
        user.is_active = values["is_active"]

    current_roles = [item.role for item in user.user_roles if item.role is not None]
    _validate_employee_role_policy(user.employee_id, current_roles)

    db.add(user)
    db.flush()
    save_audit_log(
        db,
        action="user_updated",
        entity_type="User",
        entity_id=user.id,
        old_data_json=old_data,
        new_data_json=serialize_model(user, fields=("username", "email", "employee_id", "is_active", "must_change_password")),
        user_id=actor.id if actor else None,
    )
    if not old_must_change_password and user.must_change_password:
        NotificationService(db).notify_user(
            user_id=user.id,
            notification_type="must_change_password",
            title="Password change required",
            message="An administrator requires you to change your password before continuing.",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id if actor else None,
            priority="high",
        )
    db.commit()
    return serialize_user(get_user_or_404(user.id, db))


def _count_active_admins(db: Session, *, exclude_user_id: int | None = None) -> int:
    statement = (
        select(func.count(User.id))
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            User.deleted_at.is_(None),
            User.is_active.is_(True),
            Role.code == "admin",
        )
    )
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return int(db.scalar(statement) or 0)


def _ensure_not_last_active_admin(user: User, db: Session) -> None:
    role_codes = set(user.active_role_codes)
    if "admin" not in role_codes:
        return
    if user.is_active and _count_active_admins(db, exclude_user_id=user.id) == 0:
        raise ResourceConflictException("Cannot deactivate the last active admin", code="last_active_admin")


def activate_user(user_id: int, db: Session, *, actor: User | None = None) -> UserRead:
    user = get_user_or_404(user_id, db)
    user.is_active = True
    db.add(user)
    db.flush()
    save_audit_log(db, action="user_activated", entity_type="User", entity_id=user.id, user_id=actor.id if actor else None)
    db.commit()
    return serialize_user(get_user_or_404(user.id, db))


def deactivate_user(user_id: int, db: Session, *, actor: User | None = None) -> UserRead:
    user = get_user_or_404(user_id, db)
    _ensure_not_last_active_admin(user, db)
    user.is_active = False
    db.add(user)
    db.flush()
    save_audit_log(db, action="user_disabled", entity_type="User", entity_id=user.id, user_id=actor.id if actor else None)
    db.commit()
    return serialize_user(get_user_or_404(user.id, db))


def assign_roles(user_id: int, role_ids: list[int], db: Session, *, actor: User | None = None) -> UserRead:
    user = get_user_or_404(user_id, db)
    roles = _get_role_assignments(role_ids, db)
    _validate_employee_role_policy(user.employee_id, roles + [item.role for item in user.user_roles if item.role is not None])

    existing_role_ids = {item.role_id for item in user.user_roles}
    added_codes: list[str] = []
    for role in roles:
        if role.id in existing_role_ids:
            continue
        db.add(UserRole(user_id=user.id, role_id=role.id))
        added_codes.append(role.code)
    db.flush()
    save_audit_log(
        db,
        action="role_assigned",
        entity_type="User",
        entity_id=user.id,
        new_data_json={"roles_added": added_codes},
        user_id=actor.id if actor else None,
    )
    db.commit()
    return serialize_user(get_user_or_404(user.id, db))


def remove_role(user_id: int, role_id: int, db: Session, *, actor: User | None = None) -> UserRead:
    user = get_user_or_404(user_id, db)
    mapping = next((item for item in user.user_roles if item.role_id == role_id), None)
    if not mapping:
        raise ResourceNotFoundException("Role assignment")
    role = mapping.role or get_role_or_404(role_id, db)

    if role.code == "admin" and user.is_active and _count_active_admins(db, exclude_user_id=user.id) == 0:
        raise ResourceConflictException("Cannot remove the last active admin role", code="last_active_admin_role")

    remaining_roles = [item.role for item in user.user_roles if item.role_id != role_id and item.role is not None]
    _validate_employee_role_policy(user.employee_id, remaining_roles)

    db.delete(mapping)
    db.flush()
    save_audit_log(
        db,
        action="role_removed",
        entity_type="User",
        entity_id=user.id,
        old_data_json={"role_removed": role.code},
        user_id=actor.id if actor else None,
    )
    db.commit()
    return serialize_user(get_user_or_404(user.id, db))


def reset_password(user_id: int, payload: UserResetPasswordRequest, db: Session, *, actor: User | None = None) -> UserRead:
    user = get_user_or_404(user_id, db)
    user.password_hash = get_password_hash(payload.new_password)
    user.must_change_password = payload.must_change_password
    db.add(user)
    db.flush()
    save_audit_log(
        db,
        action="password_reset",
        entity_type="User",
        entity_id=user.id,
        new_data_json={"must_change_password": payload.must_change_password},
        user_id=actor.id if actor else None,
    )
    notification_service = NotificationService(db)
    if payload.must_change_password:
        notification_service.notify_user(
            user_id=user.id,
            notification_type="must_change_password",
            title="Password reset",
            message="Your password was reset. You must change it at your next login.",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id if actor else None,
            priority="high",
        )
    else:
        notification_service.notify_user(
            user_id=user.id,
            notification_type="password_changed",
            title="Password reset",
            message="Your password was reset by an administrator.",
            entity_type="user",
            entity_id=user.id,
            actor_user_id=actor.id if actor else None,
            priority="normal",
        )
    db.commit()
    return serialize_user(get_user_or_404(user.id, db))
