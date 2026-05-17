import unittest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.exceptions.base_exception import ConflictException
from app.models.attendance_payroll import PayrollPolicy
from app.models.annual_vacation import AnnualVacations
from app.models.employees import Employees
from app.models.salary_type import SalaryType
from app.models.vacation import Vacation
from app.models.vacation_status import VacationStatus
from app.models.vacation_types import VacationTypes
from app.services.vacation_balance_service import (
    VacationLedgerEntry,
    ensure_vacation_balance_available,
    get_employee_vacation_balance,
)


class VacationBalanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

        self.db.add(SalaryType(id=0, code="monthly", salary_type="monthly"))
        self.db.add_all(
            [
                VacationTypes(id=0, code="paid", vacation_type="paid"),
                VacationTypes(id=1, code="unpaid", vacation_type="unpaid"),
                VacationTypes(id=2, code="sick", vacation_type="sick"),
                VacationStatus(id=0, code="pending", vacation_status="pending"),
                VacationStatus(id=1, code="approved", vacation_status="approved"),
                VacationStatus(id=2, code="cancelled", vacation_status="cancelled"),
                VacationStatus(id=3, code="rejected", vacation_status="rejected"),
            ]
        )
        self.employee = Employees(
            first_name="Ava",
            last_name="Stone",
            fullname="Ava Stone",
            job_title="Analyst",
            phone="123456789",
            email="ava@example.com",
            department_id=None,
            position_id=None,
            position="Analyst",
            status="active",
            hire_date=date(2025, 1, 1),
            dues=Decimal("0.00"),
            salary_type=0,
            monthly_price=Decimal("5000.00"),
            day_price=Decimal("200.00"),
            hour_price=Decimal("25.00"),
            extra_hours_price=Decimal("30.00"),
            daily_work_hours=8,
            vacation_days=18,
            is_active=True,
            allowed_late=Decimal("0.00"),
            min_extraTime=Decimal("0.00"),
            joined=date(2025, 1, 1),
        )
        self.db.add(self.employee)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _set_policy(
        self,
        *,
        allow_carryover: bool = True,
        max_carryover_days: int | None = None,
        carryover_expiry_month: int | None = None,
        carryover_expiry_day: int | None = None,
        reserve_pending: bool = False,
    ) -> None:
        policy = PayrollPolicy(
            name="default",
            payroll_cycle="monthly",
            minimum_overtime_minutes=30,
            minimum_auto_pay_minutes=0,
            allowed_late_minutes=0,
            default_currency="USD",
            significant_change_threshold=Decimal("1.00"),
            paid_vacation_counts_for_daily=True,
            overtime_enabled=True,
            late_makeup_enabled=True,
            late_deduction_enabled=False,
            auto_recalculate_draft_payroll=True,
            lock_payroll_after_payment=True,
            holidays_json=[],
            annual_vacation_days_by_year={},
            allow_vacation_carryover=allow_carryover,
            max_vacation_carryover_days=max_carryover_days,
            carryover_expiry_month=carryover_expiry_month,
            carryover_expiry_day=carryover_expiry_day,
            reserve_vacation_days_on_pending=reserve_pending,
        )
        self.db.add(policy)
        self.db.commit()

    def _set_employee_entitlements(self, employee_id: int, annual_days: dict[int, int]) -> None:
        for year, allowed_days in annual_days.items():
            self.db.add(
                AnnualVacations(
                    year=year,
                    employee_id=employee_id,
                    allowed_days=allowed_days,
                )
            )
        self.db.commit()

    def _create_employee(self, *, first_name: str, vacation_days: int) -> Employees:
        employee = Employees(
            first_name=first_name,
            last_name="Tester",
            fullname=f"{first_name} Tester",
            job_title="Analyst",
            phone=f"555{1000 + vacation_days}",
            email=f"{first_name.lower()}@example.com",
            department_id=None,
            position_id=None,
            position="Analyst",
            status="active",
            hire_date=date(2025, 1, 1),
            dues=Decimal("0.00"),
            salary_type=0,
            monthly_price=Decimal("5000.00"),
            day_price=Decimal("200.00"),
            hour_price=Decimal("25.00"),
            extra_hours_price=Decimal("30.00"),
            daily_work_hours=8,
            vacation_days=vacation_days,
            is_active=True,
            allowed_late=Decimal("0.00"),
            min_extraTime=Decimal("0.00"),
            joined=date(2025, 1, 1),
        )
        self.db.add(employee)
        self.db.commit()
        return employee

    def _add_vacation(self, *, start_date: date, end_date: date, status: int = 1) -> None:
        self.db.add(
            Vacation(
                employee_id=self.employee.id,
                start_date=start_date,
                end_date=end_date,
                vacation_type=0,
                vacation_status=status,
                is_paid=True,
            )
        )
        self.db.commit()

    def _year_balance(self, year: int, *, as_of: date) -> dict:
        balance = get_employee_vacation_balance(
            self.employee.id,
            self.db,
            start_year=year,
            end_year=year,
            as_of=as_of,
        )
        return balance["years"][0]

    def test_uses_latest_previous_configured_year_when_target_year_is_missing(self):
        self._set_policy(allow_carryover=False)
        self._set_employee_entitlements(self.employee.id, {2026: 21, 2027: 22})

        year_2028 = self._year_balance(2028, as_of=date(2028, 1, 1))

        self.assertEqual(year_2028["entitlement_days"], 22)
        self.assertEqual(year_2028["entitlement_source_year"], 2027)
        self.assertEqual(year_2028["entitlement_source"], "fallback_previous_employee_year")

    def test_carries_unused_days_into_next_year_when_enabled(self):
        self._set_policy(allow_carryover=True)
        self._set_employee_entitlements(self.employee.id, {2026: 21, 2027: 21})
        self._add_vacation(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10))

        year_2027 = self._year_balance(2027, as_of=date(2027, 1, 2))

        self.assertEqual(year_2027["carried_over_days"], 11)
        self.assertEqual(year_2027["starting_balance_days"], 32)
        self.assertEqual(year_2027["available_days"], 32)

    def test_drops_unused_days_when_carryover_is_disabled(self):
        self._set_policy(allow_carryover=False)
        self._set_employee_entitlements(self.employee.id, {2026: 21, 2027: 21})
        self._add_vacation(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10))

        year_2027 = self._year_balance(2027, as_of=date(2027, 1, 2))

        self.assertEqual(year_2027["carried_over_days"], 0)
        self.assertEqual(year_2027["starting_balance_days"], 21)
        self.assertEqual(year_2027["available_days"], 21)

    def test_expires_unused_carryover_after_deadline(self):
        self._set_policy(
            allow_carryover=True,
            carryover_expiry_month=3,
            carryover_expiry_day=31,
        )
        self._set_employee_entitlements(self.employee.id, {2026: 21, 2027: 21})
        self._add_vacation(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10))

        year_2027 = self._year_balance(2027, as_of=date(2027, 4, 1))

        self.assertEqual(year_2027["carried_over_days"], 11)
        self.assertEqual(year_2027["carryover_expired_days"], 11)
        self.assertEqual(year_2027["active_carryover_days"], 0)
        self.assertEqual(year_2027["available_days"], 21)

    def test_pending_requests_reserve_days_when_policy_is_enabled(self):
        self._set_policy(allow_carryover=False, reserve_pending=True)
        self._set_employee_entitlements(self.employee.id, {2026: 21})
        self._add_vacation(start_date=date(2026, 2, 1), end_date=date(2026, 2, 5), status=0)

        year_2026 = self._year_balance(2026, as_of=date(2026, 2, 1))

        self.assertEqual(year_2026["pending_request_days"], 5)
        self.assertEqual(year_2026["reserved_days"], 5)
        self.assertEqual(year_2026["consumed_days"], 5)
        self.assertEqual(year_2026["available_days"], 16)

    def test_pending_requests_do_not_consume_balance_when_policy_is_disabled(self):
        self._set_policy(allow_carryover=False, reserve_pending=False)
        self._set_employee_entitlements(self.employee.id, {2026: 21})
        self._add_vacation(start_date=date(2026, 2, 1), end_date=date(2026, 2, 5), status=0)

        year_2026 = self._year_balance(2026, as_of=date(2026, 2, 1))

        self.assertEqual(year_2026["pending_request_days"], 5)
        self.assertEqual(year_2026["reserved_days"], 0)
        self.assertEqual(year_2026["consumed_days"], 0)
        self.assertEqual(year_2026["available_days"], 21)

    def test_rejects_requests_that_exceed_post_expiry_balance(self):
        self._set_policy(
            allow_carryover=True,
            carryover_expiry_month=3,
            carryover_expiry_day=31,
        )
        self._set_employee_entitlements(self.employee.id, {2026: 21, 2027: 21})
        self._add_vacation(start_date=date(2026, 5, 1), end_date=date(2026, 5, 10))

        with self.assertRaises(ConflictException):
            ensure_vacation_balance_available(
                VacationLedgerEntry(
                    id=None,
                    employee_id=self.employee.id,
                    start_date=date(2027, 4, 1),
                    end_date=date(2027, 4, 22),
                    vacation_type=0,
                    vacation_status=1,
                    is_paid=True,
                ),
                self.db,
            )

    def test_falls_back_to_employee_default_when_no_annual_rows_exist(self):
        self._set_policy(allow_carryover=False)

        year_2026 = self._year_balance(2026, as_of=date(2026, 1, 1))

        self.assertEqual(year_2026["entitlement_days"], 18)
        self.assertEqual(year_2026["entitlement_source"], "employee_default")

    def test_employees_can_have_different_entitlements_for_the_same_year(self):
        self._set_policy(allow_carryover=False)
        second_employee = self._create_employee(first_name="Lina", vacation_days=25)
        self._set_employee_entitlements(self.employee.id, {2026: 21})
        self._set_employee_entitlements(second_employee.id, {2026: 28})

        first_balance = get_employee_vacation_balance(
            self.employee.id,
            self.db,
            start_year=2026,
            end_year=2026,
            as_of=date(2026, 1, 1),
        )
        second_balance = get_employee_vacation_balance(
            second_employee.id,
            self.db,
            start_year=2026,
            end_year=2026,
            as_of=date(2026, 1, 1),
        )

        self.assertEqual(first_balance["years"][0]["entitlement_days"], 21)
        self.assertEqual(second_balance["years"][0]["entitlement_days"], 28)


if __name__ == "__main__":
    unittest.main()
