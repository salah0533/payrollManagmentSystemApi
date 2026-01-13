from fastapi import APIRouter
from app.schemas.attendenceBaseModel import AttendenceBaseModel
from app.services.attendence_service import add_new_attendence,get_attendence_type,update_entry_attendence,update_exit_attendence,get_attendence,add_entry_attendence

router = APIRouter()

@router.put("/add_attendence")
def add_attendence(req:AttendenceBaseModel):
    try:
        att = get_attendence(req.employee_id,req.date)
        attendence_type = get_attendence_type(req.employee_id)

        if att:
            if req.exit_time:
                if req.entry_time < req.exit_time:
                    update_entry_attendence(att,req.date,attendence_type)
                    update_exit_attendence(att,req.date)
                else:
                    return {"message":"the entry time is biger the exit time","data":None,"status":False}
            else:
                update_entry_attendence(att,req.date,attendence_type)
        elif req.exit_time:
            if req.entry_time < req.exit_time:
                add_new_attendence(req.employee_id,req.entry_time,req.exit_time,req.date,type_id=attendence_type) 
            else:
                return {"message":"the entry time is biger the exit time","data":None,"status":False}
        else:
            add_entry_attendence(req.employee_id,req.entry_time,req.date,attendence_type)

        return {"message":"seccuess","data":None,"status":True}

    except Exception as e:
        return {"message":"an error happend"}


