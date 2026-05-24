from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.attendance_payroll import (
    AttendanceDay,
    EmployeeCompensation,
    EmployeeLedgerTransaction,
    PayrollPeriod,
)
from app.models.employees import Employees
from app.models.salary_type import SalaryType
from app.services.payroll_calculation_service import calculate_employee_payroll, lock_payroll_period


DEMO_MARKER = "[demo-old-periods]"
DEMO_EMAILS = ("demo.ledger.one@example.test", "demo.ledger.two@example.test")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _month_start(months_back: int) -> date:
    today = date.today()
    year = today.year
    month = today.month - months_back
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def _month_end(start: date) -> date:
    return date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])


def _period_generated_at(start: date) -> datetime:
    return datetime.combine(start, time(23, 59, 59), tzinfo=timezone.utc)


def _ensure_salary_type(db) -> None:
    if not db.scalar(select(SalaryType).where(SalaryType.id == 0)):
        db.add(SalaryType(id=0, code="monthly", salary_type="monthly"))
        db.flush()


def _ensure_demo_employees(db) -> list[Employees]:
    _ensure_salary_type(db)
    employees: list[Employees] = []
    rows = [
        ("Demo", "Ledger One", DEMO_EMAILS[0], Decimal("30000.00")),
        ("Demo", "Ledger Two", DEMO_EMAILS[1], Decimal("42000.00")),
    ]
    for first_name, last_name, email, salary in rows:
        employee = db.scalar(select(Employees).where(Employees.email == email))
        if not employee:
            employee = Employees(
                first_name=first_name,
                last_name=last_name,
                fullname=f"{first_name} {last_name}",
                job_title="Demo Payroll Employee",
                phone="0500000000",
                email=email,
                position="Demo Payroll Employee",
                status="active",
                hire_date=_month_start(6),
                salary_type=0,
                monthly_price=salary,
                day_price=Decimal("0.00"),
                hour_price=Decimal("0.00"),
                extra_hours_price=Decimal("600.00"),
                daily_work_hours=8,
                vacation_days=30,
                auto_attendance_enabled=False,
                is_active=True,
                allowed_late=Decimal("0.00"),
                min_extraTime=Decimal("30.00"),
                joined=_month_start(6),
            )
            db.add(employee)
            db.flush()
        employee.deleted_at = None
        employee.status = "active"
        employee.is_active = True
        db.add(employee)
        db.flush()
        if not db.scalar(select(EmployeeCompensation).where(EmployeeCompensation.employee_id == employee.id)):
            db.add(
                EmployeeCompensation(
                    employee_id=employee.id,
                    salary_type="monthly",
                    base_monthly_salary=employee.monthly_price,
                    daily_rate=Decimal("0.00"),
                    hourly_rate=Decimal("0.00"),
                    overtime_rate=employee.extra_hours_price,
                    late_deduction_rate=Decimal("0.00"),
                    currency="DZD",
                    effective_from=employee.hire_date or employee.joined or _month_start(6),
                    is_active=True,
                )
            )
            db.flush()
        employees.append(employee)
    return employees


def _ensure_period(db, start: date) -> PayrollPeriod:
    end = _month_end(start)
    period = db.scalar(select(PayrollPeriod).where(PayrollPeriod.start_date == start, PayrollPeriod.end_date == end))
    if not period:
        period = PayrollPeriod(
            name=f"{DEMO_MARKER} {start:%B %Y}",
            start_date=start,
            end_date=end,
            status="open",
            generated_at=_period_generated_at(start),
        )
        db.add(period)
        db.flush()
    elif period.name.startswith(DEMO_MARKER) and period.status == "locked":
        period.status = "open"
        period.locked_at = None
        period.locked_by = None
        db.add(period)
        db.flush()
    return period


