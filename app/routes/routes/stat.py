from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_hr_or_admin
from app.models.auth import User
from app.services.stat_service import dashboard_attendance_stats


router = APIRouter()
@router.get("/dashbord/cards")
def dashbord_cards(
    db:Session=Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    return api_success(dashboard_attendance_stats(db))
