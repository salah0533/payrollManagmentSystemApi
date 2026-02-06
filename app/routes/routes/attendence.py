from fastapi import APIRouter
from app.schemas.attendenceBaseModel import AttendenceBaseModel,DataRange
from app.services.attendence_service import add_new_attendence,get_attendance_type,get_attendence,update_attendence,get_employee_attendence,get_employees_attendence,delete_attendence
from datetime import date as Date
from fastapi import Depends

router = APIRouter()


@router.get("/emps/{date}")
def get_emps_att(date:Date):
        res = get_employees_attendence()
        return {"message":"","data":res,"status":True}

@router.get("/emp/{id}/{start}/{end}")
def get_emp_att(id:int,dates:DataRange=Depends()):
        res = get_employee_attendence(id,dates.start,dates.end)
        return {"message":"","data":res,"status":True}
        

@router.put("/add_attendence")
def add_attendence(req:AttendenceBaseModel):

        att = get_attendence(req.employee_id,req.date) if req.employee_id else None
        salary_type = att.employee_tab.salary_type
        req.attendence_type = 0 if salary_type==2 else  get_attendance_type(req.employee_id,req.entry_time,req.exit_time,req.attendence_type)


        if att:
                update_attendence(att,req)
        else:
                add_new_attendence(req)

@router.delete("/{att_id}")
def delete_att(att_id:int):
        delete_attendence(att_id)
        return {"message":"","data":None,"Status":True}



