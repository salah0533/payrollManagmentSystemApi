from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.vacation_service import get_all_vacations,get_employee_vacations,add_vacation,update_vacation,delete_vacation
from app.schemas.vacationBaseModel import VacationBaseModel,UpdateVacationBaseModel

router = APIRouter()

@router.get("/")
def get_vacations(db: Session = Depends(get_db)):
    return {"message":"","data":get_all_vacations(db),"status":True}

@router.get("/{id}")
def get_emp_vacations(id:int,db: Session = Depends(get_db)):
    return {"message":"","data":get_employee_vacations(id,db),"status":True}

@router.put("/")
def add_vacation_by_id(vac:VacationBaseModel,db: Session = Depends(get_db)):
    add_vacation(vac,db)
    return {"message":"","data":None,"status":True}

@router.post("/")
def update_vacation_by_id(vac:UpdateVacationBaseModel,db: Session = Depends(get_db)):
    update_vacation(vac,db)
    return {"message":"","data":None,"status":True}

@router.delete("/{id}")
def delete_vac(id:int,db: Session = Depends(get_db)):
    delete_vacation(id,db)
    return {"message":"","data":None,"status":True}
