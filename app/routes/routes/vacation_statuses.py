from fastapi import APIRouter,Depends
from app.services.vacation_statuses_services import get_payment_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_vacation_statuses(db:Session=Depends(get_db)):
    data = get_payment_types_srv(db)
    return {"message":"","data":data,"status":True}

#    {
#       "id": 0,
#       "vacation_status": "pending"
#     },
#     {
#       "id": 1,
#       "vacation_status": "proved"
#     },
#     {
#       "id": 2,
#       "vacation_status": "rejected"
#     },
#     {
#       "id": 3,
#       "vacation_status": "canceled"
#     }