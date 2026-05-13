from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_hr_or_admin
from app.models.auth import User
from app.services.stat_service import dashbord_card_stat


router = APIRouter()
@router.get("/dashbord/cards")
def dashbord_cards(
    db:Session=Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    res = dashbord_card_stat(db)
    return api_success({"total_emps":res[0],"total_active_emps":res[1],"total_att_percent":res[2],"total_vacation":res[3]})
