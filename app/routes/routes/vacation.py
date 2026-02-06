from fastapi import APIRouter
from app.services.vacation_service import get_all_vacations,add_vacation,update_vacation,delete_vacation,get_all_vacations
from app.schemas.vacationBaseModel import VacationBaseModel,UpdateVacationBaseModel

router = APIRouter()

@router.get("/")
def get_vacations():
    return {"message":"","data":get_all_vacations(),"status":True}

@router.get("/{id}")
def get_emp_vacations(id:int):
    return {"message":"","data":get_all_vacations(id),"status":True}

@router.put("/")
def add_vacation(vac:VacationBaseModel):
    add_vacation(vac)
    return {"message":"","data":None,"status":True}

@router.post("/")
def update_vacation(vac:UpdateVacationBaseModel):
    update_vacation(vac)
    return {"message":"","data":None,"status":True}


@router.delete("/")
def delete_vac(id:int):
    delete_vacation(id)
    return {"message":"","data":None,"status":True}
