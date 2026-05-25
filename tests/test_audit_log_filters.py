import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.auth import Role, User, UserRole
from app.models.employees import Employees
from app.models.salary_type import SalaryType
from app.services.audit_service import list_audit_logs, save_audit_log


class AuditLogFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _create_employee(self, session, *, first_name: str, last_name: str, email: str, phone: str, position: str) -> Employees:
        employee = Employees(
            first_name=first_name,
            last_name=last_name,
            fullname=f"{first_name} {last_name}",
            job_title=position,
            phone=phone,
            email=email,
            department_id=None,
            position_id=None,
            position=position,
            status="active",
            hire_date=date(2026, 5, 1),
            salary_type=0,
            monthly_price=Decimal("120000.00"),
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
            joined=date(2026, 5, 1),
        )
        session.add(employee)
        session.flush()
        return employee

    def test_hr_employee_creation_filter_returns_actor_and_employee_details(self):
        session = self.SessionLocal()
        try:
            session.add(SalaryType(id=0, code="monthly", salary_type="monthly"))
            hr_role = Role(code="hr", name="HR")
            admin_role = Role(code="admin", name="Admin")
            session.add_all([hr_role, admin_role])
            session.flush()

            hr_employee = self._create_employee(
                session,
                first_name="Hana",
                last_name="Bensaid",
                email="hana.hr@example.com",
                phone="0555000001",
                position="HR Specialist",
            )
            admin_employee = self._create_employee(
                session,
                first_name="Karim",
                last_name="Admin",
                email="karim.admin@example.com",
                phone="0555000002",
                position="Admin Manager",
            )
            hr_created_employee = self._create_employee(
                session,
                first_name="Salah",
                last_name="Addoune",
                email="salah.addoune@example.com",
                phone="0555000003",
                position="Operator",
            )
            admin_created_employee = self._create_employee(
                session,
                first_name="Meriem",
                last_name="Control",
                email="meriem.control@example.com",
                phone="0555000004",
                position="Assistant",
            )

            hr_user = User(
                employee_id=hr_employee.id,
                username="hana.hr",
                email="hana.hr@example.com",
                password_hash="hashed",
                language="en",
                is_active=True,
                must_change_password=False,
            )
            admin_user = User(
                employee_id=admin_employee.id,
                username="karim.admin",
                email="karim.admin@example.com",
                password_hash="hashed",
                language="en",
                is_active=True,
                must_change_password=False,
            )
            session.add_all([hr_user, admin_user])
            session.flush()

            session.add_all(
                [
                    UserRole(user_id=hr_user.id, role_id=hr_role.id),
                    UserRole(user_id=admin_user.id, role_id=admin_role.id),
                ]
            )
            session.flush()

            save_audit_log(
                session,
                action="employee_created",
                entity_type="Employee",
                entity_id=hr_created_employee.id,
                new_data_json={
                    "id": hr_created_employee.id,
                    "fullname": hr_created_employee.fullname,
                    "email": hr_created_employee.email,
                    "phone": hr_created_employee.phone,
                    "position": hr_created_employee.position,
                    "status": hr_created_employee.status,
                },
                user_id=hr_user.id,
            )
            save_audit_log(
                session,
                action="employee_created",
                entity_type="Employee",
                entity_id=admin_created_employee.id,
                new_data_json={
                    "id": admin_created_employee.id,
                    "fullname": admin_created_employee.fullname,
                    "email": admin_created_employee.email,
                    "phone": admin_created_employee.phone,
                    "position": admin_created_employee.position,
                    "status": admin_created_employee.status,
                },
                user_id=admin_user.id,
            )
            session.commit()

            rows = list_audit_logs(
                session,
                actions=["employee_created"],
                entity_types=["Employee"],
                actor_role="hr",
            )

            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertIsNotNone(row.actor)
            self.assertEqual(row.actor.id, hr_user.id)
            self.assertEqual(row.actor.username, "hana.hr")
            self.assertEqual(row.actor.employee_name, hr_employee.fullname)
            self.assertEqual(row.actor.roles, ["hr"])

            self.assertIsNotNone(row.entity_employee)
            self.assertEqual(row.entity_employee.id, hr_created_employee.id)
            self.assertEqual(row.entity_employee.full_name, hr_created_employee.fullname)
            self.assertEqual(row.entity_employee.email, hr_created_employee.email)
            self.assertEqual(row.entity_employee.phone, hr_created_employee.phone)
            self.assertEqual(row.entity_label, hr_created_employee.fullname)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
