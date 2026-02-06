from sqlalchemy.orm import Session
from app.db.session import get_db
from fastapi import Depends
from sqlalchemy import select
from app.models.payments import Payments
from app.models.employees import Employees
from app.services.stat_service import att_stat
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from app.schemas.paymentsBaseModel import PaymentBaseModel,UpdatePaymentBaseModel
from app.exceptions.db_exceptions.paymentNotFound import PaymentNotFound
from datetime import date
from dateutil.relativedelta import relativedelta

def get_emp_att_payment(emp_id,start:date,end:date,db:Session=Depends(get_db)):
    emp = db.get(Employees,emp_id)
    if not emp:
        raise EmployeeNotFound("employee not found")
    
    res = att_stat(emp_id,start,end)
    return res
    

def get_employee_payments(emp_id:int,db:Session=Depends(get_db)):
    try:
        return db.scalars(
            select(Payments)
            .where(
                Payments.employee_id==emp_id
            )
        ).all()
    except Exception as e:
        raise e
    
def add_payments(pay:PaymentBaseModel,db:Session=Depends(get_db)):
    try:
        new_payments = Payments(employee_id=pay.employee_id,date=pay.date,amount=pay.amount,payment_type=pay.payment_type,description=pay.description)
        db.add(new_payments)
        db.commit()
        db.refresh(new_payments)
    except Exception as e:
        raise e

def update_payment(pay:UpdatePaymentBaseModel,db:Session=Depends(get_db)):
    try:
        exist_pay = db.get(Payments,pay.id)
        for key,val in pay:
            if not val:
                continue
            setattr(exist_pay,key,val)
        db.commit()
    except Exception as e:
        raise e

def delete_payment(pay_id:int,db:Session=Depends(get_db)):
    try:
        pay = db.get(Payments,pay_id)
        if not pay:
            raise PaymentNotFound("payment not found")
        
        db.delete(Payments,pay_id)
        db.commit()
    except Exception as e:
        raise e