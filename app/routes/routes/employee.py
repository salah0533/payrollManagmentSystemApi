from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.employee_service import get_employees,get_employee,add_employee,delete_employee,update_employee
from app.schemas.emplyeesBaseModel import NewEmployeeBase,UpdateEmployeeBase


router = APIRouter()

@router.get("/")
def list_employees(db: Session = Depends(get_db)):
    return {"message":"","data":get_employees(db),"status":True}

@router.get("/{id}")
def get_employee_by_id(id:int,db: Session = Depends(get_db)):
    return {"message":"","data":get_employee(id,db),"status":True}

@router.put("/")
def create_employee(emp:NewEmployeeBase,db: Session = Depends(get_db)):
    add_employee(emp,db)
    return {"message":"","data":None,"status":True}

@router.delete("/{id}")
def delete_employee_by_id(id:int,db: Session = Depends(get_db)):
    delete_employee(id,db)
    return {"message":"","data":None,"status":True} 

@router.post("/")
def update_employee_by_id(emp:UpdateEmployeeBase,db: Session = Depends(get_db)):
    update_employee(emp,db)
    return {"message":"","data":None,"status":True} 

