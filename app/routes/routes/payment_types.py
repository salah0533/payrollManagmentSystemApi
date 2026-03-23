from fastapi import APIRouter,Depends
from app.services.payment_types_service import get_payment_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_payment_types(db:Session=Depends(get_db)):
    data = get_payment_types_srv(db)
    return {"message":"","data":data,"status":True}

    # {
    #   "payment_type": "payment",
    #   "id": 0
    # },
    # {
    #   "payment_type": "bonus",
    #   "id": 1
    # },
    # {
    #   "payment_type": "deduction",
    #   "id": 2
    # },
    # {
    #   "payment_type": "attendence",
    #   "id": 3
    # }