from fastapi import APIRouter,Depends
from app.services.settings import update_settings,add_new_settings,get_settings as get_settings_svc
from app.services.policy_service import (
    get_default_work_schedule,
    get_or_create_payroll_policy,
    update_default_work_schedule,
    update_payroll_policy,
)
from app.schemas.attendance_payroll import PayrollPolicyPayload, WorkSchedulePayload
from app.schemas.settingBaseModel import SettingsBaseModel
from sqlalchemy.orm import Session
from app.db.session import get_db

router = APIRouter()

@router.get("/")
def get_settings(db:Session=Depends(get_db)):
    res = get_settings_svc(db)
    return {"message":"","data":res,"status":True}
    
# @router.put("/")
# def add_new(set:SettingsBaseModel,db:Session=Depends(get_db)):
#     add_new_settings(set,db)
#     return {"message":"","data":None,"status":True}

@router.post("/")
def get_salary_types(set:SettingsBaseModel,db:Session=Depends(get_db)):
    update_settings(set,db)
    return {"message":"","data":None,"status":True}


@router.get("/work-schedule")
def get_work_schedule(db: Session = Depends(get_db)):
    schedule = get_default_work_schedule(db)
    return {"message":"","data":schedule,"status":True}


@router.put("/work-schedule")
def put_work_schedule(payload: WorkSchedulePayload, db: Session = Depends(get_db)):
    schedule = update_default_work_schedule(db, **payload.model_dump())
    db.commit()
    db.refresh(schedule)
    return {"message":"","data":schedule,"status":True}


@router.get("/payroll-policy")
def get_payroll_policy(db: Session = Depends(get_db)):
    policy = get_or_create_payroll_policy(db)
    return {"message":"","data":policy,"status":True}


@router.put("/payroll-policy")
def put_payroll_policy(payload: PayrollPolicyPayload, db: Session = Depends(get_db)):
    policy = update_payroll_policy(db, **payload.model_dump())
    db.commit()
    db.refresh(policy)
    return {"message":"","data":policy,"status":True}

