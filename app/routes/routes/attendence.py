from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends
from app.core.responses import api_success
from app.exceptions.base_exception import BadRequestException
from app.schemas.attendance_payroll import (
        AttendanceActionRequest,
        AttendanceCorrectionRequest,
        AttendanceDayRead,
        AttendanceReviewRequest,
        AttendanceSmartCorrectionRequest,
)
from app.dependencies.auth import require_permissions, require_self_or_permission
from app.models.auth import User
from app.services.attendance_calculation_service import (
        apply_smart_attendance_status_correction,
        create_attendance_correction,
        create_attendance_event,
        delete_attendance_day,
        get_attendance_day,
        get_attendance_days,
        get_attendance_days_by_date,
        get_attendance_days_in_range,
        mark_all_employees_present,
        recalculate_attendance_for_employee,
        review_attendance_day,
)
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
        days = get_attendance_days_by_date(date, db)
        return api_success([AttendanceDayRead.model_validate(day) for day in days])


@router.get("/days/{work_date}")
def get_attendance_days_for_date(
        work_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.read_all")),
):
        days = get_attendance_days_by_date(work_date, db)
        return api_success([AttendanceDayRead.model_validate(day) for day in days])

@router.get("/emp/{id}")
def get_emp_att(
        id:int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all", employee_param="id")),
):
        start_of_month = Date.today().replace(day=1)
        days = get_attendance_days(id, start_of_month, Date.today(), db)
        return api_success([AttendanceDayRead.model_validate(day) for day in days])

@router.get("/attbytim/{start}/{end}")
def get_att_by_time(
        start:Date,
        end:Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.read_all")),
):
        days = get_attendance_days_in_range(start, end, db)
        return api_success([AttendanceDayRead.model_validate(day) for day in days])

@router.get("/emp/{id}/{start}/{end}")
def get_emp_att(
        id:int,
        start:Date,
        end:Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all", employee_param="id")),
):
        days = get_attendance_days(id, start, end, db)
        return api_success([AttendanceDayRead.model_validate(day) for day in days])
        

@router.put("/")
def add_attendence(
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        raise BadRequestException("Legacy attendance write endpoints are disabled. Use AttendanceDay events or correction endpoints.")

@router.put("/mark_all_present")
def mark_all_present(
        work_date: Date | None = None,
        db:Session=Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        data = mark_all_employees_present(work_date or Date.today(), db, created_by=current_user.id)
        return api_success(data)
        
@router.delete("/{att_id}")
def delete_att(
        att_id:int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        raise BadRequestException("Legacy attendance delete endpoints are disabled. Use /attendance/day/{employee_id}/{work_date}.")


@router.delete("/day/{employee_id}/{work_date}")
def delete_attendance_day_view(
        employee_id: int,
        work_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        result = delete_attendance_day(employee_id, work_date, db, deleted_by=current_user.id)
        return api_success(result)


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
        return api_success({"event":event,"attendance_day":day}, status_code=201)


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
        return api_success({"event":event,"attendance_day":day}, status_code=201)


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
        return api_success({"event":event,"attendance_day":day}, status_code=201)


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
        return api_success({"event":event,"attendance_day":day}, status_code=201)


@router.post("/manual-correction")
def manual_correction(
        req: AttendanceCorrectionRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        req.corrected_by = current_user.id
        correction, day = create_attendance_correction(req, db)
        return api_success({"correction":correction,"attendance_day":day}, status_code=201)


@router.post("/day/{employee_id}/{work_date}/smart-correction")
def smart_status_correction(
        employee_id: int,
        work_date: Date,
        req: AttendanceSmartCorrectionRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.correct")),
):
        correction, day = apply_smart_attendance_status_correction(
                employee_id,
                work_date,
                req.target_status,
                current_user.id,
                req.reason,
                req.options,
                db,
        )
        return api_success({"correction": correction, "attendance_day": day}, status_code=201)


@router.post("/day/{employee_id}/{work_date}/review")
def review_attendance(
        employee_id: int,
        work_date: Date,
        req: AttendanceReviewRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.approve")),
):
        day = review_attendance_day(employee_id, work_date, req.review_status, current_user.id, req.note, db)
        return api_success(AttendanceDayRead.model_validate(day))


@router.get("/day/{employee_id}/{work_date}")
def get_attendance_day_view(
        employee_id: int,
        work_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all")),
):
        day = get_attendance_day(employee_id, work_date, db)
        return api_success(AttendanceDayRead.model_validate(day) if day else None)


@router.get("/employee/{employee_id}/{start_date}/{end_date}")
def get_employee_attendance_days(
        employee_id: int,
        start_date: Date,
        end_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_self_or_permission("attendance.read_all")),
):
        days = get_attendance_days(employee_id, start_date, end_date, db)
        return api_success([AttendanceDayRead.model_validate(day) for day in days])


@router.post("/recalculate/{employee_id}/{start_date}/{end_date}")
def recalculate_attendance(
        employee_id: int,
        start_date: Date,
        end_date: Date,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_permissions("attendance.recalculate")),
):
        days = recalculate_attendance_for_employee(employee_id, start_date, end_date, db)
        return api_success({"employee_id":employee_id,"recalculated_days":len(days)})



