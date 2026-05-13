from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions.base_exception import BadRequestException, ResourceNotFoundException
from app.models.auth import Permission, Role, RolePermission, User, UserRole
from app.models.notifications import Notification, NotificationRecipient
from app.schemas.notifications import (
    NotificationAdminListRead,
    NotificationAdminRead,
    NotificationDetailRead,
    NotificationPermissionStatusRead,
    NotificationRecipientStateRead,
    UserNotificationListRead,
    UserNotificationRead,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def notify_user(
        self,
        *,
        user_id: int,
        notification_type: str,
        title: str,
        message: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        actor_user_id: int | None = None,
        priority: str = "normal",
        expires_at: datetime | None = None,
        skip_if_no_recipients: bool = False,
    ) -> Notification | None:
        return self.notify_users(
            user_ids=[user_id],
            notification_type=notification_type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            priority=priority,
            expires_at=expires_at,
            skip_if_no_recipients=skip_if_no_recipients,
        )

    def notify_users(
        self,
        *,
        user_ids: list[int],
        notification_type: str,
        title: str,
        message: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        actor_user_id: int | None = None,
        priority: str = "normal",
        expires_at: datetime | None = None,
        skip_if_no_recipients: bool = False,
    ) -> Notification | None:
        recipient_ids = self._get_active_user_ids(user_ids)
        if not recipient_ids:
            if skip_if_no_recipients:
                return None
            raise BadRequestException("No active notification recipients were found")

        notification = Notification(
            notification_type=notification_type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            priority=priority,
            expires_at=expires_at,
        )
        self.db.add(notification)
        self.db.flush()

        for recipient_id in recipient_ids:
            self.db.add(NotificationRecipient(notification_id=notification.id, user_id=recipient_id))
        self.db.flush()
        self.db.refresh(notification)
        return notification

    def notify_role(
        self,
        *,
        role_codes: list[str],
        notification_type: str,
        title: str,
        message: str,
        entity_type: str | None = None,
        entity_id: int | None = None,
        actor_user_id: int | None = None,
        priority: str = "normal",
        expires_at: datetime | None = None,
        skip_if_no_recipients: bool = False,
    ) -> Notification | None:
        role_codes = [code.strip().lower() for code in role_codes if code and code.strip()]
        if not role_codes:
            raise BadRequestException("At least one role code is required")

        user_ids = self.db.scalars(
            select(User.id)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.code.in_(role_codes),
                User.deleted_at.is_(None),
                User.is_active.is_(True),
            )
        ).all()
        return self.notify_users(
            user_ids=list(user_ids),
            notification_type=notification_type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_user_id=actor_user_id,
            priority=priority,
            expires_at=expires_at,
            skip_if_no_recipients=skip_if_no_recipients,
        )

    def get_user_notifications(
        self,
        *,
        user_id: int,
        unread_only: bool = False,
        is_archived: bool = False,
        include_expired: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> UserNotificationListRead:
        stmt = (
            select(NotificationRecipient)
            .join(Notification, Notification.id == NotificationRecipient.notification_id)
            .options(selectinload(NotificationRecipient.notification))
            .where(NotificationRecipient.user_id == user_id)
        )
        count_stmt = (
            select(func.count(NotificationRecipient.id))
            .join(Notification, Notification.id == NotificationRecipient.notification_id)
            .where(NotificationRecipient.user_id == user_id)
        )
        stmt, count_stmt = self._apply_user_filters(
            stmt,
            count_stmt,
            unread_only=unread_only,
            is_archived=is_archived,
            include_expired=include_expired,
        )

        total = int(self.db.scalar(count_stmt) or 0)
        recipients = self.db.scalars(
            stmt.order_by(Notification.created_at.desc(), NotificationRecipient.id.desc()).offset(offset).limit(limit)
        ).all()
        return UserNotificationListRead(
            items=[self._serialize_user_notification(item) for item in recipients],
            total=total,
            unread_count=self.get_unread_count(user_id=user_id),
            limit=limit,
            offset=offset,
        )

    def get_unread_count(self, *, user_id: int) -> int:
        now = _utc_now()
        return int(
            self.db.scalar(
                select(func.count(NotificationRecipient.id))
                .join(Notification, Notification.id == NotificationRecipient.notification_id)
                .where(
                    NotificationRecipient.user_id == user_id,
                    NotificationRecipient.is_read.is_(False),
                    NotificationRecipient.is_archived.is_(False),
                    or_(Notification.expires_at.is_(None), Notification.expires_at > now),
                )
            )
            or 0
        )

    def mark_as_read(self, *, user_id: int, notification_id: str) -> UserNotificationRead:
        recipient = self._get_user_recipient(user_id=user_id, notification_id=notification_id)
        if not recipient.is_read:
            recipient.is_read = True
            recipient.read_at = _utc_now()
            self.db.add(recipient)
            self.db.flush()
        return self._serialize_user_notification(recipient)

    def mark_all_as_read(self, *, user_id: int) -> int:
        now = _utc_now()
        recipients = self.db.scalars(
            select(NotificationRecipient)
            .join(Notification, Notification.id == NotificationRecipient.notification_id)
            .where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.is_read.is_(False),
                NotificationRecipient.is_archived.is_(False),
                or_(Notification.expires_at.is_(None), Notification.expires_at > now),
            )
        ).all()
        for recipient in recipients:
            recipient.is_read = True
            recipient.read_at = now
            self.db.add(recipient)
        self.db.flush()
        return len(recipients)

    def archive_notification(self, *, user_id: int, notification_id: str) -> UserNotificationRead:
        recipient = self._get_user_recipient(user_id=user_id, notification_id=notification_id)
        if not recipient.is_archived:
            recipient.is_archived = True
            recipient.archived_at = _utc_now()
            if not recipient.is_read:
                recipient.is_read = True
                recipient.read_at = recipient.archived_at
            self.db.add(recipient)
            self.db.flush()
        return self._serialize_user_notification(recipient)

    def list_notifications(
        self,
        *,
        notification_type: str | None = None,
        priority: str | None = None,
        user_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NotificationAdminListRead:
        stmt = (
            select(Notification)
            .options(selectinload(Notification.recipients).selectinload(NotificationRecipient.user))
            .order_by(Notification.created_at.desc(), Notification.id.desc())
        )
        count_stmt = select(func.count(func.distinct(Notification.id)))

        if user_id is not None:
            stmt = stmt.join(NotificationRecipient, NotificationRecipient.notification_id == Notification.id).where(NotificationRecipient.user_id == user_id).distinct()
            count_stmt = count_stmt.select_from(Notification).join(
                NotificationRecipient, NotificationRecipient.notification_id == Notification.id
            ).where(NotificationRecipient.user_id == user_id)
        else:
            count_stmt = count_stmt.select_from(Notification)

        if notification_type:
            stmt = stmt.where(Notification.notification_type == notification_type)
            count_stmt = count_stmt.where(Notification.notification_type == notification_type)
        if priority:
            stmt = stmt.where(Notification.priority == priority)
            count_stmt = count_stmt.where(Notification.priority == priority)

        total = int(self.db.scalar(count_stmt) or 0)
        notifications = self.db.scalars(stmt.offset(offset).limit(limit)).unique().all()
        return NotificationAdminListRead(
            items=[self._serialize_admin_notification(item) for item in notifications],
            total=total,
            limit=limit,
            offset=offset,
        )

    def get_notification_detail(self, *, notification_id: str) -> NotificationDetailRead:
        notification = self.db.scalar(
            select(Notification)
            .options(selectinload(Notification.recipients).selectinload(NotificationRecipient.user))
            .where(Notification.id == notification_id)
        )
        if not notification:
            raise ResourceNotFoundException("Notification", notification_id)
        data = self._serialize_admin_notification(notification)
        return NotificationDetailRead(
            **data.model_dump(),
            recipients=[
                NotificationRecipientStateRead(
                    id=recipient.id,
                    user_id=recipient.user_id,
                    username=recipient.user.username if recipient.user else None,
                    is_read=recipient.is_read,
                    read_at=recipient.read_at,
                    is_archived=recipient.is_archived,
                    archived_at=recipient.archived_at,
                    created_at=recipient.created_at,
                )
                for recipient in sorted(notification.recipients, key=lambda item: item.id)
            ],
        )

    def notification_exists(
        self,
        *,
        notification_type: str,
        entity_type: str | None,
        entity_id: int | None,
        user_id: int | None = None,
    ) -> bool:
        stmt = select(Notification.id).where(Notification.notification_type == notification_type)
        if entity_type is None:
            stmt = stmt.where(Notification.entity_type.is_(None))
        else:
            stmt = stmt.where(Notification.entity_type == entity_type)
        if entity_id is None:
            stmt = stmt.where(Notification.entity_id.is_(None))
        else:
            stmt = stmt.where(Notification.entity_id == entity_id)
        if user_id is not None:
            stmt = stmt.join(NotificationRecipient, NotificationRecipient.notification_id == Notification.id).where(
                NotificationRecipient.user_id == user_id
            )
        return self.db.scalar(stmt.limit(1)) is not None

    def set_hr_send_permission(self, *, enabled: bool) -> NotificationPermissionStatusRead:
        role = self.db.scalar(select(Role).where(Role.code == "hr"))
        if not role:
            raise ResourceNotFoundException("Role", "hr")

        permission = self.db.scalar(select(Permission).where(Permission.code == "notifications.send"))
        if not permission:
            raise ResourceNotFoundException("Permission", "notifications.send")

        mapping = self.db.scalar(
            select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == permission.id)
        )
        if enabled and not mapping:
            self.db.add(RolePermission(role_id=role.id, permission_id=permission.id))
            self.db.flush()
        if not enabled and mapping:
            self.db.delete(mapping)
            self.db.flush()

        return NotificationPermissionStatusRead(
            role_code=role.code,
            permission_code=permission.code,
            enabled=enabled,
        )

    def _get_active_user_ids(self, user_ids: list[int]) -> list[int]:
        unique_ids = sorted({int(user_id) for user_id in user_ids})
        if not unique_ids:
            return []
        return list(
            self.db.scalars(
                select(User.id).where(
                    User.id.in_(unique_ids),
                    User.deleted_at.is_(None),
                    User.is_active.is_(True),
                )
            ).all()
        )

    def _apply_user_filters(self, stmt, count_stmt, *, unread_only: bool, is_archived: bool, include_expired: bool):
        now = _utc_now()
        stmt = stmt.where(NotificationRecipient.is_archived.is_(is_archived))
        count_stmt = count_stmt.where(NotificationRecipient.is_archived.is_(is_archived))
        if unread_only:
            stmt = stmt.where(NotificationRecipient.is_read.is_(False))
            count_stmt = count_stmt.where(NotificationRecipient.is_read.is_(False))
        if not include_expired:
            expiry_clause = or_(Notification.expires_at.is_(None), Notification.expires_at > now)
            stmt = stmt.where(expiry_clause)
            count_stmt = count_stmt.where(expiry_clause)
        return stmt, count_stmt

    def _get_user_recipient(self, *, user_id: int, notification_id: str) -> NotificationRecipient:
        recipient = self.db.scalar(
            select(NotificationRecipient)
            .join(Notification, Notification.id == NotificationRecipient.notification_id)
            .options(selectinload(NotificationRecipient.notification))
            .where(
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.notification_id == notification_id,
            )
        )
        if not recipient:
            raise ResourceNotFoundException("Notification", notification_id)
        return recipient

    def _serialize_user_notification(self, recipient: NotificationRecipient) -> UserNotificationRead:
        notification = recipient.notification
        return UserNotificationRead(
            notification_id=notification.id,
            recipient_id=recipient.id,
            notification_type=notification.notification_type,
            title=notification.title,
            message=notification.message,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            actor_user_id=notification.actor_user_id,
            priority=notification.priority,
            created_at=notification.created_at,
            expires_at=notification.expires_at,
            is_read=recipient.is_read,
            read_at=recipient.read_at,
            is_archived=recipient.is_archived,
            archived_at=recipient.archived_at,
            recipient_created_at=recipient.created_at,
        )

    def _serialize_admin_notification(self, notification: Notification) -> NotificationAdminRead:
        recipient_count = len(notification.recipients)
        read_count = sum(1 for recipient in notification.recipients if recipient.is_read)
        archived_count = sum(1 for recipient in notification.recipients if recipient.is_archived)
        return NotificationAdminRead(
            id=notification.id,
            notification_type=notification.notification_type,
            title=notification.title,
            message=notification.message,
            entity_type=notification.entity_type,
            entity_id=notification.entity_id,
            actor_user_id=notification.actor_user_id,
            priority=notification.priority,
            created_at=notification.created_at,
            expires_at=notification.expires_at,
            recipient_count=recipient_count,
            read_count=read_count,
            archived_count=archived_count,
        )
