from fastapi import APIRouter
from app.services.payment_service import get_emp_att_payment
from datetime import date
from app.schemas.attendenceBaseModel import DataRange
from app.services.payment_service import add_payments,update_payment
from app.schemas.paymentsBaseModel import PaymentBaseModel,UpdatePaymentBaseModel

router = APIRouter()

@router.get("/{emp_id}/{start}/{end}")
def get_employee_payments(emp_id:int,dates:DataRange):
    res = get_emp_att_payment(emp_id,dates.start,dates.end)
    return {"message":"","data":res,"status":True}


@router.put("/")
def add_new_payment(new_payment:PaymentBaseModel):
    add_payments(new_payment)
    return {"message":"","data":None,"status":True}

@router.post("/")
def update_payment(payment:UpdatePaymentBaseModel):
    update_payment(payment)
    return {"message":"","data":None,"status":True}

@router.delete("/{id}")
def delete_payment(id:int):
    delete_payment(id)
    return {"message":"","data":None,"status":True}
