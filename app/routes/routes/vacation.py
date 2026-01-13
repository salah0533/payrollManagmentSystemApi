from fastapi import APIRouter
from app.services.vacation_service import get_all_vacations,add_vacation,update_vacation
from app.schemas.vacationBaseModel import VacationBaseModel,UpdateVacationBaseModel

router = APIRouter()

@router.get("/")
def get_vacations():
    return {"message":"","data":get_all_vacations(),"status":True}

@router.put("/")
def add_vacation(vac:VacationBaseModel):
    add_vacation(vac)
    return {"message":"","data":None,"status":True}

@router.post("/")
def update_vacation(vac:UpdateVacationBaseModel):
    update_vacation(vac)
    return {"message":"","data":None,"status":True}


