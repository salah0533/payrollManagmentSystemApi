from fastapi import APIRouter,Depends
from app.services.vacation_statuses_services import get_payment_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_vacation_statuses(db:Session=Depends(get_db)):
    data = get_payment_types_srv(db)
    return {"message":"","data":data,"status":True}