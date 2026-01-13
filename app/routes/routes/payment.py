from fastapi import APIRouter

router = APIRouter()

@router.get("/{emp_id}")
def get_employee_payments(emp_id:int):
    