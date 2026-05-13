from fastapi import APIRouter,Depends
from app.core.responses import api_success
from app.dependencies.auth import require_authenticated_user
from app.models.auth import User
from app.services.payment_types_service import get_payment_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_payment_types(
    db:Session=Depends(get_db),
    current_user: User = Depends(require_authenticated_user),
):
    data = get_payment_types_srv(db)
    return api_success(data)

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
