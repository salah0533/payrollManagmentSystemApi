import unittest
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.models.attendance_payroll import AttendanceDay, EmployeePayroll, PayrollDiscrepancy, PayrollPolicy, WorkSchedule
from app.models.employees import Employees
from app.models.payment_types import PaymentTypes
from app.models.salary_type import SalaryType
from app.services.attendance_calculation_service import apply_smart_attendance_status_correction, create_attendance_event
from app.services.payroll_calculation_service import approve_employee_payroll, get_employee_payroll_by_period, get_or_create_payroll_period_for_date


class AttendancePayrollRefactorTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

        self.db.add_all(
            [
                SalaryType(id=0, code="monthly", salary_type="monthly"),
                PaymentTypes(id=0, code="payment", payment_type="payment"),
                WorkSchedule(
                    name="Default Schedule",
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    break_minutes=0,
                    weekly_off_days=["friday"],
                    timezone="UTC",
                    is_default=True,
                ),
                PayrollPolicy(
                    name="default",
                    payroll_cycle="monthly",
                    minimum_overtime_minutes=30,
                    allowed_late_minutes=0,
                    default_currency="USD",
                    significant_change_threshold=Decimal("1.00"),
                    paid_vacation_counts_for_daily=True,
                    overtime_enabled=True,
                    late_makeup_enabled=True,
                    late_deduction_enabled=True,
                    auto_recalculate_draft_payroll=True,
                    lock_payroll_after_payment=True,
                    holidays_json=[],
                ),
            ]
        )
        self.db.flush()

        self.employee = Employees(
            first_name="Jane",
            last_name="Tester",
            fullname="Jane Tester",
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
            monthly_price=Decimal("3200.00"),
            day_price=Decimal("120.00"),
            hour_price=Decimal("15.00"),
            extra_hours_price=Decimal("20.00"),
            daily_work_hours=8,
            vacation_days=0,
            is_active=True,
            allowed_late=Decimal("0.00"),
            min_extraTime=Decimal("0.00"),
            joined=date(2026, 1, 1),
        )
        self.db.add(self.employee)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _schedule(self) -> WorkSchedule:
        return self.db.scalar(select(WorkSchedule).where(WorkSchedule.is_default.is_(True)))

    def _policy(self) -> PayrollPolicy:
        return self.db.scalar(select(PayrollPolicy).order_by(PayrollPolicy.id))

    def test_timezone_boundary_uses_schedule_timezone_for_work_date(self):
        schedule = self._schedule()
        schedule.timezone = "Europe/Berlin"
        self.db.add(schedule)
        self.db.commit()

        _, day = create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 4, 22, 30, tzinfo=timezone.utc),
            self.db,
        )

        self.assertEqual(day.work_date, date(2026, 5, 5))

    def test_short_day_without_break_events_keeps_positive_work_minutes(self):
        schedule = self._schedule()
        schedule.break_minutes = 60
        self.db.add(schedule)
        self.db.commit()

        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 5, 9, 30, tzinfo=timezone.utc),
            self.db,
        )
        _, day = create_attendance_event(
            self.employee.id,
            "check_out",
            datetime(2026, 5, 5, 10, 0, tzinfo=timezone.utc),
            self.db,
        )

        self.assertEqual(day.actual_work_minutes, 30)
        self.assertEqual(day.status, "late")
        self.assertGreater(day.unpaid_minutes, 0)

    def test_allowed_late_grace_keeps_status_present(self):
        policy = self._policy()
        policy.allowed_late_minutes = 10
        self.db.add(policy)
        self.db.commit()

        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 6, 9, 5, tzinfo=timezone.utc),
            self.db,
        )
        _, day = create_attendance_event(
            self.employee.id,
            "check_out",
            datetime(2026, 5, 6, 17, 0, tzinfo=timezone.utc),
            self.db,
        )

        self.assertEqual(day.late_minutes, 0)
        self.assertEqual(day.status, "present")
        self.assertEqual(day.normal_paid_minutes, 480)

    def test_smart_correction_after_payroll_approval_creates_discrepancy(self):
        work_date = date(2026, 5, 7)
        apply_smart_attendance_status_correction(
            self.employee.id,
            work_date,
            "present",
            corrected_by=1,
            reason="Seed attendance",
            options={},
            db=self.db,
        )
        period = get_or_create_payroll_period_for_date(work_date, self.db)
        payroll = get_employee_payroll_by_period(self.employee.id, period.id, self.db)
        original_net_salary = Decimal(str(payroll.net_salary))

        approve_employee_payroll(payroll.id, self.db, approved_by=1)

        apply_smart_attendance_status_correction(
            self.employee.id,
            work_date,
            "absent",
            corrected_by=1,
            reason="Change after approval",
            options={},
            db=self.db,
        )

        payroll_after = self.db.get(EmployeePayroll, payroll.id)
        open_discrepancies = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()

        self.assertEqual(Decimal(str(payroll_after.net_salary)), original_net_salary)
        self.assertTrue(
            any(item.discrepancy_type == "attendance_changed_after_approval" for item in open_discrepancies)
        )

    def test_fixing_attendance_resolves_managed_discrepancies(self):
        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 11, 9, 0, tzinfo=timezone.utc),
            self.db,
        )
        period = get_or_create_payroll_period_for_date(date(2026, 5, 11), self.db)
        payroll = get_employee_payroll_by_period(self.employee.id, period.id, self.db)

        open_before = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        self.assertTrue(any(item.discrepancy_type == "missing_checkout" for item in open_before))

        apply_smart_attendance_status_correction(
            self.employee.id,
            date(2026, 5, 11),
            "present",
            corrected_by=1,
            reason="Complete the day",
            options={},
            db=self.db,
        )

        open_after = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        self.assertFalse(any(item.discrepancy_type == "missing_checkout" for item in open_after))
        self.assertFalse(any(item.discrepancy_type == "attendance_requires_review" for item in open_after))

    def test_duplicate_attendance_day_is_rejected(self):
        self.db.add(
            AttendanceDay(
                employee_id=self.employee.id,
                work_date=date(2026, 5, 9),
                status="absent",
                review_status="draft",
            )
        )
        self.db.commit()

        self.db.add(
            AttendanceDay(
                employee_id=self.employee.id,
                work_date=date(2026, 5, 9),
                status="present",
                review_status="approved",
            )
        )

        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
