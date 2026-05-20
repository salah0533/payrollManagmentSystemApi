import unittest
import json
from datetime import date, datetime, time, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import Base
from app.exceptions.base_exception import BadRequestException
from app.models.auth import User
from app.models.attendance_payroll import (
    AttendanceDay,
    EmployeeCompensation,
    EmployeePayroll,
    PayrollCalculationHistory,
    PayrollDiscrepancy,
    PayrollPolicy,
    WorkSchedule,
)
from app.models.employees import Employees
from app.models.notifications import Notification
from app.models.payment_types import PaymentTypes
from app.models.salary_type import SalaryType
from app.routes.routes.settings import put_payroll_policy
from app.schemas.attendance_payroll import AttendanceCorrectionRequest
from app.schemas.attendance_payroll import PayrollPolicyPayload
from app.services.attendance_calculation_service import (
    apply_smart_attendance_status_correction,
    calculate_attendance_day,
    create_attendance_correction,
    create_attendance_event,
    delete_attendance_day,
    get_attendance_days,
    get_attendance_days_by_date,
    process_pending_attendance_notifications,
)
from app.services.payroll_calculation_service import (
    approve_employee_payroll,
    calculate_employee_payroll,
    calculate_monthly_employee_payroll,
    create_payroll_history_snapshot,
    get_employee_payroll_by_period,
    get_or_create_payroll_period_for_date,
    get_payroll_discrepancies,
    mark_employee_payroll_paid,
    reconcile_existing_payrolls_for_settings_change,
)
from app.services.policy_service import get_employee_compensation, get_working_days, parse_holidays


