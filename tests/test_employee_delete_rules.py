import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import selectinload, sessionmaker

import app.models  # noqa: F401
from app.core.security import get_password_hash
from app.db.base import Base
from app.exceptions.base_exception import BadRequestException, ForbiddenException
from app.models.auth import Role, User, UserRole
from app.models.employees import Employees
from app.services.employee_service import delete_employee
from app.services.user_service import ResourceConflictException, delete_user


class EmployeeDeleteRulesTests(unittest.TestCase):
    admin_password = "AdminPass123!"

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.admin_role = Role(code="admin", name="Admin", is_system_role=True)
        self.hr_role = Role(code="hr", name="HR", is_system_role=True)
        self.db.add_all([self.admin_role, self.hr_role])
        self.db.flush()
        self.admin = self._create_user("admin", role=self.admin_role, password=self.admin_password)
        self.hr = self._create_user("hr", role=self.hr_role, password="HrPass123!")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _reload_user(self, user_id: int) -> User:
        return self.db.scalar(
            select(User)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
            .where(User.id == user_id)
        )

    def _create_user(
        self,
        username: str,
        *,
        role: Role | None = None,
        password: str = "UserPass123!",
        employee_id: int | None = None,
        is_active: bool = True,
    ) -> User:
        user = User(
            employee_id=employee_id,
            username=username,
            email=f"{username}@example.com",
            password_hash=get_password_hash(password),
            is_active=is_active,
            must_change_password=False,
        )
        self.db.add(user)
        self.db.flush()
        if role is not None:
            self.db.add(UserRole(user_id=user.id, role_id=role.id))
        self.db.commit()
        return self._reload_user(user.id)

    def _create_employee(self) -> Employees:
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
        self.db.commit()
        self.db.refresh(employee)
        return employee

    def _create_employee_with_user(self, *, user_is_active: bool) -> tuple[Employees, User]:
        employee = self._create_employee()
        user = self._create_user(
            f"user_{'active' if user_is_active else 'inactive'}",
            employee_id=employee.id,
            is_active=user_is_active,
        )
        self.db.refresh(employee)
        return employee, user

    def test_delete_employee_fails_without_admin_password(self):
        employee = self._create_employee()

        with self.assertRaises(BadRequestException):
            delete_employee(employee.id, self.db, actor=self.admin)

    def test_delete_employee_fails_with_wrong_admin_password(self):
        employee = self._create_employee()

        with self.assertRaises(BadRequestException):
            delete_employee(employee.id, self.db, admin_password="wrong", actor=self.admin)

    def test_delete_employee_is_forbidden_for_hr_even_with_employee_permissions(self):
        employee = self._create_employee()

        with self.assertRaises(ForbiddenException):
            delete_employee(employee.id, self.db, admin_password="HrPass123!", actor=self.hr)

    def test_delete_employee_blocks_when_linked_user_exists(self):
        employee, _ = self._create_employee_with_user(user_is_active=False)

        with self.assertRaises(ResourceConflictException):
            delete_employee(employee.id, self.db, admin_password=self.admin_password, actor=self.admin)

        still_present = self.db.scalar(select(Employees).where(Employees.id == employee.id))
        self.assertIsNone(still_present.deleted_at)

    def test_delete_employee_succeeds_with_current_admin_password_when_no_user_is_linked(self):
        employee, user = self._create_employee_with_user(user_is_active=False)
        user.employee_id = None
        self.db.add(user)
        self.db.commit()

        delete_employee(employee.id, self.db, admin_password=self.admin_password, actor=self.admin)

        deleted_employee = self.db.scalar(select(Employees).where(Employees.id == employee.id))
        self.assertIsNotNone(deleted_employee.deleted_at)
        self.assertEqual(deleted_employee.status, "inactive")
        self.assertFalse(deleted_employee.is_active)

    def test_user_delete_fails_without_admin_password(self):
        user = self._create_user("regular")

        with self.assertRaises(BadRequestException):
            delete_user(user.id, self.db, actor=self.admin)

    def test_user_delete_fails_with_wrong_admin_password(self):
        user = self._create_user("regular")

        with self.assertRaises(BadRequestException):
            delete_user(user.id, self.db, admin_password="wrong", actor=self.admin)

    def test_user_delete_succeeds_with_admin_password_and_unlinks_employee(self):
        employee, user = self._create_employee_with_user(user_is_active=True)

        delete_user(user.id, self.db, admin_password=self.admin_password, actor=self.admin)

        updated_user = self.db.scalar(select(User).where(User.id == user.id))
        self.assertIsNotNone(updated_user.deleted_at)
        self.assertFalse(updated_user.is_active)
        self.assertIsNone(updated_user.employee_id)
        self.assertIsNotNone(self.db.scalar(select(Employees).where(Employees.id == employee.id)))

    def test_last_active_admin_still_cannot_be_deleted(self):
        with self.assertRaises(ResourceConflictException):
            delete_user(self.admin.id, self.db, admin_password=self.admin_password, actor=self.admin)


if __name__ == "__main__":
    unittest.main()
