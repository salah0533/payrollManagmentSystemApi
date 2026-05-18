from fastapi import APIRouter,Depends
from app.core.responses import api_success
from app.services.settings import update_settings,add_new_settings,get_settings as get_settings_svc
from app.services.policy_service import (
    get_default_work_schedule,
    get_or_create_payroll_policy,
    update_default_work_schedule,
    update_payroll_policy,
)
from app.dependencies.auth import require_authenticated_user, require_permissions
from app.models.auth import User
from app.schemas.attendance_payroll import PayrollPolicyPayload, WorkSchedulePayload
from app.schemas.settingBaseModel import SettingsBaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_settings(
    db:Session=Depends(get_db),
    current_user: User = Depends(require_permissions("settings.read")),
):
    res = get_settings_svc(db)
    return api_success(res)
    
# @router.put("/")
# def add_new(set:SettingsBaseModel,db:Session=Depends(get_db)):
#     add_new_settings(set,db)
#     return {"message":"","data":None,"status":True}

@router.post("/")
def get_salary_types(
    set:SettingsBaseModel,
    db:Session=Depends(get_db),
    current_user: User = Depends(require_permissions("settings.update")),
):
    update_settings(set,db)
    return api_success()


@router.get("/work-schedule")
def get_work_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("settings.read")),
):
    schedule = get_default_work_schedule(db)
    return api_success(schedule)


@router.put("/work-schedule")
def put_work_schedule(
    payload: WorkSchedulePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("settings.update")),
):
    current_schedule = get_default_work_schedule(db)
    impactful_fields = ("start_time", "end_time", "break_minutes", "weekly_off_days", "timezone", "is_default")
    previous_values = {field: getattr(current_schedule, field) for field in impactful_fields}
    schedule = update_default_work_schedule(db, **payload.model_dump())
    if any(previous_values[field] != getattr(schedule, field) for field in impactful_fields):
        from app.services.payroll_calculation_service import reconcile_existing_payrolls_for_settings_change

        reconcile_existing_payrolls_for_settings_change(
            db,
            reason="work_schedule_updated",
            created_by=current_user.id,
        )
    db.commit()
    db.refresh(schedule)
    return api_success(schedule)


@router.get("/payroll-policy")
def get_payroll_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("settings.read")),
):
    policy = get_or_create_payroll_policy(db)
    return api_success(policy)


@router.get("/payroll-currency")
def get_payroll_currency(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_authenticated_user),
):
    policy = get_or_create_payroll_policy(db)
    currency = policy.default_currency if policy.default_currency != "ILS" else "DZD"
    return api_success({"default_currency": currency})


@router.put("/payroll-policy")
def put_payroll_policy(
    payload: PayrollPolicyPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("settings.update")),
):
    current_policy = get_or_create_payroll_policy(db)
    impactful_fields = (
        "minimum_overtime_minutes",
        "minimum_auto_pay_minutes",
        "allowed_late_minutes",
        "paid_vacation_counts_for_daily",
        "overtime_enabled",
        "late_makeup_enabled",
        "late_deduction_enabled",
        "auto_recalculate_draft_payroll",
        "lock_payroll_after_payment",
        "holidays_json",
    )
    previous_values = {field: getattr(current_policy, field) for field in impactful_fields}
    policy = update_payroll_policy(db, **payload.model_dump())
    if any(previous_values[field] != getattr(policy, field) for field in impactful_fields):
        from app.services.payroll_calculation_service import reconcile_existing_payrolls_for_settings_change

        reconcile_existing_payrolls_for_settings_change(
            db,
            reason="payroll_policy_updated",
            created_by=current_user.id,
        )
    db.commit()
    db.refresh(policy)
    return api_success(policy)

