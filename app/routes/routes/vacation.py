from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.vacation_service import overlab_check,get_all_current_vacations,get_all_vacations,get_employee_vacations,add_vacation,update_vacation,delete_vacation
from app.schemas.vacationBaseModel import VacationBaseModel,UpdateVacationBaseModel
from datetime import date
router = APIRouter()

@router.get("/")
def get_vacations(db: Session = Depends(get_db)):
    return {"message":"","data":get_all_vacations(db),"status":True}

@router.get("/current")
def get_current_vacations(db: Session = Depends(get_db)):
    return {"message":"","data":get_all_current_vacations(db),"status":True}

@router.get("/{id}/{start}/{end}")
def get_emp_vacations(id:int,start:date,end:date,db: Session = Depends(get_db)):
    return {"message":"","data":get_employee_vacations(id,start,end,db),"status":True}

@router.put("/")
def add_vacation_by_id(vac:VacationBaseModel,db: Session = Depends(get_db)):
    if overlab_check(vac.employee_id,vac.start_date,vac.end_date,db) != []:
        return {"message":"vacation already exist in these dates","data":None,"status":False}
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
