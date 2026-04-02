from fastapi import APIRouter,Depends,HTTPException,status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.annual_vacations import get_ann_vac as get_ann_vac_svc,get_used_vac_days,check_vacation_year,get_all_ann_vac,add_new_ann_vac as add_new_ann_vac_src ,update_ann_vac,delete_ann_vac
from app.schemas.annualVcationModel import AnnualVacationModel,DeleteAnnualVacationModel
router = APIRouter()


@router.get("/{emp_id}")
def get_ann_vac(emp_id:int,db:Session=Depends(get_db)):
    data = get_ann_vac_svc(emp_id,db)
    return {"message":"","data":data,"status":True}

@router.get("/used_vac/{emp_id}")
def used_vac_days(emp_id: int, db: Session = Depends(get_db)):
    used = get_used_vac_days(emp_id, db)
    ann_vac = get_all_ann_vac(emp_id, db)
    for year, total in used:
        ann_vac[year]["used"] = total

    return {
        "message": "",
        "data": ann_vac,
        "status": True
    }

@router.put("/")
def add(req:AnnualVacationModel,db:Session=Depends(get_db)):
    add_new_ann_vac_src(req,db)
    return {"message":"","data":None,"status":True}

    
@router.post("/")
def update(req:AnnualVacationModel,db:Session=Depends(get_db)):
    update_ann_vac(req,db)
    return {"message":"","data":None,"status":True}

@router.delete("/")
def delete(req:DeleteAnnualVacationModel,db:Session=Depends(get_db)):
    delete_ann_vac(req,db)
    return {"message":"","data":None,"status":True}