from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class NotificationPriority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class NotificationType(str, Enum):
    general = "general"
    vacation_request_submitted = "vacation_request_submitted"
    vacation_approved = "vacation_approved"
    vacation_rejected = "vacation_rejected"
    vacation_cancelled = "vacation_cancelled"
    attendance_missing_checkin = "attendance_missing_checkin"
    attendance_missing_checkout = "attendance_missing_checkout"
    attendance_late = "attendance_late"
    attendance_correction_review_required = "attendance_correction_review_required"
    payroll_draft_ready = "payroll_draft_ready"
    payroll_needs_review = "payroll_needs_review"
    payroll_approved = "payroll_approved"
    payroll_paid = "payroll_paid"
    payroll_discrepancy_detected = "payroll_discrepancy_detected"
    account_created = "account_created"
    password_changed = "password_changed"
    must_change_password = "must_change_password"


class NotificationDispatchRequest(BaseModel):
    notification_type: NotificationType = NotificationType.general
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    user_ids: list[int] = Field(default_factory=list)
    role_codes: list[str] = Field(default_factory=list)
    entity_type: str | None = Field(default=None, max_length=100)
    entity_id: int | None = None
    priority: NotificationPriority = NotificationPriority.normal
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_targets(self):
        if not self.user_ids and not self.role_codes:
            raise ValueError("At least one target user or role is required")
        return self


class NotificationHrSendPermissionUpdateRequest(BaseModel):
    enabled: bool


class UserNotificationRead(BaseModel):
    notification_id: int
    recipient_id: int
    notification_type: str
    title: str
    message: str
    entity_type: str | None = None
    entity_id: int | None = None
    actor_user_id: int | None = None
    priority: str
    created_at: datetime
    expires_at: datetime | None = None
    is_read: bool
    read_at: datetime | None = None
    is_archived: bool
    archived_at: datetime | None = None
    recipient_created_at: datetime


class UserNotificationListRead(BaseModel):
    items: list[UserNotificationRead]
    total: int
    unread_count: int
    limit: int
    offset: int


class NotificationUnreadCountRead(BaseModel):
    unread_count: int


class NotificationActionResultRead(BaseModel):
    notification_id: int | None = None
    updated: int | None = None
    status: str


class NotificationRecipientStateRead(BaseModel):
    id: int
    user_id: int
    username: str | None = None
    is_read: bool
    read_at: datetime | None = None
    is_archived: bool
    archived_at: datetime | None = None
    created_at: datetime


class NotificationAdminRead(BaseModel):
    id: int
    notification_type: str
    title: str
    message: str
    entity_type: str | None = None
    entity_id: int | None = None
    actor_user_id: int | None = None
    priority: str
    created_at: datetime
    expires_at: datetime | None = None
    recipient_count: int
    read_count: int
    archived_count: int


class NotificationAdminListRead(BaseModel):
    items: list[NotificationAdminRead]
    total: int
    limit: int
    offset: int


class NotificationDetailRead(NotificationAdminRead):
    recipients: list[NotificationRecipientStateRead]


class NotificationPermissionStatusRead(BaseModel):
    role_code: str
    permission_code: str
    enabled: bool
