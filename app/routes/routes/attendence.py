from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends
from app.models.types.attendenceTypes import AttendanceType
from app.schemas.attendenceBaseModel import AttendenceBaseModel,DataRange
from app.schemas.attendance_payroll import AttendanceActionRequest, AttendanceCorrectionRequest
from app.dependencies.auth import require_permissions, require_self_or_permission
from app.models.auth import User
from app.services.attendance_calculation_service import (
        create_attendance_correction,
        create_attendance_event,
        get_attendance_day,
        get_attendance_days,
        recalculate_attendance_for_employee,
)
from app.services.attendence_service import add_new_attendence,get_attendance_type,get_attendence, get_attendence_by_date,update_attendence,get_employee_attendence_by_date,get_employee_attendence,get_employees_attendence,delete_attendence,mark_all_emp_present
from datetime import date as Date
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()


@router.get("/emps/{date}")
def get_emps_att(
        date:Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.read_all")),
):
        res = get_employees_attendence(date,db)
        return {"message":"","data":res,"status":True}

@router.get("/emp/{id}")
def get_emp_att(
        id:int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all", employee_param="id")),
):
        res = get_employee_attendence(id,db)
        return {"message":"","data":res,"status":True}

@router.get("/attbytim/{start}/{end}")
def get_att_by_time(
        start:Date,
        end:Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.read_all")),
):
        res = get_attendence_by_date(start,end,db)
        return {"message":"","data":res,"status":True}

@router.get("/emp/{id}/{start}/{end}")
def get_emp_att(
        id:int,
        start:Date,
        end:Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all", employee_param="id")),
):
        res = get_employee_attendence_by_date(id,start,end,db)
        return {"message":"","data":res,"status":True}
        

@router.put("/")
def add_attendence(
        req:AttendenceBaseModel,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        att = get_attendence(req.employee_id,req.date,db) if req.employee_id else None
        req.attendence_type = get_attendance_type(
                req.employee_id,
                req.entry_time,
                req.exit_time,
                req.attendence_type,
                req.date,
                db,
        )
        if req.attendence_type  == AttendanceType.Absent :
                req.entry_time = time(0,0,0)
        if att:
                update_attendence(att,req,db)
        else:
                add_new_attendence(req,db)

        return {"message":"","data":None,"status":True}

@router.put("/mark_all_present")
def mark_all_present(
        db:Session=Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        data = mark_all_emp_present(db)
        return {"message":"","data":data,"status":True}
        
@router.delete("/{att_id}")
def delete_att(
        att_id:int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        delete_attendence(att_id,db)
        return {"message":"","data":None,"status":True}


@router.post("/check-in")
def check_in(
        req: AttendanceActionRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        event_time = req.event_time or datetime.now(timezone.utc)
        event, day = create_attendance_event(
                employee_id=req.employee_id,
                event_type="check_in",
                event_time=event_time,
                db=db,
                source=req.source,
                note=req.note,
                created_by=current_user.id,
        )
        return {"message":"","data":{"event":event,"attendance_day":day},"status":True}


@router.post("/break-start")
def break_start(
        req: AttendanceActionRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        event_time = req.event_time or datetime.now(timezone.utc)
        event, day = create_attendance_event(
                employee_id=req.employee_id,
                event_type="break_start",
                event_time=event_time,
                db=db,
                source=req.source,
                note=req.note,
                created_by=current_user.id,
        )
        return {"message":"","data":{"event":event,"attendance_day":day},"status":True}


@router.post("/break-end")
def break_end(
        req: AttendanceActionRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        event_time = req.event_time or datetime.now(timezone.utc)
        event, day = create_attendance_event(
                employee_id=req.employee_id,
                event_type="break_end",
                event_time=event_time,
                db=db,
                source=req.source,
                note=req.note,
                created_by=current_user.id,
        )
        return {"message":"","data":{"event":event,"attendance_day":day},"status":True}


@router.post("/check-out")
def check_out(
        req: AttendanceActionRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        event_time = req.event_time or datetime.now(timezone.utc)
        event, day = create_attendance_event(
                employee_id=req.employee_id,
                event_type="check_out",
                event_time=event_time,
                db=db,
                source=req.source,
                note=req.note,
                created_by=current_user.id,
        )
        return {"message":"","data":{"event":event,"attendance_day":day},"status":True}


@router.post("/manual-correction")
def manual_correction(
        req: AttendanceCorrectionRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        req.corrected_by = current_user.id
        correction, day = create_attendance_correction(req, db)
        return {"message":"","data":{"correction":correction,"attendance_day":day},"status":True}


@router.get("/day/{employee_id}/{work_date}")
def get_attendance_day_view(
        employee_id: int,
        work_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all")),
):
        day = get_attendance_day(employee_id, work_date, db)
        return {"message":"","data":day,"status":True}


@router.get("/employee/{employee_id}/{start_date}/{end_date}")
def get_employee_attendance_days(
        employee_id: int,
        start_date: Date,
        end_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all")),
):
        days = get_attendance_days(employee_id, start_date, end_date, db)
        return {"message":"","data":days,"status":True}


@router.post("/recalculate/{employee_id}/{start_date}/{end_date}")
def recalculate_attendance(
        employee_id: int,
        start_date: Date,
        end_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.recalculate")),
):
        days = recalculate_attendance_for_employee(employee_id, start_date, end_date, db)
        return {"message":"","data":{"employee_id":employee_id,"recalculated_days":len(days)},"status":True}



