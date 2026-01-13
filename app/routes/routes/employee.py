from fastapi import APIRouter
from app.services.employee_service import get_employees,get_employee,add_employee,delete_employee,update_employee
from app.schemas.emplyeesBaseModel import NewEmployeeBase,UpdateEmployeeBase


router = APIRouter()

@router.get("/")
def get_employees():
    return {"message":"","data":get_employees(),"status":True}

@router.get("/{id}")
def get_employee(id:int):
    return {"message":"","data":get_employee(id),"status":True}

@router.put("/")
def add_employee(emp:NewEmployeeBase):
    add_employee(emp)
    return {"message":"","data":None,"status":True}

@router.delete("/{id}")
def delete_employee(id:int):
    delete_employee(id)
    return {"message":"","data":None,"status":True} 

@router.post("/")
def update_employee(emp:UpdateEmployeeBase):
    update_employee(emp)
    return {"message":"","data":None,"status":True} 