class AttendancePayrollRefactorTests(unittest.TestCase):
    def setUp(self):
        self.today_patcher = patch("app.services.payroll_calculation_service._today", return_value=date(2026, 6, 1))
        self.today_patcher.start()
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
                    weekly_off_days=["friday", "saturday"],
                    timezone="UTC",
                    is_default=True,
                ),
                PayrollPolicy(
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
                    monthly_payroll_calculation_mode="working_days",
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
            monthly_price=Decimal("85000.00"),
            day_price=Decimal("16800.00"),
            hour_price=Decimal("2100.00"),
            extra_hours_price=Decimal("2600.00"),
            daily_work_hours=8,
            vacation_days=0,
            is_active=True,
            allowed_late=Decimal("0.00"),
            min_extraTime=Decimal("0.00"),
            joined=date(2026, 1, 1),
        )
        self.db.add(self.employee)
        self.db.flush()
        self.user = User(
            employee_id=self.employee.id,
            username="jane-user",
            password_hash="hash",
            is_active=True,
            must_change_password=False,
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.today_patcher.stop()

    def _schedule(self) -> WorkSchedule:
        return self.db.scalar(select(WorkSchedule).where(WorkSchedule.is_default.is_(True)))

    def _policy(self) -> PayrollPolicy:
        return self.db.scalar(select(PayrollPolicy).order_by(PayrollPolicy.id))

    def _payroll_period_for_month(self, year: int, month: int):
        return get_or_create_payroll_period_for_date(date(year, month, 1), self.db)

    def _working_days_for_period(self, period) -> list[date]:
        schedule = self._schedule()
        holidays = parse_holidays(self._policy().holidays_json)
        return get_working_days(period.start_date, period.end_date, schedule, holidays)

    def _month_days(self, *, absent_dates: set[date] | None = None, overtime_minutes_by_date: dict[date, int] | None = None) -> list[AttendanceDay]:
        absent_dates = absent_dates or set()
        overtime_minutes_by_date = overtime_minutes_by_date or {}
        schedule = self._schedule()
        expected_minutes = int((datetime.combine(date.today(), schedule.end_time) - datetime.combine(date.today(), schedule.start_time)).total_seconds() // 60)
        days: list[AttendanceDay] = []
        period = self._payroll_period_for_month(2026, 5)
        for work_date in self._working_days_for_period(period):
            is_absent = work_date in absent_dates
            overtime_minutes = overtime_minutes_by_date.get(work_date, 0)
            normal_paid_minutes = 0 if is_absent else expected_minutes
            days.append(
                AttendanceDay(
                    employee_id=self.employee.id,
                    work_date=work_date,
                    expected_work_minutes=expected_minutes,
                    actual_work_minutes=0 if is_absent else expected_minutes + overtime_minutes,
                    normal_paid_minutes=normal_paid_minutes,
                    late_minutes=0,
                    early_leave_minutes=0,
                    late_makeup_minutes=0,
                    overtime_minutes=overtime_minutes,
                    absence_minutes=expected_minutes if is_absent else 0,
                    unpaid_minutes=expected_minutes if is_absent else 0,
                    status="absent" if is_absent else "present",
                    review_status="approved",
                )
            )
        return days

    def _payroll_stub(self, period) -> EmployeePayroll:
        payroll = EmployeePayroll(
            payroll_period_id=period.id,
            employee_id=self.employee.id,
            salary_type="monthly",
            status="draft",
        )
        self.db.add(payroll)
        self.db.flush()
        return payroll

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

    def test_allowed_late_grace_at_exact_limit_stays_present(self):
        policy = self._policy()
        policy.allowed_late_minutes = 30
        self.db.add(policy)
        self.db.commit()

        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 6, 9, 30, tzinfo=timezone.utc),
            self.db,
        )
        _, day = create_attendance_event(
            self.employee.id,
            "check_out",
            datetime(2026, 5, 6, 17, 0, tzinfo=timezone.utc),
            self.db,
        )

        self.assertEqual(day.status, "present")
        self.assertEqual(day.late_minutes, 0)
        self.assertEqual(day.unpaid_minutes, 0)
        self.assertEqual(day.normal_paid_minutes, 480)

    def test_allowed_late_grace_counts_full_lateness_after_crossing_the_limit(self):
        policy = self._policy()
        policy.allowed_late_minutes = 30
        self.db.add(policy)
        self.db.commit()

        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 6, 9, 31, tzinfo=timezone.utc),
            self.db,
        )
        _, day = create_attendance_event(
            self.employee.id,
            "check_out",
            datetime(2026, 5, 6, 17, 0, tzinfo=timezone.utc),
            self.db,
        )

        self.assertEqual(day.status, "late")
        self.assertEqual(day.late_minutes, 31)
        self.assertEqual(day.normal_paid_minutes, 449)
        self.assertEqual(day.unpaid_minutes, 31)

    def test_scheduled_break_without_break_events_reduces_worked_and_paid_time(self):
        schedule = self._schedule()
        schedule.start_time = time(8, 0)
        schedule.end_time = time(17, 0)
        schedule.break_start_time = time(12, 0)
        schedule.break_end_time = time(13, 0)
        schedule.break_minutes = 60
        self.db.add(schedule)

        policy = self._policy()
        policy.allowed_late_minutes = 30
        self.db.add(policy)
        self.db.commit()

        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 6, 8, 45, tzinfo=timezone.utc),
            self.db,
        )
        _, day = create_attendance_event(
            self.employee.id,
            "check_out",
            datetime(2026, 5, 6, 17, 0, tzinfo=timezone.utc),
            self.db,
        )

        self.assertEqual(day.actual_work_minutes, 435)
        self.assertEqual(day.break_minutes, 60)
        self.assertEqual(day.status, "late")
        self.assertEqual(day.late_minutes, 45)
        self.assertEqual(day.normal_paid_minutes, 435)
        self.assertEqual(day.unpaid_minutes, 45)

    def test_smart_correction_honors_custom_check_out_for_unpaid_minutes(self):
        correction, day = apply_smart_attendance_status_correction(
            self.employee.id,
            date(2026, 5, 7),
            "late",
            corrected_by=1,
            reason="Approve late arrival with early departure",
            options={"check_in_time": "09:31", "check_out_time": "16:00"},
            db=self.db,
        )

        self.assertEqual(correction.new_values_json["check_in_time"], "09:31:00")
        self.assertEqual(correction.new_values_json["check_out_time"], "16:00:00")
        self.assertEqual(day.status, "late")
        self.assertEqual(day.check_out_time, time(16, 0))
        self.assertEqual(day.late_minutes, 31)
        self.assertEqual(day.early_leave_minutes, 60)
        self.assertEqual(day.unpaid_minutes, 91)

    def test_manual_time_correction_after_smart_status_recomputes_status(self):
        work_date = date(2026, 5, 11)
        apply_smart_attendance_status_correction(
            self.employee.id,
            work_date,
            "present",
            corrected_by=1,
            reason="Seed full-day attendance",
            options={},
            db=self.db,
        )

        correction, updated_day = create_attendance_correction(
            AttendanceCorrectionRequest(
                employee_id=self.employee.id,
                work_date=work_date,
                correction_type="field",
                new_values_json={"check_in_time": "09:31"},
                reason="Adjust the actual check-in time",
                corrected_by=1,
            ),
            self.db,
        )

        self.assertEqual(correction.new_values_json, {"check_in_time": "09:31"})
        self.assertEqual(updated_day.status, "late")
        self.assertEqual(updated_day.late_minutes, 31)
        self.assertEqual(updated_day.unpaid_minutes, 31)

        recalculated_day = calculate_attendance_day(self.employee.id, work_date, self.db, trigger_reason="manual_recalculation")

        self.assertEqual(recalculated_day.status, "late")
        self.assertEqual(recalculated_day.late_minutes, 31)

    def test_manual_correction_allows_blank_reason(self):
        correction, updated_day = create_attendance_correction(
            AttendanceCorrectionRequest(
                employee_id=self.employee.id,
                work_date=date(2026, 5, 12),
                correction_type="field",
                new_values_json={"check_in_time": "09:15"},
                reason="   ",
                corrected_by=1,
            ),
            self.db,
        )

        self.assertEqual(correction.reason, "")
        self.assertEqual(updated_day.check_in_time, time(9, 15))

    def test_missing_checkout_notification_waits_until_schedule_end(self):
        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 6, 9, 0, tzinfo=timezone.utc),
            self.db,
        )

        early_result = process_pending_attendance_notifications(
            self.db,
            now=datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        )
        self.db.commit()

        self.assertEqual(early_result["sent"], 0)
        self.assertEqual(self.db.scalars(select(Notification)).all(), [])

        late_result = process_pending_attendance_notifications(
            self.db,
            now=datetime(2026, 5, 6, 17, 5, tzinfo=timezone.utc),
        )
        self.db.commit()
        notifications = self.db.scalars(select(Notification).order_by(Notification.created_at.asc())).all()

        self.assertEqual(late_result["sent"], 1)
        self.assertEqual([item.notification_type for item in notifications], ["attendance_missing_checkout"])

    def test_break_notifications_follow_configured_break_window(self):
        schedule = self._schedule()
        schedule.break_start_time = time(12, 0)
        schedule.break_end_time = time(13, 0)
        schedule.break_minutes = 60
        self.db.add(schedule)
        self.db.commit()

        create_attendance_event(
            self.employee.id,
            "check_in",
            datetime(2026, 5, 7, 9, 0, tzinfo=timezone.utc),
            self.db,
        )

        break_start_result = process_pending_attendance_notifications(
            self.db,
            now=datetime(2026, 5, 7, 12, 5, tzinfo=timezone.utc),
        )
        self.db.commit()

        self.assertEqual(break_start_result["sent"], 1)
        self.assertEqual(
            [item.notification_type for item in self.db.scalars(select(Notification).order_by(Notification.created_at.asc())).all()],
            ["attendance_missing_break_start"],
        )

        create_attendance_event(
            self.employee.id,
            "break_start",
            datetime(2026, 5, 7, 12, 10, tzinfo=timezone.utc),
            self.db,
        )
        break_end_result = process_pending_attendance_notifications(
            self.db,
            now=datetime(2026, 5, 7, 13, 5, tzinfo=timezone.utc),
        )
        self.db.commit()
        notifications = self.db.scalars(select(Notification).order_by(Notification.created_at.asc())).all()

        self.assertEqual(break_end_result["sent"], 1)
        self.assertEqual(
            [item.notification_type for item in notifications],
            ["attendance_missing_break_start", "attendance_missing_break_end"],
        )

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

    def test_deleting_only_attendance_day_deletes_empty_auto_payroll(self):
        work_date = date(2026, 5, 12)
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
        payroll_id = payroll.id

        result = delete_attendance_day(self.employee.id, work_date, self.db, deleted_by=1)

        deleted_day = self.db.scalar(
            select(AttendanceDay).where(
                AttendanceDay.employee_id == self.employee.id,
                AttendanceDay.work_date == work_date,
            )
        )
        deleted_payroll = self.db.get(EmployeePayroll, payroll_id)

        self.assertEqual(result["payroll_sync_status"], "deleted_empty_payroll")
        self.assertIsNone(deleted_day)
        self.assertIsNone(deleted_payroll)

    def test_deleting_attendance_day_recalculates_existing_period_payroll(self):
        deleted_date = date(2026, 5, 12)
        remaining_date = date(2026, 5, 13)
        for work_date in (deleted_date, remaining_date):
            apply_smart_attendance_status_correction(
                self.employee.id,
                work_date,
                "present",
                corrected_by=1,
                reason="Seed attendance",
                options={},
                db=self.db,
            )
        period = get_or_create_payroll_period_for_date(deleted_date, self.db)
        payroll = get_employee_payroll_by_period(self.employee.id, period.id, self.db)

        result = delete_attendance_day(self.employee.id, deleted_date, self.db, deleted_by=1)
        payroll_after = self.db.get(EmployeePayroll, payroll.id)
        open_discrepancies = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()

        self.assertEqual(result["payroll_sync_status"], "recalculated")
        self.assertIsNotNone(payroll_after)
        self.assertEqual(payroll_after.status, "needs_review")
        self.assertTrue(
            any(
                item.discrepancy_type == "missing_attendance"
                and deleted_date.isoformat() in item.description
                for item in open_discrepancies
            )
        )

    def test_work_schedule_change_reconciles_missing_attendance_discrepancies(self):
        target_date = date(2026, 5, 3)
        self.db.add_all([day for day in self._month_days() if day.work_date != target_date])
        self.db.commit()

        period = self._payroll_period_for_month(2026, 5)
        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db)
        self.db.commit()

        open_before = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        self.assertTrue(
            any(
                item.discrepancy_type == "missing_attendance"
                and target_date.isoformat() in item.description
                for item in open_before
            )
        )

        schedule = self._schedule()
        schedule.weekly_off_days = ["saturday", "sunday"]
        self.db.add(schedule)
        reconcile_existing_payrolls_for_settings_change(self.db, reason="work_schedule_updated")
        self.db.commit()

        open_after = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        self.assertFalse(
            any(
                item.discrepancy_type == "missing_attendance"
                and target_date.isoformat() in item.description
                for item in open_after
            )
        )

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

    def test_monthly_payroll_uses_period_auto_rates_when_no_override_exists(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        absence_date = date(2026, 5, 3)
        days = self._month_days(absent_dates={absence_date})

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)
        compensation = get_employee_compensation(self.employee.id, period.end_date, self.db)

        self.assertEqual(len(self._working_days_for_period(period)), 21)
        self.assertEqual(compensation.daily_rate, Decimal("0.00"))
        self.assertEqual(compensation.hourly_rate, Decimal("0.00"))
        self.assertIsNone(compensation.daily_rate_override)
        self.assertIsNone(compensation.hourly_rate_override)
        self.assertEqual(results["calculation_data_json"]["period_expected_minutes"], 10080)
        self.assertEqual(results["calculation_data_json"]["paid_minutes"], 9600)
        self.assertEqual(results["calculation_data_json"]["missing_workday_minutes"], 0)
        self.assertEqual(results["calculation_data_json"]["attendance_deduction"], "4047.62")
        self.assertEqual(results["calculation_data_json"]["late_penalty_amount"], "0.00")
        self.assertEqual(results["attendance_deduction_amount"], Decimal("4047.62"))
        self.assertAlmostEqual(Decimal(results["calculation_data_json"]["resolved_daily_rate"]), Decimal("4047.619047619047619047619048"))
        self.assertEqual(results["calculation_data_json"]["rate_source"], "auto")
        self.assertEqual(results["deduction_amount"], Decimal("4047.62"))
        self.assertEqual(results["net_salary"], Decimal("80952.38"))

    def test_monthly_payroll_keeps_auto_minute_rate_even_with_daily_override(self):
        period = self._payroll_period_for_month(2026, 5)
        self.db.add(
            EmployeeCompensation(
                employee_id=self.employee.id,
                salary_type="monthly",
                base_monthly_salary=Decimal("85000.00"),
                daily_rate=Decimal("0.00"),
                hourly_rate=Decimal("0.00"),
                overtime_rate=Decimal("0.00"),
                late_deduction_rate=Decimal("0.00"),
                daily_rate_override=Decimal("5000.00"),
                hourly_rate_override=None,
                overtime_rate_override=None,
                late_deduction_rate_override=None,
                currency="DZD",
                effective_from=date(2026, 1, 1),
                is_active=True,
            )
        )
        self.db.flush()
        payroll = self._payroll_stub(period)
        days = self._month_days(absent_dates={date(2026, 5, 3)})

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(results["deduction_amount"], Decimal("4047.62"))
        self.assertEqual(results["net_salary"], Decimal("80952.38"))
        self.assertEqual(results["calculation_data_json"]["attendance_deduction"], "4047.62")
        self.assertEqual(results["calculation_data_json"]["auto_minute_rate"], "8.432539682539682539682539683")
        self.assertEqual(results["calculation_data_json"]["rate_source"], "override")
        self.assertEqual(results["calculation_data_json"]["rate_sources"]["daily_rate"], "override")

    def test_monthly_payroll_does_not_double_deduct_partial_late_day(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        policy = self._policy()
        policy.late_deduction_enabled = True
        self.db.add(policy)
        self.db.flush()
        days = self._month_days(absent_dates={date(2026, 5, 3)})
        for day in days:
            if day.work_date == date(2026, 5, 4):
                day.actual_work_minutes = 420
                day.normal_paid_minutes = 420
                day.late_minutes = 60
                day.unpaid_minutes = 60
                day.status = "late"

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(results["calculation_data_json"]["unpaid_minutes"], 540)
        self.assertEqual(results["calculation_data_json"]["partial_unpaid_minutes"], 60)
        self.assertEqual(results["attendance_deduction_amount"], Decimal("4553.57"))
        self.assertEqual(results["calculation_data_json"]["late_penalty_eligible_minutes"], 0)
        self.assertEqual(results["late_deduction_amount"], Decimal("0.00"))
        self.assertEqual(results["net_salary"], Decimal("80446.43"))

    def test_monthly_overtime_falls_back_to_auto_hourly_rate_without_override(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        days = self._month_days(overtime_minutes_by_date={date(2026, 5, 4): 120})

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(Decimal(results["calculation_data_json"]["resolved_overtime_rate"]), Decimal("2600.00"))
        self.assertEqual(results["overtime_amount"], Decimal("5200.00"))
        self.assertEqual(results["calculation_data_json"]["rate_sources"]["overtime_rate"], "configured")

    def test_monthly_compensation_repairs_legacy_zero_overtime_rate_from_employee_price(self):
        period = self._payroll_period_for_month(2026, 5)
        self.db.add(
            EmployeeCompensation(
                employee_id=self.employee.id,
                salary_type="monthly",
                base_monthly_salary=Decimal("85000.00"),
                daily_rate=Decimal("0.00"),
                hourly_rate=Decimal("0.00"),
                overtime_rate=Decimal("0.00"),
                late_deduction_rate=Decimal("0.00"),
                daily_rate_override=None,
                hourly_rate_override=None,
                overtime_rate_override=None,
                late_deduction_rate_override=None,
                currency="DZD",
                effective_from=date(2026, 1, 1),
                is_active=True,
            )
        )
        self.db.commit()

        compensation = get_employee_compensation(self.employee.id, period.end_date, self.db)

        self.assertEqual(compensation.overtime_rate, Decimal("2600.00"))

    def test_monthly_overtime_falls_back_to_auto_hourly_rate_when_no_configured_rate_exists(self):
        period = self._payroll_period_for_month(2026, 5)
        self.employee.extra_hours_price = Decimal("0.00")
        self.db.add(self.employee)
        self.db.add(
            EmployeeCompensation(
                employee_id=self.employee.id,
                salary_type="monthly",
                base_monthly_salary=Decimal("85000.00"),
                daily_rate=Decimal("0.00"),
                hourly_rate=Decimal("0.00"),
                overtime_rate=Decimal("0.00"),
                late_deduction_rate=Decimal("0.00"),
                daily_rate_override=None,
                hourly_rate_override=None,
                overtime_rate_override=None,
                late_deduction_rate_override=None,
                currency="DZD",
                effective_from=date(2026, 1, 1),
                is_active=True,
            )
        )
        self.db.commit()
        payroll = self._payroll_stub(period)
        days = self._month_days(overtime_minutes_by_date={date(2026, 5, 4): 120})

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertAlmostEqual(Decimal(results["calculation_data_json"]["resolved_overtime_rate"]), Decimal("505.9523809523809523809523810"))
        self.assertEqual(results["overtime_amount"], Decimal("1011.90"))
        self.assertEqual(results["calculation_data_json"]["rate_sources"]["overtime_rate"], "auto")

    def test_monthly_legacy_daily_or_hourly_rates_trigger_needs_review(self):
        period = self._payroll_period_for_month(2026, 5)
        for day in self._month_days():
            self.db.add(day)
        self.db.add(
            EmployeeCompensation(
                employee_id=self.employee.id,
                salary_type="monthly",
                base_monthly_salary=Decimal("85000.00"),
                daily_rate=Decimal("16800.00"),
                hourly_rate=Decimal("2100.00"),
                overtime_rate=Decimal("0.00"),
                late_deduction_rate=Decimal("0.00"),
                daily_rate_override=None,
                hourly_rate_override=None,
                overtime_rate_override=None,
                late_deduction_rate_override=None,
                currency="DZD",
                effective_from=date(2026, 1, 1),
                is_active=True,
            )
        )
        self.db.commit()

        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
        latest_history = self.db.scalar(
            select(PayrollCalculationHistory)
            .where(PayrollCalculationHistory.employee_payroll_id == payroll.id)
            .order_by(PayrollCalculationHistory.id.desc())
        )

        self.assertEqual(payroll.status, "needs_review")
        self.assertTrue(latest_history.calculation_data_json["rate_review_warnings"])
        self.assertIn("daily_rate=16800.00", latest_history.calculation_data_json["rate_review_warnings"][0])

    def test_monthly_payroll_caps_automatic_deduction_at_base_salary(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)

        results = calculate_monthly_employee_payroll(payroll, period, [], self.db)

        self.assertEqual(results["attendance_deduction_amount"], Decimal("85000.00"))
        self.assertEqual(results["late_deduction_amount"], Decimal("0.00"))
        self.assertEqual(results["net_salary"], Decimal("0.00"))
        self.assertEqual(results["calculation_data_json"]["paid_minutes"], 0)

    def test_monthly_tiny_attendance_can_be_paid_when_minimum_policy_is_disabled(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        work_date = self._working_days_for_period(period)[0]
        days = [
            AttendanceDay(
                employee_id=self.employee.id,
                work_date=work_date,
                expected_work_minutes=480,
                actual_work_minutes=1,
                normal_paid_minutes=1,
                late_minutes=0,
                early_leave_minutes=0,
                late_makeup_minutes=0,
                overtime_minutes=0,
                absence_minutes=0,
                unpaid_minutes=479,
                status="present",
                review_status="approved",
            )
        ]

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(results["calculation_data_json"]["paid_minutes"], 1)
        self.assertEqual(results["calculation_data_json"]["earned_paid_minutes"], 1)
        self.assertEqual(results["calculation_data_json"]["held_for_review_amount"], "0.00")
        self.assertEqual(results["net_salary"], Decimal("8.43"))
        self.assertEqual(results["total_amount"], Decimal("8.43"))
        self.assertFalse(results["needs_review"])

    def test_monthly_tiny_attendance_is_held_for_review_when_minimum_policy_is_enabled(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        policy = self._policy()
        policy.minimum_auto_pay_minutes = 5
        self.db.add(policy)
        self.db.flush()
        work_date = self._working_days_for_period(period)[0]
        days = [
            AttendanceDay(
                employee_id=self.employee.id,
                work_date=work_date,
                expected_work_minutes=480,
                actual_work_minutes=1,
                normal_paid_minutes=1,
                late_minutes=0,
                early_leave_minutes=0,
                late_makeup_minutes=0,
                overtime_minutes=0,
                absence_minutes=0,
                unpaid_minutes=479,
                status="present",
                review_status="draft",
            )
        ]

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(results["calculation_data_json"]["attendance_review_held_minutes"], 1)
        self.assertEqual(results["calculation_data_json"]["earned_paid_minutes"], 1)
        self.assertEqual(results["calculation_data_json"]["paid_minutes"], 0)
        self.assertEqual(results["calculation_data_json"]["earned_net_salary"], "8.43")
        self.assertEqual(results["calculation_data_json"]["held_for_review_amount"], "8.43")
        self.assertEqual(results["net_salary"], Decimal("8.43"))
        self.assertEqual(results["total_amount"], Decimal("0.00"))
        self.assertTrue(results["needs_review"])
        self.assertEqual(days[0].review_status, "needs_review")

    def test_monthly_tiny_attendance_keeps_one_minute_earned_when_late_penalty_enabled(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        policy = self._policy()
        policy.late_deduction_enabled = True
        self.db.add(policy)
        self.db.flush()
        work_date = self._working_days_for_period(period)[0]
        days = [
            AttendanceDay(
                employee_id=self.employee.id,
                work_date=work_date,
                expected_work_minutes=480,
                actual_work_minutes=1,
                normal_paid_minutes=1,
                late_minutes=239,
                early_leave_minutes=300,
                late_makeup_minutes=0,
                overtime_minutes=0,
                absence_minutes=0,
                unpaid_minutes=479,
                status="late",
                review_status="approved",
            )
        ]

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(results["calculation_data_json"]["late_penalty_eligible_minutes"], 0)
        self.assertEqual(results["late_deduction_amount"], Decimal("0.00"))
        self.assertEqual(results["net_salary"], Decimal("8.43"))
        self.assertEqual(results["total_amount"], Decimal("8.43"))

    def test_approving_tiny_monthly_attendance_releases_payable_amount(self):
        period = self._payroll_period_for_month(2026, 5)
        policy = self._policy()
        policy.minimum_auto_pay_minutes = 5
        self.db.add(policy)
        self.db.flush()
        work_date = self._working_days_for_period(period)[0]
        day = AttendanceDay(
            employee_id=self.employee.id,
            work_date=work_date,
            expected_work_minutes=480,
            actual_work_minutes=1,
            normal_paid_minutes=1,
            late_minutes=0,
            early_leave_minutes=0,
            late_makeup_minutes=0,
            overtime_minutes=0,
            absence_minutes=0,
            unpaid_minutes=479,
            status="present",
            review_status="draft",
        )
        payroll = EmployeePayroll(
            payroll_period_id=period.id,
            employee_id=self.employee.id,
            salary_type="monthly",
            status="draft",
        )
        results = calculate_monthly_employee_payroll(payroll, period, [day], self.db)
        for field_name, value in results.items():
            if field_name in {"calculation_data_json", "needs_review"}:
                continue
            setattr(payroll, field_name, value)
        payroll.status = "needs_review"
        payroll.total_amount = Decimal("0.00")
        payroll.balance_amount = Decimal("0.00")
        self.db.add(payroll)
        self.db.flush()
        create_payroll_history_snapshot(
            payroll,
            old_gross_salary=Decimal("0.00"),
            old_net_salary=Decimal("0.00"),
            reason="seed_needs_review_tiny_attendance",
            calculation_data_json=results["calculation_data_json"],
            db=self.db,
            created_by=1,
        )
        self.db.commit()

        self.assertEqual(Decimal(str(payroll.net_salary)), Decimal("8.43"))
        self.assertEqual(Decimal(str(payroll.total_amount)), Decimal("0.00"))
        self.assertEqual(payroll.status, "needs_review")

        approved = approve_employee_payroll(payroll.id, self.db, approved_by=1)

        self.assertEqual(Decimal(str(approved.net_salary)), Decimal("8.43"))
        self.assertEqual(Decimal(str(approved.total_amount)), Decimal("8.43"))
        self.assertEqual(Decimal(str(approved.balance_amount)), Decimal("8.43"))
        self.assertEqual(approved.status, "approved")

    def test_current_period_monthly_payroll_accrues_through_today(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        cutoff = date(2026, 5, 19)
        days = [day for day in self._month_days() if day.work_date <= cutoff]

        with patch("app.services.payroll_calculation_service._today", return_value=cutoff):
            results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        full_workdays = len(self._working_days_for_period(period))
        accrued_workdays = len([work_day for work_day in self._working_days_for_period(period) if work_day <= cutoff])
        expected_period_minutes = accrued_workdays * 480
        expected_net_salary = (Decimal("85000.00") * Decimal(accrued_workdays) / Decimal(full_workdays)).quantize(Decimal("0.01"))

        self.assertEqual(results["calculation_data_json"]["effective_cutoff_date"], "2026-05-19")
        self.assertEqual(results["calculation_data_json"]["working_days_count"], accrued_workdays)
        self.assertEqual(results["calculation_data_json"]["period_expected_minutes"], expected_period_minutes)
        self.assertEqual(results["calculation_data_json"]["missing_attendance_days"], 0)
        self.assertEqual(results["attendance_deduction_amount"], Decimal("0.00"))
        self.assertEqual(results["net_salary"], expected_net_salary)
        self.assertEqual(results["total_amount"], expected_net_salary)

    def test_calendar_days_mode_uses_full_month_calendar_denominator(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        policy = self._policy()
        policy.monthly_payroll_calculation_mode = "calendar_days"
        self.db.add(policy)
        self.db.flush()
        absence_date = date(2026, 5, 3)
        days = self._month_days(absent_dates={absence_date})

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(results["calculation_data_json"]["monthly_payroll_calculation_mode"], "calendar_days")
        self.assertEqual(results["calculation_data_json"]["working_days_count"], 21)
        self.assertEqual(results["calculation_data_json"]["payroll_basis_days_count"], 31)
        self.assertEqual(results["calculation_data_json"]["period_expected_minutes"], 14880)
        self.assertEqual(results["calculation_data_json"]["full_period_payroll_basis_days_count"], 31)
        self.assertEqual(results["calculation_data_json"]["auto_minute_rate"], "5.712365591397849462365591398")
        self.assertEqual(results["attendance_deduction_amount"], Decimal("2741.94"))
        self.assertEqual(results["net_salary"], Decimal("82258.06"))

    def test_calendar_days_mode_treats_weekly_off_rows_as_paid_without_deduction(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        policy = self._policy()
        policy.monthly_payroll_calculation_mode = "calendar_days"
        self.db.add(policy)
        self.db.flush()
        days = self._month_days()
        weekly_off_date = date(2026, 5, 1)
        days.append(
            AttendanceDay(
                employee_id=self.employee.id,
                work_date=weekly_off_date,
                expected_work_minutes=0,
                actual_work_minutes=0,
                normal_paid_minutes=0,
                late_minutes=0,
                early_leave_minutes=0,
                late_makeup_minutes=0,
                overtime_minutes=0,
                absence_minutes=0,
                unpaid_minutes=0,
                status="weekly_off",
                review_status="approved",
            )
        )

        results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        self.assertEqual(days[-1].status, "weekly_off")
        self.assertEqual(results["calculation_data_json"]["missing_attendance_days"], 0)
        self.assertEqual(results["attendance_deduction_amount"], Decimal("0.00"))
        self.assertEqual(results["net_salary"], Decimal("85000.00"))

    def test_employee_range_read_materializes_weekly_off_rows_as_approved(self):
        rows = get_attendance_days(self.employee.id, date(2026, 5, 1), date(2026, 5, 3), self.db)

        self.assertEqual([row.work_date for row in rows], [date(2026, 5, 1), date(2026, 5, 2)])
        self.assertTrue(all(row.status == "weekly_off" for row in rows))
        self.assertTrue(all(row.review_status == "approved" for row in rows))
        self.assertTrue(all(row.reviewed_at is not None for row in rows))
        self.assertTrue(all(row.unpaid_minutes == 0 for row in rows))
        self.assertTrue(all(row.absence_minutes == 0 for row in rows))
        stored_rows = self.db.scalars(
            select(AttendanceDay)
            .where(
                AttendanceDay.employee_id == self.employee.id,
                AttendanceDay.work_date >= date(2026, 5, 1),
                AttendanceDay.work_date <= date(2026, 5, 3),
            )
            .order_by(AttendanceDay.work_date.asc())
        ).all()
        self.assertEqual([row.work_date for row in stored_rows], [date(2026, 5, 1), date(2026, 5, 2)])

    def test_daily_read_materializes_weekly_off_rows_for_active_employees_only(self):
        inactive_employee = Employees(
            first_name="Inactive",
            last_name="Employee",
            fullname="Inactive Employee",
            job_title="Engineer",
            phone="0987654321",
            email="inactive@example.com",
            department_id=None,
            position_id=None,
            position=None,
            status="inactive",
            hire_date=date(2026, 1, 1),
            dues=Decimal("0.00"),
            salary_type=0,
            monthly_price=Decimal("1000.00"),
            day_price=Decimal("0.00"),
            hour_price=Decimal("0.00"),
            extra_hours_price=Decimal("0.00"),
            daily_work_hours=8,
            vacation_days=0,
            is_active=False,
            allowed_late=Decimal("0.00"),
            min_extraTime=Decimal("0.00"),
            joined=date(2026, 1, 1),
        )
        self.db.add(inactive_employee)
        self.db.commit()

        rows = get_attendance_days_by_date(date(2026, 5, 1), self.db)

        self.assertEqual([row.employee_id for row in rows], [self.employee.id])
        self.assertEqual(rows[0].status, "weekly_off")

    def test_weekly_off_materialization_is_idempotent_and_does_not_create_payroll_history(self):
        before_history_count = len(self.db.scalars(select(PayrollCalculationHistory)).all())

        first_rows = get_attendance_days(self.employee.id, date(2026, 5, 1), date(2026, 5, 3), self.db)
        second_rows = get_attendance_days(self.employee.id, date(2026, 5, 1), date(2026, 5, 3), self.db)

        stored_rows = self.db.scalars(
            select(AttendanceDay)
            .where(
                AttendanceDay.employee_id == self.employee.id,
                AttendanceDay.work_date >= date(2026, 5, 1),
                AttendanceDay.work_date <= date(2026, 5, 3),
            )
            .order_by(AttendanceDay.work_date.asc())
        ).all()

        self.assertEqual(len(first_rows), 2)
        self.assertEqual(len(second_rows), 2)
        self.assertEqual([row.work_date for row in stored_rows], [date(2026, 5, 1), date(2026, 5, 2)])
        self.assertEqual(len(self.db.scalars(select(PayrollCalculationHistory)).all()), before_history_count)

    def test_weekly_off_date_cannot_be_corrected_to_absent(self):
        with self.assertRaises(BadRequestException):
            apply_smart_attendance_status_correction(
                self.employee.id,
                date(2026, 5, 1),
                "absent",
                corrected_by=1,
                reason="Attempt to mark weekly off absent",
                options={},
                db=self.db,
            )
        self.db.rollback()

    def test_weekly_off_date_can_be_corrected_to_unpaid(self):
        correction, day = apply_smart_attendance_status_correction(
            self.employee.id,
            date(2026, 5, 1),
            "unpaid",
            corrected_by=1,
            reason="Convert weekly off to unpaid",
            options={},
            db=self.db,
        )

        self.assertEqual(correction.new_values_json["status"], "unpaid")
        self.assertEqual(day.status, "unpaid")
        self.assertEqual(day.expected_work_minutes, 480)
        self.assertEqual(day.unpaid_minutes, 480)
        self.assertEqual(day.normal_paid_minutes, 0)
        self.assertEqual(day.absence_minutes, 0)

    def test_current_period_calendar_days_mode_accrues_through_cutoff_date(self):
        period = self._payroll_period_for_month(2026, 5)
        payroll = self._payroll_stub(period)
        policy = self._policy()
        policy.monthly_payroll_calculation_mode = "calendar_days"
        self.db.add(policy)
        self.db.flush()
        cutoff = date(2026, 5, 19)
        days = [day for day in self._month_days() if day.work_date <= cutoff]

        with patch("app.services.payroll_calculation_service._today", return_value=cutoff):
            results = calculate_monthly_employee_payroll(payroll, period, days, self.db)

        expected_period_minutes = 19 * 480
        expected_net_salary = (Decimal("85000.00") * Decimal("19") / Decimal("31")).quantize(Decimal("0.01"))

        self.assertEqual(results["calculation_data_json"]["monthly_payroll_calculation_mode"], "calendar_days")
        self.assertEqual(results["calculation_data_json"]["effective_cutoff_date"], "2026-05-19")
        self.assertEqual(results["calculation_data_json"]["working_days_count"], 13)
        self.assertEqual(results["calculation_data_json"]["payroll_basis_days_count"], 19)
        self.assertEqual(results["calculation_data_json"]["period_expected_minutes"], expected_period_minutes)
        self.assertEqual(results["attendance_deduction_amount"], Decimal("0.00"))
        self.assertEqual(results["net_salary"], expected_net_salary)
        self.assertEqual(results["total_amount"], expected_net_salary)

    def test_switching_payroll_mode_through_settings_triggers_reconciliation(self):
        policy = self._policy()
        payload = PayrollPolicyPayload(
            name=policy.name,
            payroll_cycle=policy.payroll_cycle,
            minimum_overtime_minutes=policy.minimum_overtime_minutes,
            minimum_auto_pay_minutes=policy.minimum_auto_pay_minutes,
            allowed_late_minutes=policy.allowed_late_minutes,
            default_currency=policy.default_currency,
            significant_change_threshold=Decimal(str(policy.significant_change_threshold)),
            paid_vacation_counts_for_daily=policy.paid_vacation_counts_for_daily,
            overtime_enabled=policy.overtime_enabled,
            late_makeup_enabled=policy.late_makeup_enabled,
            late_deduction_enabled=policy.late_deduction_enabled,
            monthly_payroll_calculation_mode="calendar_days",
            auto_recalculate_draft_payroll=policy.auto_recalculate_draft_payroll,
            lock_payroll_after_payment=policy.lock_payroll_after_payment,
            annual_vacation_days_by_year=policy.annual_vacation_days_by_year or {},
            allow_vacation_carryover=policy.allow_vacation_carryover,
            max_vacation_carryover_days=policy.max_vacation_carryover_days,
            carryover_expiry_month=policy.carryover_expiry_month,
            carryover_expiry_day=policy.carryover_expiry_day,
            reserve_vacation_days_on_pending=policy.reserve_vacation_days_on_pending,
        )

        with patch(
            "app.services.payroll_calculation_service.reconcile_existing_payrolls_for_settings_change"
        ) as reconcile_mock:
            response = put_payroll_policy(
                payload=payload,
                db=self.db,
                current_user=SimpleNamespace(id=99),
            )

        response_payload = json.loads(response.body)
        self.assertTrue(response_payload["status"])
        reconcile_mock.assert_called_once_with(
            self.db,
            reason="payroll_policy_updated",
            created_by=99,
        )
        self.assertEqual(self._policy().monthly_payroll_calculation_mode, "calendar_days")

    def test_current_period_discrepancy_detection_ignores_future_missing_attendance(self):
        period = self._payroll_period_for_month(2026, 5)
        future_missing_date = date(2026, 5, 25)
        for day in self._month_days():
            if day.work_date != future_missing_date:
                self.db.add(day)
        self.db.commit()

        with patch("app.services.payroll_calculation_service._today", return_value=date(2026, 5, 19)):
            payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
            self.db.commit()

        open_discrepancies = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        self.assertFalse(
            any(
                item.discrepancy_type == "missing_attendance"
                and future_missing_date.isoformat() in item.description
                for item in open_discrepancies
            )
        )

    def test_past_period_discrepancy_detection_includes_missing_past_workday(self):
        period = self._payroll_period_for_month(2026, 5)
        missing_date = date(2026, 5, 25)
        for day in self._month_days():
            if day.work_date != missing_date:
                self.db.add(day)
        self.db.commit()

        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
        self.db.commit()

        open_discrepancies = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        self.assertTrue(
            any(
                item.discrepancy_type == "missing_attendance"
                and missing_date.isoformat() in item.description
                for item in open_discrepancies
            )
        )

    def test_period_reconciliation_auto_resolves_future_missing_attendance(self):
        period = self._payroll_period_for_month(2026, 5)
        future_missing_date = date(2026, 5, 25)
        for day in self._month_days():
            if day.work_date != future_missing_date:
                self.db.add(day)
        self.db.commit()

        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
        self.db.commit()

        open_before = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        self.assertTrue(any(future_missing_date.isoformat() in item.description for item in open_before))

        with patch("app.services.payroll_calculation_service._today", return_value=date(2026, 5, 19)):
            discrepancies = get_payroll_discrepancies(period.id, self.db)

        refreshed = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.discrepancy_type == "missing_attendance",
            )
        ).all()
        self.assertFalse(
            any(item.status == "open" and future_missing_date.isoformat() in item.description for item in refreshed)
        )
        self.assertTrue(
            any(item.status == "resolved" and future_missing_date.isoformat() in item.description for item in discrepancies)
        )

    def test_approval_succeeds_with_only_medium_discrepancies(self):
        period = self._payroll_period_for_month(2026, 5)
        for day in self._month_days():
            self.db.add(day)
        self.db.commit()

        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
        self.db.add(
            PayrollDiscrepancy(
                employee_payroll_id=payroll.id,
                payroll_period_id=period.id,
                employee_id=self.employee.id,
                discrepancy_type="overtime_conflict",
                description="Manual medium discrepancy",
                severity="medium",
                status="open",
            )
        )
        self.db.commit()

        approved = approve_employee_payroll(payroll.id, self.db, approved_by=1)
        self.assertEqual(approved.status, "approved")

    def test_approval_fails_with_high_discrepancies(self):
        period = self._payroll_period_for_month(2026, 5)
        for day in self._month_days():
            self.db.add(day)
        self.db.commit()

        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
        self.db.add(
            PayrollDiscrepancy(
                employee_payroll_id=payroll.id,
                payroll_period_id=period.id,
                employee_id=self.employee.id,
                discrepancy_type="overtime_conflict",
                description="Manual high discrepancy",
                severity="high",
                status="open",
            )
        )
        self.db.commit()

        with self.assertRaises(BadRequestException):
            approve_employee_payroll(payroll.id, self.db, approved_by=1)

    def test_payment_succeeds_with_only_medium_discrepancies_when_approved(self):
        period = self._payroll_period_for_month(2026, 5)
        for day in self._month_days():
            self.db.add(day)
        self.db.commit()

        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
        self.db.add(
            PayrollDiscrepancy(
                employee_payroll_id=payroll.id,
                payroll_period_id=period.id,
                employee_id=self.employee.id,
                discrepancy_type="overtime_conflict",
                description="Manual medium discrepancy",
                severity="medium",
                status="open",
            )
        )
        self.db.commit()

        approved = approve_employee_payroll(payroll.id, self.db, approved_by=1)
        paid = mark_employee_payroll_paid(approved.id, self.db, paid_by=1)
        self.assertEqual(paid.status, "locked")
        self.assertEqual(Decimal(str(paid.balance_amount)), Decimal("0.00"))

    def test_payment_fails_with_high_discrepancies(self):
        period = self._payroll_period_for_month(2026, 5)
        for day in self._month_days():
            self.db.add(day)
        self.db.commit()

        payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
        approved = approve_employee_payroll(payroll.id, self.db, approved_by=1)
        self.db.add(
            PayrollDiscrepancy(
                employee_payroll_id=approved.id,
                payroll_period_id=period.id,
                employee_id=self.employee.id,
                discrepancy_type="overtime_conflict",
                description="Manual high discrepancy",
                severity="high",
                status="open",
            )
        )
        self.db.commit()

        with self.assertRaises(BadRequestException):
            mark_employee_payroll_paid(approved.id, self.db, paid_by=1)

    def test_current_period_discrepancy_record_does_not_send_immediate_notification(self):
        period = self._payroll_period_for_month(2026, 5)
        missing_date = date(2026, 5, 18)
        for day in self._month_days():
            if day.work_date != missing_date:
                self.db.add(day)
        self.db.commit()

        with patch("app.services.payroll_calculation_service._today", return_value=date(2026, 5, 19)):
            payroll = calculate_employee_payroll(self.employee.id, period.id, self.db, force_history=True)
            self.db.commit()

        discrepancies = self.db.scalars(
            select(PayrollDiscrepancy).where(
                PayrollDiscrepancy.employee_payroll_id == payroll.id,
                PayrollDiscrepancy.status == "open",
            )
        ).all()
        notifications = self.db.scalars(
            select(Notification).where(Notification.notification_type == "payroll_discrepancy_detected")
        ).all()

        self.assertTrue(
            any(
                item.discrepancy_type == "missing_attendance"
                and missing_date.isoformat() in item.description
                for item in discrepancies
            )
        )
        self.assertEqual(notifications, [])


if __name__ == "__main__":
    unittest.main()
