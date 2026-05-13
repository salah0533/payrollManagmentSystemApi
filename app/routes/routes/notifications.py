from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_admin, require_permissions
from app.models.auth import Role, User, UserRole
from app.schemas.notifications import (
    NotificationDispatchRequest,
    NotificationHrSendPermissionUpdateRequest,
)
from app.services.notification_service import NotificationService


router = APIRouter()


@router.get("/")
def list_notifications(
    notification_type: str | None = None,
    priority: str | None = None,
    user_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("notifications.read_all")),
):
    service = NotificationService(db)
    return api_success(
        service.list_notifications(
            notification_type=notification_type,
            priority=priority,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/{notification_id}")
def get_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("notifications.read_all")),
):
    return api_success(NotificationService(db).get_notification_detail(notification_id=notification_id))


@router.post("/")
def send_notification(
    payload: NotificationDispatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("notifications.send")),
):
    service = NotificationService(db)
    notification = service.notify_users(
        user_ids=_resolve_manual_targets(service, payload.user_ids, payload.role_codes),
        notification_type=payload.notification_type.value,
        title=payload.title,
        message=payload.message,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        actor_user_id=current_user.id,
        priority=payload.priority.value,
        expires_at=payload.expires_at,
    )
    db.commit()
    return api_success(service.get_notification_detail(notification_id=notification.id), status_code=201)


@router.put("/permissions/hr-send")
def update_hr_send_permission(
    payload: NotificationHrSendPermissionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    status = NotificationService(db).set_hr_send_permission(enabled=payload.enabled)
    db.commit()
    return api_success(status)


def _resolve_manual_targets(service: NotificationService, user_ids: list[int], role_codes: list[str]) -> list[int]:
    resolved_user_ids = set(user_ids)
    if role_codes:
        role_codes = [code.strip().lower() for code in role_codes if code and code.strip()]
        role_user_ids = service.db.scalars(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.code.in_(role_codes),
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        ).all()
        resolved_user_ids.update(role_user_ids)
    return sorted(resolved_user_ids)
