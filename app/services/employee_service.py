from app.models.employees import Employees
from app.exceptions.db_exceptions.employeeNotFound import EmployeeNotFound
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import select


def get_employees(db:Session)->list[dict]:
    try:
        res = db.execute(select(Employees))
        return res.mappings().all()
    except SQLAlchemyError as e:
        raise e

def get_employee(id:int,db:Session)->dict:
    try:
        em = db.get(Employees,id)
        if em:
            return em.to_dict()
        else:
            raise EmployeeNotFound("Employee not found")
    except Exception as e:
        raise e
    
def add_employee(emp:dict,db:Session):
    try:
        new_emp = Employees(
            fullname=emp.fullname,
            job_title=emp.job_title,
            phone=emp.phone,
            email=emp.email,
            dues=emp.dues,
            salary_type=emp.salary_type,
            daily_work_hours=emp.daily_work_hours,
            extra_hours_price=emp.extra_hours_price,
            hour_price=emp.hour_price,
            day_price=emp.day_price,
            monthly_price=emp.monthly_price,
            vacation_days=emp.vacation_days,
            is_active=emp.is_active,
            allowed_late=emp.allowed_late,
            min_extraTime=emp.min_extraTime,
        )
        db.add(new_emp)
        db.commit()
        db.refresh(new_emp)
    except SQLAlchemyError as e:
        raise e

def update_employee(new_data:dict,db:Session)->None:
    try:
        employee = db.get(Employees,new_data.id)
        if not employee:
            raise EmployeeNotFound("Employee not found")
        
        for key,val in new_data.model_dump(exclude_unset=True).items():
            if val is None:
                continue
            setattr(employee,key,val)
        db.commit()

    except Exception as e:
        raise e

def delete_employee(id:int,db:Session):
    try:
        
        emp = db.get(Employees,id)
        if not emp:
            raise EmployeeNotFound("Employee not found")
        db.delete(emp)
        db.commit()
    except Exception as e:
        raise e