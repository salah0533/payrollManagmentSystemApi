from fastapi import APIRouter,Depends
from app.services.salary_types_services import get_payment_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_salary_types(db:Session=Depends(get_db)):
    data = get_payment_types_srv(db)
    return {"message":"","data":data,"status":True}