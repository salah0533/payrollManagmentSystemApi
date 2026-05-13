import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.auth import Permission, Role, RolePermission, User, UserRole
from app.models.notifications import NotificationRecipient
from app.services.notification_service import NotificationService


class NotificationServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.service = NotificationService(self.db)

        self.hr_role = Role(code="hr", name="HR", description="HR", is_system_role=True)
        self.employee_role = Role(code="employee", name="Employee", description="Employee", is_system_role=True)
        self.send_permission = Permission(
            code="notifications.send",
            name="Send notifications",
            description="Send notifications",
            module="notifications",
        )
        self.db.add_all([self.hr_role, self.employee_role, self.send_permission])
        self.db.flush()

        self.user_employee = User(
            username="employee_user",
            password_hash="hash",
            is_active=True,
            must_change_password=False,
        )
        self.user_hr = User(
            username="hr_user",
            password_hash="hash",
            is_active=True,
            must_change_password=False,
        )
        self.db.add_all([self.user_employee, self.user_hr])
        self.db.flush()
        self.db.add_all(
            [
                UserRole(user_id=self.user_employee.id, role_id=self.employee_role.id),
                UserRole(user_id=self.user_hr.id, role_id=self.hr_role.id),
            ]
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_notify_role_delivers_to_matching_users(self):
        notification = self.service.notify_role(
            role_codes=["hr"],
            notification_type="general",
            title="Reminder",
            message="HR only message",
        )
        self.db.commit()

        self.assertIsNotNone(notification)
        self.assertEqual(self.service.get_unread_count(user_id=self.user_hr.id), 1)
        self.assertEqual(self.service.get_unread_count(user_id=self.user_employee.id), 0)

    def test_mark_read_and_archive_are_scoped_per_user(self):
        notification = self.service.notify_users(
            user_ids=[self.user_employee.id, self.user_hr.id],
            notification_type="general",
            title="All hands",
            message="Shared notification",
        )
        self.db.commit()

        employee_view = self.service.mark_as_read(user_id=self.user_employee.id, notification_id=notification.id)
        self.db.commit()
        hr_recipient = self.db.scalar(
            select(NotificationRecipient).where(
                NotificationRecipient.user_id == self.user_hr.id,
                NotificationRecipient.notification_id == notification.id,
            )
        )

        self.assertTrue(employee_view.is_read)
        self.assertEqual(self.service.get_unread_count(user_id=self.user_employee.id), 0)
        self.assertIsNotNone(hr_recipient)
        self.assertFalse(hr_recipient.is_read)
        self.assertEqual(self.service.get_unread_count(user_id=self.user_hr.id), 1)

        hr_view = self.service.archive_notification(user_id=self.user_hr.id, notification_id=notification.id)
        self.db.commit()
        self.assertTrue(hr_view.is_archived)
        self.assertTrue(hr_view.is_read)
        self.assertEqual(self.service.get_unread_count(user_id=self.user_hr.id), 0)

    def test_set_hr_send_permission_toggles_role_permission(self):
        enabled = self.service.set_hr_send_permission(enabled=True)
        self.db.commit()
        mapping = self.db.scalar(
            select(RolePermission).where(
                RolePermission.role_id == self.hr_role.id,
                RolePermission.permission_id == self.send_permission.id,
            )
        )

        self.assertTrue(enabled.enabled)
        self.assertIsNotNone(mapping)

        disabled = self.service.set_hr_send_permission(enabled=False)
        self.db.commit()
        mapping = self.db.scalar(
            select(RolePermission).where(
                RolePermission.role_id == self.hr_role.id,
                RolePermission.permission_id == self.send_permission.id,
            )
        )

        self.assertFalse(disabled.enabled)
        self.assertIsNone(mapping)


if __name__ == "__main__":
    unittest.main()
