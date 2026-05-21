import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.auth import User
from app.models.employees import Employees
from app.services.employee_service import delete_employee
from app.services.user_service import ResourceConflictException, delete_user


class EmployeeDeleteRulesTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create_employee_with_user(self, *, user_is_active: bool) -> tuple[Employees, User]:
        employee = Employees(
            first_name="Jane",
            last_name="Doe",
            fullname="Jane Doe",
            job_title="Engineer",
            phone="1234567890",
            email="jane@example.com",
            department_id=None,
            position_id=None,
            position=None,
            status="active",
            hire_date=date(2026, 1, 1),
            dues=Decimal("0.00"),
            salary_type=0,
            monthly_price=Decimal("5000.00"),
            day_price=Decimal("0.00"),
            hour_price=Decimal("0.00"),
            extra_hours_price=Decimal("0.00"),
            daily_work_hours=8,
            vacation_days=30,
            auto_attendance_enabled=False,
            auto_attendance_effective_from=None,
            is_active=True,
            allowed_late=Decimal("0.00"),
            min_extraTime=Decimal("0.00"),
            joined=date(2026, 1, 1),
        )
        self.db.add(employee)
        self.db.flush()

        user = User(
            employee_id=employee.id,
            username=f"user_{'active' if user_is_active else 'inactive'}",
            email=f"{'active' if user_is_active else 'inactive'}@example.com",
            password_hash="hashed",
            is_active=user_is_active,
            must_change_password=False,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(employee)
        self.db.refresh(user)
        return employee, user

    def test_delete_employee_blocks_when_linked_user_is_active(self):
        employee, _ = self._create_employee_with_user(user_is_active=True)

        with self.assertRaises(ResourceConflictException):
            delete_employee(employee.id, self.db)

        still_present = self.db.scalar(select(Employees).where(Employees.id == employee.id))
        self.assertIsNone(still_present.deleted_at)

    def test_delete_employee_blocks_when_linked_user_is_inactive(self):
        employee, user = self._create_employee_with_user(user_is_active=False)

        with self.assertRaises(ResourceConflictException):
            delete_employee(employee.id, self.db)

        updated_user = self.db.scalar(select(User).where(User.id == user.id))
        self.assertIsNotNone(updated_user.employee_id)

    def test_delete_employee_allows_after_linked_user_is_deleted(self):
        employee, user = self._create_employee_with_user(user_is_active=False)

        delete_user(user.id, self.db)
        delete_employee(employee.id, self.db)

        deleted_employee = self.db.scalar(select(Employees).where(Employees.id == employee.id))
        updated_user = self.db.scalar(select(User).where(User.id == user.id))
        self.assertIsNotNone(deleted_employee.deleted_at)
        self.assertEqual(deleted_employee.status, "inactive")
        self.assertFalse(deleted_employee.is_active)
        self.assertIsNotNone(updated_user.deleted_at)
        self.assertIsNone(updated_user.employee_id)

    def test_delete_employee_allows_after_link_is_removed(self):
        employee, user = self._create_employee_with_user(user_is_active=False)
        user.employee_id = None
        self.db.add(user)
        self.db.commit()

        delete_employee(employee.id, self.db)

        deleted_employee = self.db.scalar(select(Employees).where(Employees.id == employee.id))
        self.assertIsNotNone(deleted_employee.deleted_at)


if __name__ == "__main__":
    unittest.main()
