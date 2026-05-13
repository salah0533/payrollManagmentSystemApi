# Backend In-App Notifications

## Overview

This backend implements an in-app notification system with two tables:

- `notifications`: shared notification content
- `notification_recipients`: per-user delivery state inside the app

The design keeps the message content separate from recipient state so one notification can be sent to many users while each recipient keeps their own `read` and `archived` flags.

## Architecture

### `Notification`

Stores the shared message payload:

- `id`
- `notification_type`
- `title`
- `message`
- `entity_type`
- `entity_id`
- `actor_user_id`
- `priority`
- `created_at`
- `expires_at`

### `NotificationRecipient`

Stores state per recipient:

- `id`
- `notification_id`
- `user_id`
- `is_read`
- `read_at`
- `is_archived`
- `archived_at`
- `created_at`

Important constraints:

- one `Notification` can have many `NotificationRecipient` rows
- `notification_id + user_id` is unique
- recipient state is always user-specific
- self-service APIs never accept `user_id` from the frontend

### `NotificationService`

All notification business logic lives in `app/services/notification_service.py`.

Primary methods:

- `notify_user(...)`
- `notify_users(...)`
- `notify_role(...)`
- `get_user_notifications(...)`
- `get_unread_count(...)`
- `mark_as_read(...)`
- `mark_all_as_read(...)`
- `archive_notification(...)`

Additional admin support methods:

- `list_notifications(...)`
- `get_notification_detail(...)`
- `set_hr_send_permission(...)`

## API Endpoints

### Self-service

- `GET /me/notifications`
- `GET /me/notifications/unread-count`
- `POST /me/notifications/{notification_id}/read`
- `POST /me/notifications/read-all`
- `POST /me/notifications/{notification_id}/archive`

Notes:

- these endpoints always use `current_user`
- they never accept `user_id` from the client
- they return only that user’s own notifications

### Admin and authorized HR

- `GET /notifications`
- `GET /notifications/{notification_id}`
- `POST /notifications`

The send endpoint supports direct user targets and role targets in the same request. Manual sends currently support the requested system notification types plus a `general` type for admin-authored messages.

### Admin-only HR send toggle

- `PUT /notifications/permissions/hr-send`

This endpoint grants or revokes the `notifications.send` permission for the `hr` role by updating the existing RBAC tables.

## Access Rules

- normal employees can only read and mutate their own notification state
- `notifications.read_own` is required for self-service notification access
- `notifications.read_all` is required for broader list/detail access
- `notifications.send` is required for manual sending
- admins bypass permission checks through the existing auth dependency behavior
- HR can read broad notification lists by default
- HR can send notifications only after an admin enables `notifications.send` for the HR role

## Supported Types

System-generated notification types:

- `vacation_request_submitted`
- `vacation_approved`
- `vacation_rejected`
- `vacation_cancelled`
- `attendance_missing_checkin`
- `attendance_missing_checkout`
- `attendance_late`
- `attendance_correction_review_required`
- `payroll_draft_ready`
- `payroll_needs_review`
- `payroll_approved`
- `payroll_paid`
- `payroll_discrepancy_detected`
- `account_created`
- `password_changed`
- `must_change_password`

## Business Integrations

The backend now creates notifications in these flows:

- employee vacation submission notifies HR/admin
- vacation approval, rejection, or cancellation notifies the employee
- missing check-in, missing check-out, and late attendance notify the employee
- payroll draft-ready and needs-review states notify HR/admin
- newly detected payroll discrepancies notify HR/admin with high priority
- payroll approval and paid status notify the employee
- account creation notifies the user
- password change notifies the user
- password reset with mandatory password change notifies the user

## Frontend Consumption

Recommended polling flow:

1. Poll `GET /me/notifications/unread-count` for badge updates.
2. Fetch `GET /me/notifications` for the inbox list.
3. Call `POST /me/notifications/{notification_id}/read` when a notification is opened.
4. Call `POST /me/notifications/{notification_id}/archive` when a notification is dismissed from the inbox.

Suggested query usage for `GET /me/notifications`:

- `unread_only=true` for unread-only inbox views
- `archived=true` for archived history
- `include_expired=true` for admin/debug use if needed
- `limit` and `offset` for pagination

## How Backend Services Create Notifications

Backend services should create notifications through `NotificationService`, not directly through the ORM.

Patterns already used in the codebase:

- service creates or updates the business entity
- service calls `NotificationService`
- outer service transaction commits once

This keeps routes thin and avoids duplicating notification logic in controllers.

## Manual Verification

### Setup

1. Run the migration.
2. Seed permissions and roles if needed.
3. Log in as admin, HR, and employee test users.

### Self-service checks

1. Call `GET /me/notifications/unread-count`.
2. Call `GET /me/notifications`.
3. Mark one notification read.
4. Archive one notification.
5. Confirm another user cannot see or mutate that notification state.

### Admin and HR checks

1. As admin, call `POST /notifications` with a direct `user_ids` target.
2. As admin, enable HR send access with `PUT /notifications/permissions/hr-send`.
3. As HR, call `POST /notifications` and confirm it succeeds after the toggle.
4. As HR before the toggle, confirm the same request is rejected with `403`.

### Business event checks

1. Submit a self-service vacation request and confirm HR/admin receive a notification.
2. Approve or reject that request and confirm the employee receives a notification.
3. Create an incomplete attendance day and confirm the employee receives the correct missing check-in or check-out alert.
4. Recalculate payroll with discrepancies and confirm HR/admin receive high-priority discrepancy notifications.
5. Approve or mark payroll paid and confirm the employee receives the payroll status notification.
