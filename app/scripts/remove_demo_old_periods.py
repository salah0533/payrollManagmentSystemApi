from __future__ import annotations

from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models.attendance_payroll import (
    AttendanceDay,
    EmployeeCompensation,
    EmployeeFinancialTotal,
    EmployeeLedgerTransaction,
    EmployeePayroll,
    PayrollCalculationHistory,
    PayrollPeriod,
)
from app.models.employees import Employees
from app.services.payroll_calculation_service import recalculate_employee_financial_total


DEMO_MARKER = "[demo-old-periods]"
DEMO_EMAILS = ("demo.ledger.one@example.test", "demo.ledger.two@example.test")


def main() -> None:
    db = SessionLocal()
    try:
        demo_employees = db.scalars(select(Employees).where(Employees.email.in_(DEMO_EMAILS))).all()
        demo_employee_ids = [employee.id for employee in demo_employees]
        demo_periods = db.scalars(select(PayrollPeriod).where(PayrollPeriod.name.like(f"{DEMO_MARKER}%"))).all()
        demo_period_ids = [period.id for period in demo_periods]

        if demo_employee_ids:
            db.execute(delete(EmployeeLedgerTransaction).where(EmployeeLedgerTransaction.employee_id.in_(demo_employee_ids)))
            db.execute(delete(EmployeeFinancialTotal).where(EmployeeFinancialTotal.employee_id.in_(demo_employee_ids)))

        demo_payroll_ids = []
        if demo_employee_ids:
            demo_payroll_ids = db.scalars(
                select(EmployeePayroll.id).where(
                    EmployeePayroll.employee_id.in_(demo_employee_ids)
                )
            ).all()
        if demo_payroll_ids:
            db.execute(delete(PayrollCalculationHistory).where(PayrollCalculationHistory.employee_payroll_id.in_(demo_payroll_ids)))
            db.execute(delete(EmployeePayroll).where(EmployeePayroll.id.in_(demo_payroll_ids)))

        if demo_employee_ids:
            db.execute(delete(AttendanceDay).where(AttendanceDay.employee_id.in_(demo_employee_ids)))
            db.execute(delete(EmployeeCompensation).where(EmployeeCompensation.employee_id.in_(demo_employee_ids)))

        if demo_period_ids:
            db.execute(delete(PayrollPeriod).where(PayrollPeriod.id.in_(demo_period_ids)))

        for employee in demo_employees:
            db.delete(employee)

        db.flush()
        for employee_id in demo_employee_ids:
            if db.get(Employees, employee_id):
                recalculate_employee_financial_total(employee_id, db)
        db.commit()
        print(f"removed demo old-period employees: {len(demo_employee_ids)}")
        print(f"removed demo old-period periods: {len(demo_period_ids)}")
        print(f"removed demo payroll rows: {len(demo_payroll_ids)}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