def _work_dates(start: date, count: int = 14) -> list[date]:
    dates: list[date] = []
    current = start
    end = _month_end(start)
    while current <= end and len(dates) < count:
        if current.weekday() not in {4, 5}:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def _upsert_attendance(db, employee: Employees, period: PayrollPeriod, employee_index: int) -> None:
    for index, work_date in enumerate(_work_dates(period.start_date, 16)):
        existing = db.scalar(
            select(AttendanceDay).where(
                AttendanceDay.employee_id == employee.id,
                AttendanceDay.work_date == work_date,
            )
        )
        status = "absent" if index in {3 + employee_index, 11} else "late" if index in {5, 12} else "present"
        actual_minutes = 0 if status == "absent" else 450 if status == "late" else 480
        late_minutes = 30 if status == "late" else 0
        unpaid_minutes = 480 if status == "absent" else 30 if status == "late" else 0
        values = {
            "work_schedule_id": None,
            "check_in_time": None if status == "absent" else time(8, 30) if status == "late" else time(8, 0),
            "break_start_time": None if status == "absent" else time(12, 0),
            "break_end_time": None if status == "absent" else time(13, 0),
            "check_out_time": None if status == "absent" else time(17, 0),
            "expected_work_minutes": 480,
            "actual_work_minutes": actual_minutes,
            "break_minutes": 60 if status != "absent" else 0,
            "normal_paid_minutes": max(0, actual_minutes - late_minutes),
            "late_minutes": late_minutes,
            "early_leave_minutes": 0,
            "late_makeup_minutes": 0,
            "overtime_minutes": 0,
            "absence_minutes": 480 if status == "absent" else 0,
            "unpaid_minutes": unpaid_minutes,
            "status": status,
            "review_status": "approved",
            "reviewed_at": _utc_now(),
            "reviewed_by": None,
            "locked_at": None,
            "is_manually_corrected": False,
            "calculated_at": _utc_now(),
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
            db.add(existing)
        else:
            db.add(AttendanceDay(employee_id=employee.id, work_date=work_date, **values))
    db.flush()


def _add_transactions(db, employee: Employees, period: PayrollPeriod, month_index: int) -> None:
    samples = [
        ("bonus", Decimal("2500.00"), 6, "yearly bonus"),
        ("deduction", Decimal("900.00"), 12, "equipment deduction"),
        ("payment", Decimal("-5000.00"), 20, "cash payment"),
    ]
    for transaction_type, amount, day, label in samples:
        tx_date = datetime.combine(
            min(period.end_date, date(period.start_date.year, period.start_date.month, day)),
            time(12, 0),
            tzinfo=timezone.utc,
        )
        description = f"{DEMO_MARKER} {label} for {period.start_date:%B %Y}"
        exists = db.scalar(
            select(EmployeeLedgerTransaction).where(
                EmployeeLedgerTransaction.employee_id == employee.id,
                EmployeeLedgerTransaction.type == transaction_type,
                EmployeeLedgerTransaction.transaction_date == tx_date,
                EmployeeLedgerTransaction.description == description,
            )
        )
        if not exists:
            db.add(
                EmployeeLedgerTransaction(
                    employee_id=employee.id,
                    type=transaction_type,
                    transaction_date=tx_date,
                    amount=amount + Decimal(month_index * 100),
                    description=description,
                )
            )
    db.flush()


def main() -> None:
    db = SessionLocal()
    try:
        employees = _ensure_demo_employees(db)
        created_payrolls = 0
        created_transactions = 0
        for month_index, months_back in enumerate((3, 2, 1), start=1):
            period = _ensure_period(db, _month_start(months_back))
            for employee_index, employee in enumerate(employees):
                _upsert_attendance(db, employee, period, employee_index)
                payroll = calculate_employee_payroll(
                    employee.id,
                    period.id,
                    db,
                    reason=f"{DEMO_MARKER} seed old period",
                    force_history=True,
                )
                payroll.notes = DEMO_MARKER
                db.add(payroll)
                _add_transactions(db, employee, period, month_index)
                created_payrolls += 1
                created_transactions += 3
            if month_index == 1 and period.status != "locked":
                lock_payroll_period(period.id, db)
        db.commit()
        print(f"demo old-period data added for {len(employees)} employees")
        print(f"payroll rows touched: {created_payrolls}")
        print(f"ledger transactions ensured: {created_transactions}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
