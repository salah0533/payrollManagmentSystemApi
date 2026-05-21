import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.security import utc_now
from app.db.base import Base
from app.models.attendance_payroll import EmployeePayroll, PayrollPeriod
from app.models.employees import Employees
from app.services.payroll_calculation_service import get_payroll_balance_report, get_payroll_period


class DeletedEmployeePayrollVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

        self.active_employee = self._create_employee("Active Employee")
        self.deleted_employee = self._create_employee("Deleted Employee", deleted=True)
        self.period = PayrollPeriod(
            name="May 2026",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            status="draft",
        )
        self.db.add(self.period)
        self.db.flush()
        self._create_payroll(self.active_employee.id, Decimal("100.00"))
        self._create_payroll(self.deleted_employee.id, Decimal("200.00"))
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

    def _create_payroll(self, employee_id: int, total: Decimal) -> None:
        self.db.add(
            EmployeePayroll(
                payroll_period_id=self.period.id,
                employee_id=employee_id,
                salary_type="monthly",
                base_salary=total,
                normal_amount=total,
                overtime_amount=Decimal("0.00"),
                bonus_amount=Decimal("0.00"),
                deduction_amount=Decimal("0.00"),
                late_deduction_amount=Decimal("0.00"),
                unpaid_vacation_deduction=Decimal("0.00"),
                adjustment_amount=Decimal("0.00"),
                gross_salary=total,
                net_salary=total,
                total_amount=total,
                paid_amount=Decimal("0.00"),
                balance_amount=total,
                status="draft",
            )
        )

    def test_payroll_report_excludes_deleted_employees_by_default(self):
        report = get_payroll_balance_report(self.db, period_id=self.period.id)

        self.assertEqual(report["total_amount"], Decimal("100.00"))
        self.assertEqual([row["employee_id"] for row in report["employees"]], [self.active_employee.id])

    def test_payroll_report_includes_deleted_employees_when_archived_requested(self):
        report = get_payroll_balance_report(self.db, period_id=self.period.id, include_archived=True)

        self.assertEqual(report["total_amount"], Decimal("300.00"))
        self.assertEqual(
            sorted(row["employee_id"] for row in report["employees"]),
            sorted([self.active_employee.id, self.deleted_employee.id]),
        )

    def test_payroll_period_excludes_deleted_employee_payrolls_by_default(self):
        period = get_payroll_period(self.period.id, self.db)

        self.assertEqual([payroll.employee_id for payroll in period.payrolls], [self.active_employee.id])

    def test_payroll_period_includes_deleted_employee_payrolls_when_archived_requested(self):
        period = get_payroll_period(self.period.id, self.db, include_archived=True)

        self.assertEqual(
            sorted(payroll.employee_id for payroll in period.payrolls),
            sorted([self.active_employee.id, self.deleted_employee.id]),
        )


if __name__ == "__main__":
    unittest.main()
