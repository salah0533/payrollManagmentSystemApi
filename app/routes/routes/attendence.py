from fastapi import APIRouter, Depends
from app.schemas.attendenceBaseModel import AttendenceBaseModel,DataRange
from app.services.attendence_service import add_new_attendence,get_attendance_type,get_attendence,update_attendence,get_employee_attendence,get_employees_attendence,delete_attendence
from datetime import date as Date
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()


@router.get("/emps/{date}")
def get_emps_att(date:Date,db: Session = Depends(get_db)):
        res = get_employees_attendence(date,db)
        return {"message":"","data":res,"status":True}

@router.get("/emp/{id}/{start}/{end}")
def get_emp_att(id:int,start:Date,end:Date,db: Session = Depends(get_db)):
        res = get_employee_attendence(id,start,end,db)
        return {"message":"","data":res,"status":True}
        

@router.put("/add_attendence")
def add_attendence(req:AttendenceBaseModel,db: Session = Depends(get_db)):

        att = get_attendence(req.employee_id,req.date,db) if req.employee_id else None
        req.attendence_type = get_attendance_type(
                req.employee_id,
                req.entry_time,
                req.exit_time,
                req.attendence_type,
                db,
        )

        if att:
                update_attendence(att,req,db)
        else:
                add_new_attendence(req,db)

        return {"message":"","data":None,"status":True}

@router.delete("/{att_id}")
def delete_att(att_id:int,db: Session = Depends(get_db)):
        delete_attendence(att_id,db)
        return {"message":"","data":None,"status":True}



