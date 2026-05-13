from sqlalchemy.orm import Session
from sqlalchemy import select,desc
from app.models.payments import Payments
from app.models.employees import Employees
from app.exceptions.base_exception import ResourceNotFoundException
from app.services.stat_service import att_stat
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from app.schemas.paymentsBaseModel import PaymentBaseModel,UpdatePaymentBaseModel
from app.exceptions.db_exceptions.paymentNotFound import PaymentNotFound
from datetime import timedelta
from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta


def get_emp_att_payment(emp_id,start:date,end:date,db:Session):
    emp = db.get(Employees,emp_id)
    if not emp:
        raise EmployeeNotFound("employee not found")
    
    res = att_stat(emp_id,start,end,db)
    return res
    
def get_all_payements(start:date,end:date,db:Session):
    return db.scalars(
        select(Payments)
        .where( Payments.date>=start,
                Payments.date<=end)
        .order_by(Payments.date)
        ).all()

def get_employee_payments(emp_id,start:date,end:date,db:Session):
    return db.scalars(
        select(Payments)
        .where(
            Payments.employee_id==emp_id,
            Payments.date >= start,
            Payments.date <= end + timedelta(days=1)
        )
    ).all()

def get_last_att_date(emp_id:int,db:Session):
    return db.scalar(
        select(Payments.end)
        .where( Payments.payment_type==3)
        .order_by(desc(Payments.end))
        .limit(1)
    )
def add_payments(pay:PaymentBaseModel,start,end,db:Session):
        
        new_payments = Payments(
            employee_id=pay.employee_id,
            date=pay.date,
            amount=pay.amount,
            payment_type=pay.payment_type,
            start=start,
            end=end,
            description=pay.description
        )

        emp = db.get(Employees, pay.employee_id)
        if not emp:
            raise EmployeeNotFound()

        INCOME_TYPES = [1, 3]

        emp.dues = (emp.dues or Decimal("0")) + Decimal(str(pay.amount)) if pay.payment_type in INCOME_TYPES else (emp.dues or Decimal("0")) - Decimal(str(pay.amount))

        db.add(new_payments)
        db.add(emp)

        db.commit()
        db.refresh(new_payments)

def update_payment(pay:UpdatePaymentBaseModel,db:Session):
    exist_pay = db.get(Payments, pay.id)
    if not exist_pay:
        raise PaymentNotFound("payment not found")

    emp = db.get(Employees, exist_pay.employee_id)
    if not emp:
        raise ResourceNotFoundException("Employee")

    INCOME_TYPES = [1, 3]  # bonus, attendence

    if exist_pay.payment_type in INCOME_TYPES:
        emp.dues = (emp.dues or Decimal("0")) - exist_pay.amount
    else:
        emp.dues = (emp.dues or Decimal("0")) + exist_pay.amount

    update_data = pay.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        if val is None:
            continue
        setattr(exist_pay, key, val)

    if exist_pay.payment_type in INCOME_TYPES:
        emp.dues = (emp.dues or Decimal("0")) + exist_pay.amount
    else:
        emp.dues = (emp.dues or Decimal("0")) - exist_pay.amount

    db.add(exist_pay)
    db.add(emp)

    db.commit()

def delete_payment(pay_id: int, db: Session):
    pay = db.get(Payments, pay_id)
    if not pay:
        raise PaymentNotFound("payment not found")

    emp = db.get(Employees, pay.employee_id)
    if not emp:
        raise ResourceNotFoundException("Employee")

    INCOME_TYPES = [1, 3]  # bonus, attendence

    if pay.payment_type in INCOME_TYPES:
        emp.dues = (emp.dues or Decimal("0")) - Decimal(str(pay.amount))
    else:
        emp.dues = (emp.dues or Decimal("0")) + Decimal(str(pay.amount))

    db.delete(pay)
    db.add(emp)

    db.commit()
