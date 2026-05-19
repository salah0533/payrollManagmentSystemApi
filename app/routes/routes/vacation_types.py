from fastapi import APIRouter,Depends
from app.core.responses import api_success
from app.dependencies.auth import require_authenticated_user
from app.models.auth import User
from app.services.vacation_types_services import get_payment_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_vacation_types(
    db:Session=Depends(get_db),
    current_user: User = Depends(require_authenticated_user),
):
    data = get_payment_types_srv(db)
    db.commit()
    return api_success(data)

    # {
    #   "id": 0,
    #   "vacation_type": "yearly_vacation"
    # },
    # {
    #   "id": 1,
    #   "vacation_type": "sick_leave"
    # },
    # {
    #   "id": 2,
    #   "vacation_type": "vacation"
    # }
