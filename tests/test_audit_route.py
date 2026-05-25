import json
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.attendance_payroll import AuditLog
from app.models.auth import Role, User, UserRole
from app.models.employees import Employees
from app.models.salary_type import SalaryType
from app.routes.routes.audit import list_audit_logs


class AuditRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.SessionLocal()
        self._seed_fixture_data()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _seed_fixture_data(self):
        salary_type = SalaryType(code="monthly", salary_type="monthly")
        admin_role = Role(code="admin", name="Admin")
        employee_role = Role(code="employee", name="Employee")
        self.db.add_all([salary_type, admin_role, employee_role])
        self.db.flush()

        self.admin_employee = self._create_employee(
            first_name="Amina",
            last_name="Admin",
            email="amina.admin@payrolldemo.com",
            salary_type_id=salary_type.id,
        )
        self.target_employee = self._create_employee(
            first_name="Tariq",
            last_name="Teammate",
            email="tariq.teammate@payrolldemo.com",
            salary_type_id=salary_type.id,
        )
        self.db.flush()

        self.admin_user = User(
            employee_id=self.admin_employee.id,
            username="amina.admin",
            email="amina.admin@payrolldemo.com",
            password_hash="hashed",
            is_active=True,
        )
        self.target_user = User(
            employee_id=self.target_employee.id,
            username="tariq.employee",
            email="tariq.teammate@payrolldemo.com",
            password_hash="hashed",
            is_active=True,
        )
        self.db.add_all([self.admin_user, self.target_user])
        self.db.flush()

        self.db.add_all(
            [
                UserRole(user_id=self.admin_user.id, role_id=admin_role.id),
                UserRole(user_id=self.target_user.id, role_id=employee_role.id),
            ]
        )
        self.db.flush()

        self.db.add_all(
            [
                AuditLog(
                    user_id=self.admin_user.id,
                    action="login",
                    entity_type="User",
                    entity_id=self.admin_user.id,
                    ip_address="127.0.0.1",
                    new_data_json={"status": "active"},
                    created_at=datetime(2026, 5, 25, 8, 0, tzinfo=timezone.utc),
                ),
                AuditLog(
                    user_id=self.admin_user.id,
                    action="user_updated",
                    entity_type="User",
                    entity_id=self.target_user.id,
                    old_data_json={"email": "old@payrolldemo.com"},
                    new_data_json={"email": self.target_user.email},
                    created_at=datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc),
                ),
                AuditLog(
                    user_id=None,
                    action="employee_created",
                    entity_type="Employee",
                    entity_id=self.target_employee.id,
                    new_data_json={"fullname": self.target_employee.fullname},
                    created_at=datetime(2026, 5, 25, 10, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        self.db.commit()

    def _create_employee(self, *, first_name: str, last_name: str, email: str, salary_type_id: int) -> Employees:
        employee = Employees(
            first_name=first_name,
            last_name=last_name,
            fullname=f"{first_name} {last_name}",
            job_title="Operations",
            phone="0555000000",
            email=email,
            department_id=1,
            position_id=1,
            position="Operations",
            status="active",
            hire_date=date(2026, 1, 1),
            salary_type=salary_type_id,
            monthly_price=Decimal("30000.00"),
            day_price=Decimal("1000.00"),
            hour_price=Decimal("125.00"),
            extra_hours_price=Decimal("150.00"),
            daily_work_hours=8,
            vacation_days=21,
            auto_attendance_enabled=False,
            is_active=True,
            allowed_late=Decimal("15.00"),
            min_extraTime=Decimal("30.00"),
            joined=date(2026, 1, 1),
        )
        self.db.add(employee)
        return employee

    def _response_data(self, response):
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["status"])
        return payload["data"]

    def test_login_row_shows_enriched_admin_actor_and_target(self):
        response = list_audit_logs(
            page=1,
            page_size=10,
            action=["login"],
            entity_type=["User"],
            db=self.db,
            current_user=self.admin_user,
        )
        data = self._response_data(response)

        self.assertEqual(data["total_records"], 1)
        self.assertEqual(data["total_pages"], 1)
        row = data["items"][0]
        self.assertEqual(row["action"], "login")
        self.assertEqual(row["actor"]["employee_name"], "Amina Admin")
        self.assertEqual(row["actor"]["username"], "amina.admin")
        self.assertIn("admin", row["actor"]["roles"])
        self.assertEqual(row["entity_user"]["id"], self.admin_user.id)
        self.assertEqual(row["entity_label"], "Amina Admin")

    def test_search_applies_before_pagination_and_finds_older_rows(self):
        response = list_audit_logs(
            page=1,
            page_size=1,
            search="old@payrolldemo.com",
            db=self.db,
            current_user=self.admin_user,
        )
        data = self._response_data(response)

        self.assertEqual(data["total_records"], 1)
        self.assertEqual(data["total_pages"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["action"], "user_updated")
        self.assertEqual(data["items"][0]["entity_user"]["username"], "tariq.employee")

    def test_filters_support_actor_role_actor_user_action_and_entity_type(self):
        response = list_audit_logs(
            page=1,
            page_size=10,
            action=["user_updated"],
            entity_type=["User"],
            actor_user_id=self.admin_user.id,
            actor_role="admin",
            db=self.db,
            current_user=self.admin_user,
        )
        data = self._response_data(response)

        self.assertEqual(data["total_records"], 1)
        self.assertEqual(data["items"][0]["action"], "user_updated")
        self.assertEqual(data["items"][0]["actor"]["id"], self.admin_user.id)
        self.assertEqual(data["items"][0]["entity_user"]["id"], self.target_user.id)

    def test_pagination_returns_newest_rows_first(self):
        response = list_audit_logs(
            page=1,
            page_size=2,
            db=self.db,
            current_user=self.admin_user,
        )
        data = self._response_data(response)

        self.assertEqual(data["total_records"], 3)
        self.assertEqual(data["total_pages"], 2)
        self.assertEqual([row["action"] for row in data["items"]], ["employee_created", "user_updated"])

    def test_system_actor_filter_returns_only_system_rows(self):
        response = list_audit_logs(
            page=1,
            page_size=10,
            actor_role="system",
            db=self.db,
            current_user=self.admin_user,
        )
        data = self._response_data(response)

        self.assertEqual(data["total_records"], 1)
        self.assertIsNone(data["items"][0]["actor"])
        self.assertEqual(data["items"][0]["entity_employee"]["full_name"], "Tariq Teammate")


if __name__ == "__main__":
    unittest.main()
