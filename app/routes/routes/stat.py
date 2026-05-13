from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.stat_service import dashbord_card_stat


router = APIRouter()
@router.get("/dashbord/cards")
def dashbord_cards(db:Session=Depends(get_db)):
    res = dashbord_card_stat(db)
    return {"message":"","data":{"total_emps":res[0],"total_active_emps":res[1],"total_att_percent":res[2],"total_vacation":res[3]},"status":True}