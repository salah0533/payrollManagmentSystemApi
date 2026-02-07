from fastapi import APIRouter,Depends
from app.services.att_types_service import get_att_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_att_types(db:Session=Depends(get_db)):
    data = get_att_types_srv(db)
    return {"message":"","data":data,"status":True}