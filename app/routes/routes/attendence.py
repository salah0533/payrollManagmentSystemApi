from fastapi import APIRouter
from app.shemas.attendenceBaseModel import AttendenceBaseModel
from app.services.attendence_service import add_new_attendence,get_attendence_type

router = APIRouter()

@router.put("/add_attendence")
def add_attendence(req:AttendenceBaseModel):
    try:
        if req.entry_time >= req.exit_time:
            return {"message":"","dat":None}
        attendence_type = get_attendence_type(req.employee_id)
        

        if req.exit_time:
            add_new_attendence(req.employee_id,req.entry_time,req.exit_time,req.date,type_id=attendence_type)
    except Exception as e:
        return {"message":"an error happend"}


