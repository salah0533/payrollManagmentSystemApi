from datetime import date as Date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_authenticated_user, require_permissions
from app.exceptions.base_exception import BadRequestException, ConflictException
from app.models.auth import User
from app.schemas.notifications import NotificationActionResultRead, NotificationUnreadCountRead
from app.models.types.vacationStatus import VacationStatuses
from app.schemas.attendance_payroll import AttendanceDayRead, EmployeePayrollRead
from app.schemas.user import SelfAttendanceActionRequest, SelfVacationRequestCreate
from app.schemas.vacationBaseModel import VacationBaseModel
from app.services.attendance_calculation_service import create_attendance_event, get_attendance_days
from app.services.notification_service import NotificationService
from app.services.payroll_calculation_service import list_payroll_periods
from app.services.user_service import get_employee_or_404, serialize_employee
from app.services.vacation_service import add_vacation, get_emp_all_vacations, overlab_check


router = APIRouter()


def _current_employee_id(current_user: User) -> int:
    if current_user.employee_id is None:
        raise BadRequestException("This user is not linked to an employee profile")
    return current_user.employee_id


@router.get("/profile")
def get_my_profile(current_user: User = Depends(require_authenticated_user), db: Session = Depends(get_db)):
    employee = get_employee_or_404(_current_employee_id(current_user), db)
    return api_success(serialize_employee(employee))


@router.get("/attendance")
def get_my_attendance(
    start_date: Date,
    end_date: Date,
    current_user: User = Depends(require_permissions("attendance.read_own")),
    db: Session = Depends(get_db),
):
    employee_id = _current_employee_id(current_user)
    days = get_attendance_days(employee_id, start_date, end_date, db)
    return api_success([AttendanceDayRead.model_validate(day) for day in days])


@router.get("/payroll")
def get_my_payroll(
    period_id: int,
    current_user: User = Depends(require_permissions("payroll.read_own")),
    db: Session = Depends(get_db),
):
    from app.services.payroll_calculation_service import get_employee_payroll_by_period

    payroll = get_employee_payroll_by_period(_current_employee_id(current_user), period_id, db)
    return api_success(EmployeePayrollRead.model_validate(payroll))


@router.get("/payroll-periods")
def get_my_payroll_periods(
    current_user: User = Depends(require_permissions("payroll.read_own")),
    db: Session = Depends(get_db),
):
    return api_success(list_payroll_periods(db))


@router.get("/vacations")
def get_my_vacations(current_user: User = Depends(require_permissions("vacations.read_own")), db: Session = Depends(get_db)):
    vacations = get_emp_all_vacations(_current_employee_id(current_user), db)
    return api_success(vacations)


@router.post("/vacations/request")
def request_my_vacation(
    payload: SelfVacationRequestCreate,
    current_user: User = Depends(require_permissions("vacations.request_own")),
    db: Session = Depends(get_db),
):
    employee_id = _current_employee_id(current_user)
    if overlab_check(employee_id, payload.start_date, payload.end_date, db):
        raise ConflictException("Vacation already exists in the requested range", code="vacation_overlap")
    add_vacation(
        VacationBaseModel(
            employee_id=employee_id,
            start_date=payload.start_date,
            end_date=payload.end_date,
            vacation_type=payload.vacation_type,
            vacation_status=int(VacationStatuses.pending),
            is_paid=payload.is_paid,
        ),
        db,
        actor=current_user,
    )
    return api_success(status_code=201)


def _handle_self_attendance_action(
    *,
    event_type: str,
    payload: SelfAttendanceActionRequest,
    current_user: User,
    db: Session,
):
    employee_id = _current_employee_id(current_user)
    event_time = payload.event_time or datetime.now(timezone.utc)
    event, day = create_attendance_event(
        employee_id=employee_id,
        event_type=event_type,
        event_time=event_time,
        db=db,
        source="self_service",
        note=payload.note,
        created_by=current_user.id,
    )
    return api_success({"event": event, "attendance_day": day}, status_code=201)


@router.post("/attendance/check-in")
def check_in_myself(
    payload: SelfAttendanceActionRequest,
    current_user: User = Depends(require_permissions("attendance.check_in_own")),
    db: Session = Depends(get_db),
):
    return _handle_self_attendance_action(event_type="check_in", payload=payload, current_user=current_user, db=db)


@router.post("/attendance/break-start")
def break_start_myself(
    payload: SelfAttendanceActionRequest,
    current_user: User = Depends(require_permissions("attendance.check_in_own")),
    db: Session = Depends(get_db),
):
    return _handle_self_attendance_action(event_type="break_start", payload=payload, current_user=current_user, db=db)


@router.post("/attendance/break-end")
def break_end_myself(
    payload: SelfAttendanceActionRequest,
    current_user: User = Depends(require_permissions("attendance.check_in_own")),
    db: Session = Depends(get_db),
):
    return _handle_self_attendance_action(event_type="break_end", payload=payload, current_user=current_user, db=db)


@router.post("/attendance/check-out")
def check_out_myself(
    payload: SelfAttendanceActionRequest,
    current_user: User = Depends(require_permissions("attendance.check_in_own")),
    db: Session = Depends(get_db),
):
    return _handle_self_attendance_action(event_type="check_out", payload=payload, current_user=current_user, db=db)


@router.get("/notifications")
def get_my_notifications(
    unread_only: bool = False,
    archived: bool = False,
    include_expired: bool = False,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_permissions("notifications.read_own")),
    db: Session = Depends(get_db),
):
    service = NotificationService(db)
    return api_success(
        service.get_user_notifications(
            user_id=current_user.id,
            unread_only=unread_only,
            is_archived=archived,
            include_expired=include_expired,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/notifications/unread-count")
def get_my_notification_unread_count(
    current_user: User = Depends(require_permissions("notifications.read_own")),
    db: Session = Depends(get_db),
):
    unread_count = NotificationService(db).get_unread_count(user_id=current_user.id)
    return api_success(NotificationUnreadCountRead(unread_count=unread_count))


@router.post("/notifications/{notification_id}/read")
def mark_my_notification_read(
    notification_id: str,
    current_user: User = Depends(require_permissions("notifications.read_own")),
    db: Session = Depends(get_db),
):
    notification = NotificationService(db).mark_as_read(user_id=current_user.id, notification_id=notification_id)
    db.commit()
    return api_success(notification)


@router.post("/notifications/read-all")
def mark_all_my_notifications_read(
    current_user: User = Depends(require_permissions("notifications.read_own")),
    db: Session = Depends(get_db),
):
    updated = NotificationService(db).mark_all_as_read(user_id=current_user.id)
    db.commit()
    return api_success(NotificationActionResultRead(updated=updated, status="marked_all_as_read"))


@router.post("/notifications/{notification_id}/archive")
def archive_my_notification(
    notification_id: str,
    current_user: User = Depends(require_permissions("notifications.read_own")),
    db: Session = Depends(get_db),
):
    notification = NotificationService(db).archive_notification(user_id=current_user.id, notification_id=notification_id)
    db.commit()
    return api_success(notification)
