from fastapi import APIRouter,Depends
from app.dependencies.auth import require_authenticated_user
from app.models.auth import User
from app.services.att_types_service import get_att_types_srv
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_att_types(
    db:Session=Depends(get_db),
    current_user: User = Depends(require_authenticated_user),
):
    data = get_att_types_srv(db)
    return {"message":"","data":data,"status":True}
