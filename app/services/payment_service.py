from datetime import date

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions.base_exception import BadRequestException
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from app.models.employees import Employees
from app.models.payments import Payments
from app.services.payroll_calculation_service import get_employee_payroll_by_period, get_or_create_payroll_period_for_date


def _legacy_payment_write_disabled() -> None:
    raise BadRequestException(
        "Legacy payment writes are disabled. Use /payroll/mark-paid for payments and /payroll/adjustment for bonuses, deductions, or due settlements."
    )


def get_emp_att_payment(emp_id, start: date, end: date, db: Session):
    employee = db.get(Employees, emp_id)
    if not employee:
        raise EmployeeNotFound("employee not found")
    period = get_or_create_payroll_period_for_date(end, db)
    payroll = get_employee_payroll_by_period(emp_id, period.id, db)
    return {
        "employee_id": emp_id,
        "period_id": period.id,
        "period_start": period.start_date,
        "period_end": period.end_date,
        "salary_type": payroll.salary_type,
        "base_salary": payroll.base_salary,
        "normal_amount": payroll.normal_amount,
        "overtime_amount": payroll.overtime_amount,
        "bonus_amount": payroll.bonus_amount,
        "deduction_amount": payroll.deduction_amount,
        "late_deduction_amount": payroll.late_deduction_amount,
        "unpaid_vacation_deduction": payroll.unpaid_vacation_deduction,
        "adjustment_amount": payroll.adjustment_amount,
        "net_salary": payroll.net_salary,
        "paid_amount": payroll.paid_amount,
        "balance_amount": payroll.balance_amount,
        "status": payroll.status,
        "source": "employee_payroll",
    }


def get_all_payements(start: date, end: date, db: Session):
    return db.scalars(
        select(Payments)
        .options(selectinload(Payments.employee_payroll_tab))
        .where(Payments.date >= start, Payments.date <= end)
        .order_by(Payments.date, Payments.id)
    ).all()


def get_employee_payments(emp_id, start: date, end: date, db: Session):
    return db.scalars(
        select(Payments)
        .options(selectinload(Payments.employee_payroll_tab))
        .where(
            Payments.employee_id == emp_id,
            Payments.date >= start,
            Payments.date <= end,
        )
        .order_by(Payments.date, Payments.id)
    ).all()


def get_last_att_date(emp_id: int, db: Session):
    employee = db.get(Employees, emp_id)
    if not employee:
        raise EmployeeNotFound("employee not found")
    latest_payment = db.scalar(
        select(Payments.end)
        .where(Payments.employee_id == emp_id, Payments.employee_payroll_id.is_not(None))
        .order_by(desc(Payments.end), desc(Payments.id))
        .limit(1)
    )
    return latest_payment


def add_payments(pay, start, end, db: Session):
    _legacy_payment_write_disabled()


def update_payment(pay, db: Session):
    _legacy_payment_write_disabled()


def delete_payment(pay_id: int, db: Session):
    _legacy_payment_write_disabled()
