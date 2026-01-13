from app.models.employees import Employees
from fastapi import Depends
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from app.db.session import get_db
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select


def get_employees(id:int,db:Session=Depends(get_db))->dict:
    try:
        res = db.execute(select(Employees))
        return res.mappings().all()
    except SQLAlchemyError as e:
        raise e

def get_employee(id:int,db:Session=Depends(get_db))->dict:
    try:
        em = db.get(Employees,id)
        if em:
            return em.to_dict()
        else:
            raise EmployeeNotFound("Employee not found")
    except Exception as e:
        raise e
    
def add_employee(emp:dict,db:Session=Depends(get_db)):
    try:
        new_emp = Employees(name=emp.name,job_title=emp.job_title,phone=emp.phone,dues=emp.dues,
                            role=emp.role,daly_work_hours=emp.daly_work_hours,
                            extra_hours_price=emp.extra_hours_price,hour_price=emp.hour_price,
                            day_price=emp.day_price,month_price=emp.month_price,
                            vacation_days=emp.vacation_days)
        db.add(new_emp)
        db.commit()
        db.refresh(new_emp)
    except SQLAlchemyError as e:
        raise e

def update_employee(new_data:dict,db:Session=Depends(get_db))->None:
    try:
        employee = db.get(Employees,new_data.id)
        if not employee:
            raise EmployeeNotFound("Employee not found")
        
        for key,val in new_data:
            if not val:
                continue
            setattr(employee,key,val)
        db.commit()

    except Exception as e:
        raise e

def delete_employee(id:int,db:Session=Depends(get_db)):
    try:
        
        emp = db.get(Employees,id)
        if not emp:
            raise EmployeeNotFound("Employee not found")
        db.delete(emp)
        db.commit()
    except Exception as e:
        raise e