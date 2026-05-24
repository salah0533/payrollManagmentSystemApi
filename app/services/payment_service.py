from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions.base_exception import ResourceNotFoundException
from app.models.attendance_payroll import EmployeeLedgerTransaction
from app.models.employees import Employees
from app.services.payroll_calculation_service import get_employee_ledger, recalculate_employee_financial_total


def _day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _day_end(value: date) -> datetime:
    return datetime.combine(value, time.max, tzinfo=timezone.utc)


def get_emp_att_payment(emp_id, start: date, end: date, db: Session):
    return get_employee_ledger(emp_id, db)


def get_all_payements(start: date, end: date, db: Session):
    return db.scalars(
        select(EmployeeLedgerTransaction)
        .where(EmployeeLedgerTransaction.transaction_date >= _day_start(start), EmployeeLedgerTransaction.transaction_date <= _day_end(end))
        .order_by(EmployeeLedgerTransaction.transaction_date.asc(), EmployeeLedgerTransaction.id.asc())
    ).all()


def get_employee_payments(emp_id, start: date, end: date, db: Session):
    return db.scalars(
        select(EmployeeLedgerTransaction)
        .where(
            EmployeeLedgerTransaction.employee_id == emp_id,
            EmployeeLedgerTransaction.transaction_date >= _day_start(start),
            EmployeeLedgerTransaction.transaction_date <= _day_end(end),
        )
        .order_by(EmployeeLedgerTransaction.transaction_date.asc(), EmployeeLedgerTransaction.id.asc())
    ).all()


def get_last_att_date(emp_id: int, db: Session):
    employee = db.get(Employees, emp_id)
    if not employee:
        raise ResourceNotFoundException("Employee")
    latest = db.scalar(
        select(EmployeeLedgerTransaction.transaction_date)
        .where(EmployeeLedgerTransaction.employee_id == emp_id)
        .order_by(EmployeeLedgerTransaction.transaction_date.desc(), EmployeeLedgerTransaction.id.desc())
        .limit(1)
    )
    return latest.date() if latest else None


def add_payments(pay, start, end, db: Session):
    row = EmployeeLedgerTransaction(
        employee_id=pay.employee_id,
        type=pay.payment_type,
        transaction_date=datetime.combine(pay.date, time(12), tzinfo=timezone.utc),
        amount=pay.amount,
        description=pay.description,
    )
    db.add(row)
    db.flush()
    recalculate_employee_financial_total(pay.employee_id, db)
    db.commit()
    return row


def update_payment(pay, db: Session):
    row = db.get(EmployeeLedgerTransaction, pay.id)
    if not row:
        raise ResourceNotFoundException("Ledger transaction")
    data = pay.model_dump(exclude_unset=True)
    if data.get("date") is not None:
        row.transaction_date = datetime.combine(data["date"], time(12), tzinfo=timezone.utc)
    if data.get("payment_type") is not None:
        row.type = data["payment_type"]
    if data.get("amount") is not None:
        row.amount = data["amount"]
    if data.get("description") is not None:
        row.description = data["description"]
    row.status = "changed"
    db.add(row)
    db.flush()
    recalculate_employee_financial_total(row.employee_id, db)
    db.commit()
    return row


def delete_payment(pay_id: int, db: Session):
    row = db.get(EmployeeLedgerTransaction, pay_id)
    if not row:
        raise ResourceNotFoundException("Ledger transaction")
    employee_id = row.employee_id
    db.delete(row)
    db.flush()
    recalculate_employee_financial_total(employee_id, db)
    db.commit()
