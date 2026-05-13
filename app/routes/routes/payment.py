from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_hr_or_admin, require_self_or_permission
from app.models.auth import User
from app.schemas.paymentsBaseModel import PaymentBaseModel, UpdatePaymentBaseModel
from app.services.payment_service import (
    add_payments,
    delete_payment,
    get_all_payements,
    get_emp_att_payment,
    get_employee_payments as get_employee_payments_srv,
    get_last_att_date as get_last_att_date_srv,
    update_payment,
)
from app.utility.helper import get_month_range
from app.utility.validators import validate_year_month


router = APIRouter()


@router.get("/att/{emp_id}/{month}")
def get_employee_att_payments(
    emp_id: int,
    month: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    validate_year_month(month)
    start, end = get_month_range(month)
    res = get_emp_att_payment(emp_id, start, end, db)
    return api_success(res)


@router.get("/get_all_payment/{start}/{end}")
def get_all(
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    res = get_all_payements(start, end, db)
    return api_success(res)


@router.get("/last_att_date")
def get_last_att_date(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    res = get_last_att_date_srv(emp_id, db)
    return api_success(res)


@router.get("/{emp_id}/{start}/{end}")
def get_employee_payments(
    emp_id: int,
    start: date,
    end: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_permission("payroll.read_all", employee_param="emp_id")),
):
    res = get_employee_payments_srv(emp_id, start, end, db)
    return api_success(res)


@router.put("/")
def add_new_payment(
    new_payment: PaymentBaseModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    start, end = None, None
    if new_payment.year_month:
        start, end = get_month_range(new_payment.year_month)
    add_payments(new_payment, start, end, db)
    return api_success(status_code=201)


@router.post("/")
def update_payment_by_id(
    payment: UpdatePaymentBaseModel,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    update_payment(payment, db)
    return api_success()


@router.delete("/{id}")
def delete_payment_by_id(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    delete_payment(id, db)
    return api_success()
