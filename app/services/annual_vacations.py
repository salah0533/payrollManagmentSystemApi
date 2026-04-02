from sqlalchemy.orm import Session
from sqlalchemy import select,func
from app.models.annual_vacation import AnnualVacations
from app.models.vacation import Vacation
from app.models.types.vacationStatus import VacationStatuses
from app.models.types.vacationTypes import VacationTypes
from app.schemas.annualVcationModel import AnnualVacationModel,DeleteAnnualVacationModel

def get_ann_vac(emp_id:int,db:Session):
    return db.scalars(
        select(AnnualVacations)
        .where(AnnualVacations.employee_id==emp_id)
    ).all()
def get_all_ann_vac(emp_id:int,db:Session):
    return {
        str(year):{"used":0,"allowed_days": allowed}
        for year, allowed in db.execute(
            select(AnnualVacations.year, AnnualVacations.allowed_days)
            .where(AnnualVacations.employee_id == emp_id)
        )
    }

    
def get_used_vac_days(emp_id:int,db:Session):
    return db.execute(
        select(
            func.strftime('%Y', Vacation.start_date).label("year"),
            func.sum(
                func.julianday(Vacation.end_date) - func.julianday(Vacation.start_date) + 1
            ).label("total_days")
        )
        .where(
            Vacation.employee_id==emp_id,
            Vacation.is_paid.is_(True),
            Vacation.vacation_status == VacationStatuses.aproved,
            Vacation.vacation_type == VacationTypes.yearly_vacation
        )
        .group_by("year")
        .order_by("year")
    ).all()


def check_vacation_year(emp_id,year,db:Session):
    res = db.scalar(
        select(AnnualVacations.year)
        .where(AnnualVacations.employee_id==emp_id,
               AnnualVacations.year==year)
    )
    if res is not None:
        return True
    else :
        return False
    
def add_new_ann_vac(req:AnnualVacationModel,db:Session):
    new = AnnualVacations(year=req.year,employee_id=req.emp_id,allowed_days=req.allowed_days)
    db.add(new)
    db.commit()

def update_ann_vac(req:AnnualVacationModel,db:Session):
    ann_vac = db.get(AnnualVacations,(req.year,req.emp_id))
    if ann_vac:
        ann_vac.allowed_days = req.allowed_days
        db.commit()

def delete_ann_vac(req:DeleteAnnualVacationModel,db:Session):
    ann_vac = db.get(AnnualVacations,(req.year,req.emp_id))
    if ann_vac:
        db.delete(ann_vac)
        db.commit()


