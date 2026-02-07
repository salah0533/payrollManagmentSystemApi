from fastapi import APIRouter, Depends
from app.services.payment_service import get_emp_att_payment, add_payments, update_payment, delete_payment
from datetime import date
from app.schemas.paymentsBaseModel import PaymentBaseModel,UpdatePaymentBaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/{emp_id}/{start}/{end}")
def get_employee_payments(emp_id:int,start:date,end:date,db: Session = Depends(get_db)):
    res = get_emp_att_payment(emp_id,start,end,db)
    return {"message":"","data":res,"status":True}


@router.put("/")
def add_new_payment(new_payment:PaymentBaseModel,db: Session = Depends(get_db)):
    add_payments(new_payment,db)
    return {"message":"","data":None,"status":True}

@router.post("/")
def update_payment_by_id(payment:UpdatePaymentBaseModel,db: Session = Depends(get_db)):
    update_payment(payment,db)
    return {"message":"","data":None,"status":True}

@router.delete("/{id}")
def delete_payment_by_id(id:int,db: Session = Depends(get_db)):
    delete_payment(id,db)
    return {"message":"","data":None,"status":True}
