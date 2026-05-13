from datetime import date

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.exceptions.db_exceptions.noVacationFound import NoVacationFound
from app.models.auth import User
from app.models.vacation import Vacation
from app.models.types.vacationStatus import VacationStatuses
from app.schemas.vacationBaseModel import VacationBaseModel, UpdateVacationBaseModel
from app.services.notification_service import NotificationService
from app.services.payroll_calculation_service import sync_vacation_with_payroll


def _vacation_title(status_code: str) -> str:
    return {
        "vacation_request_submitted": "Vacation request submitted",
        "vacation_approved": "Vacation approved",
        "vacation_rejected": "Vacation rejected",
        "vacation_cancelled": "Vacation cancelled",
    }[status_code]


def _vacation_message(vacation: Vacation, employee_name: str, status_code: str) -> str:
    period = f"{vacation.start_date.isoformat()} to {vacation.end_date.isoformat()}"
    if status_code == "vacation_request_submitted":
        return f"{employee_name} submitted a vacation request for {period}."
    if status_code == "vacation_approved":
        return f"Your vacation request for {period} was approved."
    if status_code == "vacation_rejected":
        return f"Your vacation request for {period} was rejected."
    return f"Your vacation request for {period} was cancelled."


def _get_employee_user_id(employee_id: int, db: Session) -> int | None:
    return db.scalar(select(User.id).where(User.employee_id == employee_id, User.deleted_at.is_(None)))


def _notify_vacation_submission(vacation: Vacation, db: Session, actor: User | None = None) -> None:
    employee_name = vacation.employee_tab.fullname if vacation.employee_tab else f"Employee #{vacation.employee_id}"
    NotificationService(db).notify_role(
        role_codes=["hr", "admin"],
        notification_type="vacation_request_submitted",
        title=_vacation_title("vacation_request_submitted"),
        message=_vacation_message(vacation, employee_name, "vacation_request_submitted"),
        entity_type="vacation",
        entity_id=vacation.id,
        actor_user_id=actor.id if actor else None,
        priority="normal",
        skip_if_no_recipients=True,
    )


def _notify_vacation_status_change(vacation: Vacation, db: Session, actor: User | None = None) -> None:
    status_to_type = {
        int(VacationStatuses.approved): "vacation_approved",
        int(VacationStatuses.rejected): "vacation_rejected",
        int(VacationStatuses.cancelled): "vacation_cancelled",
    }
    notification_type = status_to_type.get(vacation.vacation_status)
    if not notification_type:
        return

    user_id = _get_employee_user_id(vacation.employee_id, db)
    if user_id is None:
        return

    employee_name = vacation.employee_tab.fullname if vacation.employee_tab else f"Employee #{vacation.employee_id}"
    service = NotificationService(db)
    if service.notification_exists(
        notification_type=notification_type,
        entity_type="vacation",
        entity_id=vacation.id,
        user_id=user_id,
    ):
        return
    service.notify_user(
        user_id=user_id,
        notification_type=notification_type,
        title=_vacation_title(notification_type),
        message=_vacation_message(vacation, employee_name, notification_type),
        entity_type="vacation",
        entity_id=vacation.id,
        actor_user_id=actor.id if actor else None,
        priority="normal",
    )

def get_all_vacations(year:int,db:Session):
    return db.scalars(
        select(Vacation)
        .where(extract("year",Vacation.start_date)==year)
    ).all()

def get_all_current_vacations(db: Session):
    today = date.today()

    return db.scalars(
        select(Vacation)
        .where(
            Vacation.start_date <= today,
            Vacation.end_date >= today
        )
    ).all()

def get_employee_vacations(id:int,start,end,db:Session):

    return db.scalars(
        select(Vacation)
        .where(Vacation.employee_id==id,
               Vacation.start_date >= start,
               Vacation.end_date <= end
               )
    ).all()

def overlab_check(id:int,start,end,db:Session):
    return db.scalars(
    select(Vacation)
    .where(
        Vacation.employee_id == id,
        Vacation.start_date <= end,
        Vacation.end_date >= start
    )).all()

def get_emp_all_vacations(emp_id:int,db:Session):

    return db.scalars(
        select(Vacation)
        .where(Vacation.employee_id==emp_id)
    ).all()

    
def add_vacation(vac: VacationBaseModel, db: Session, *, actor: User | None = None):
    new_vac = Vacation(
        employee_id=vac.employee_id,
        start_date=vac.start_date,
        end_date=vac.end_date,
        vacation_type=vac.vacation_type,
        vacation_status=vac.vacation_status,
        is_paid=vac.is_paid,
    )
    db.add(new_vac)
    db.flush()
    db.refresh(new_vac, attribute_names=["employee_tab"])
    if vac.vacation_status == int(VacationStatuses.approved):
        sync_vacation_with_payroll(vac.employee_id, vac.start_date, vac.end_date, db, reason="vacation_approved")
        _notify_vacation_status_change(new_vac, db, actor=actor)
    elif vac.vacation_status in {int(VacationStatuses.rejected), int(VacationStatuses.cancelled)}:
        _notify_vacation_status_change(new_vac, db, actor=actor)
    else:
        _notify_vacation_submission(new_vac, db, actor=actor)
    db.commit()
    db.refresh(new_vac)
    return new_vac
    
def update_vacation(updated_vac: UpdateVacationBaseModel, db: Session, *, actor: User | None = None):
    vac = db.get(Vacation,updated_vac.id)
    if not vac:
        raise NoVacationFound(f"No vacation found with this id {updated_vac.id}")
    old_start = vac.start_date
    old_end = vac.end_date
    old_status = vac.vacation_status

    for key,val in updated_vac.model_dump(exclude_unset=True).items():
        if val is None or key == "id":
            continue
        setattr(vac,key,val)
    db.flush()
    if vac.vacation_status == int(VacationStatuses.approved):
        sync_vacation_with_payroll(vac.employee_id, vac.start_date, vac.end_date, db, reason="vacation_approved")
    elif old_status == int(VacationStatuses.approved):
        sync_vacation_with_payroll(vac.employee_id, old_start, old_end, db, reason="vacation_rejected")
    if old_status != vac.vacation_status:
        db.refresh(vac, attribute_names=["employee_tab"])
        _notify_vacation_status_change(vac, db, actor=actor)
    db.commit()
    db.refresh(vac)
    return vac

def delete_vacation(id:int,db:Session):
    vac = db.get(Vacation,id)
    if not vac :
        raise NoVacationFound()
    employee_id = vac.employee_id
    start_date = vac.start_date
    end_date = vac.end_date
    db.delete(vac)
    db.flush()
    sync_vacation_with_payroll(employee_id, start_date, end_date, db, reason="vacation_rejected")
    db.commit()
    
    
