from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_hr_or_admin, require_self_or_permission
from app.models.auth import User
from app.services.annual_vacations import get_ann_vac as get_ann_vac_svc,get_used_vac_days,check_vacation_year,get_all_ann_vac,add_new_ann_vac as add_new_ann_vac_src ,update_ann_vac,delete_ann_vac
from app.schemas.annualVcationModel import AnnualVacationModel,DeleteAnnualVacationModel
router = APIRouter()


@router.get("/{emp_id}")
def get_ann_vac(
    emp_id:int,
    db:Session=Depends(get_db),
    current_user: User = Depends(require_self_or_permission("employees.read", employee_param="emp_id")),
):
    data = get_ann_vac_svc(emp_id,db)
    return api_success(data)

@router.get("/used_vac/{emp_id}")
def used_vac_days(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_permission("employees.read", employee_param="emp_id")),
):
    used = get_used_vac_days(emp_id, db)
    ann_vac = get_all_ann_vac(emp_id, db)
    for year, total in used:
        ann_vac[year]["used"] = total

    return api_success(ann_vac)

@router.put("/")
def add(
    req:AnnualVacationModel,
    db:Session=Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    add_new_ann_vac_src(req,db)
    return api_success(status_code=201)

    
@router.post("/")
def update(
    req:AnnualVacationModel,
    db:Session=Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    update_ann_vac(req,db)
    return api_success()

@router.delete("/")
def delete(
    req:DeleteAnnualVacationModel,
    db:Session=Depends(get_db),
    current_user: User = Depends(require_hr_or_admin),
):
    delete_ann_vac(req,db)
    return api_success()
