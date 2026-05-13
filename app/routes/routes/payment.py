from fastapi import APIRouter, Depends, HTTPException
from app.services.payment_service import get_all_payements,get_emp_att_payment, add_payments, update_payment, delete_payment ,get_employee_payments as get_employee_payments_srv,get_last_att_date as get_last_att_date_srv
from datetime import date,datetime
from app.schemas.paymentsBaseModel import PaymentBaseModel,UpdatePaymentBaseModel,MonthInput
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.utility.helper import get_month_range

router = APIRouter()

@router.get("/att/{emp_id}/{month}")
def get_employee_att_payments(emp_id:int,month:str,db: Session = Depends(get_db)):
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid format. Use YYYY-MM")
    start,end = get_month_range(month)
    res = get_emp_att_payment(emp_id,start,end,db)
    return {"message":"","data":res,"status":True}

@router.get("/get_all_payment/{start}/{end}")
def get_all(start:date,end:date,db:Session=Depends(get_db)):
    res = get_all_payements(start,end,db) 
    return {"message":"","data":res,"status":True}

@router.get("/last_att_date")
def get_last_att_date(emp_id:int,db: Session = Depends(get_db)):
    res = get_last_att_date_srv(emp_id,db)
    return {"message":"","data":res,"status":True}

@router.get("/{emp_id}/{start}/{end}")
def get_employee_payments(emp_id:int,start:date,end:date,db: Session = Depends(get_db)):
    res = get_employee_payments_srv(emp_id,start,end,db)
    return {"message":"","data":res,"status":True}

@router.put("/")
def add_new_payment(new_payment:PaymentBaseModel,db: Session = Depends(get_db)):
    start,end=None,None
    if new_payment.year_month:
        try:
            datetime.strptime(new_payment.year_month, "%Y-%m")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid format. Use YYYY-MM")
        start,end = get_month_range(new_payment.year_month)
    add_payments(new_payment,start,end,db)
    return {"message":"","data":None,"status":True}

@router.post("/")
def update_payment_by_id(payment:UpdatePaymentBaseModel,db: Session = Depends(get_db)):
    update_payment(payment,db)
    return {"message":"","data":None,"status":True}

@router.delete("/{id}")
def delete_payment_by_id(id:int,db: Session = Depends(get_db)):
    delete_payment(id,db)
    return {"message":"","data":None,"status":True}
