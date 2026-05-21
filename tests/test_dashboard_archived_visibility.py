import unittest
from datetime import date, time
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.security import utc_now
from app.db.base import Base
from app.models.attendance_payroll import AttendanceDay, WorkSchedule
from app.models.employees import Employees
from app.models.vacation import Vacation
from app.services.attendance_calculation_service import get_attendance_days_in_range
from app.services.stat_service import dashboard_attendance_stats
from app.services.vacation_service import get_all_current_vacations, get_all_vacations


class DashboardArchivedVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.today = date.today()
        self.db.add(
            WorkSchedule(
                name="Default",
                start_time=time(9, 0),
                end_time=time(17, 0),
                break_minutes=0,
                weekly_off_days=[],
                timezone="Africa/Algiers",
                is_default=True,
            )
        )
        self.db.flush()
        self.active_employee = self._create_employee("Active Employee")
        self.deleted_employee = self._create_employee("Deleted Employee", deleted=True)
        self._create_attendance(self.active_employee.id)
        self._create_attendance(self.deleted_employee.id)
        self._create_vacation(self.active_employee.id)
        self._create_vacation(self.deleted_employee.id)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _create_employee(self, fullname: str, *, deleted: bool = False) -> Employees:
        first_name, last_name = fullname.split(" ", 1)
        employee = Employees(
            first_name=first_name,
            last_name=last_name,
            fullname=fullname,
            job_title="Engineer",
            phone="1234567890",
            email=f"{first_name.lower()}@example.com",
            department_id=None,
            position_id=None,
            position=None,
            status="inactive" if deleted else "active",
            hire_date=date(2026, 1, 1),
            dues=Decimal("0.00"),
            salary_type=0,
            monthly_price=Decimal("1000.00"),
            day_price=Decimal("0.00"),
            hour_price=Decimal("0.00"),
            extra_hours_price=Decimal("0.00"),
            daily_work_hours=8,
            vacation_days=30,
            auto_attendance_enabled=False,
            auto_attendance_effective_from=None,
            is_active=not deleted,
            allowed_late=Decimal("0.00"),
            min_extraTime=Decimal("0.00"),
            joined=date(2026, 1, 1),
            deleted_at=utc_now() if deleted else None,
        )
        self.db.add(employee)
        self.db.flush()
        return employee

    def _create_attendance(self, employee_id: int) -> None:
        self.db.add(
            AttendanceDay(
                employee_id=employee_id,
                work_date=self.today,
                expected_work_minutes=480,
                actual_work_minutes=480,
                normal_paid_minutes=480,
                status="present",
                review_status="approved",
            )
        )

    def _create_vacation(self, employee_id: int) -> None:
        self.db.add(
            Vacation(
                employee_id=employee_id,
                start_date=self.today,
                end_date=self.today,
                vacation_type=1,
                vacation_status=1,
                is_paid=True,
            )
        )

    def test_dashboard_stats_ignore_soft_deleted_employees_and_history(self):
        stats = dashboard_attendance_stats(self.db)

        self.assertEqual(stats["total_emps"], 1)
        self.assertEqual(stats["total_active_emps"], 1)
        self.assertEqual(stats["present_days"], 1)
        self.assertEqual(stats["total_vacation"], 1)

    def test_dashboard_attendance_range_ignores_soft_deleted_employees(self):
        days = get_attendance_days_in_range(self.today, self.today, self.db)

        self.assertEqual([day.employee_id for day in days], [self.active_employee.id])

    def test_dashboard_vacation_lists_ignore_soft_deleted_employees(self):
        all_vacations = get_all_vacations(self.today.year, self.db)
        current_vacations = get_all_current_vacations(self.db)

        self.assertEqual([vacation.employee_id for vacation in all_vacations], [self.active_employee.id])
        self.assertEqual([vacation.employee_id for vacation in current_vacations], [self.active_employee.id])


if __name__ == "__main__":
    unittest.main()
