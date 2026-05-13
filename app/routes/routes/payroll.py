from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.attendance_payroll import PayrollAdjustmentCreate, PayrollDiscrepancyResolveRequest
from app.services.payroll_calculation_service import (
    add_payroll_adjustment,
    approve_employee_payroll,
    get_employee_payroll_by_period,
    get_payroll_discrepancies,
    get_payroll_history,
    get_payroll_period,
    mark_employee_payroll_paid,
    recalculate_payroll_period,
    resolve_payroll_discrepancy,
    calculate_employee_payroll,
)


router = APIRouter()


@router.get("/period/{period_id}")
def get_period(period_id: int, db: Session = Depends(get_db)):
    period = get_payroll_period(period_id, db)
    return {"message": "", "data": period, "status": True}


@router.get("/employee/{employee_id}/{period_id}")
def get_employee_period_payroll(employee_id: int, period_id: int, db: Session = Depends(get_db)):
    payroll = get_employee_payroll_by_period(employee_id, period_id, db)
    return {"message": "", "data": payroll, "status": True}


@router.post("/recalculate/{employee_id}/{period_id}")
def recalculate_employee_payroll(employee_id: int, period_id: int, db: Session = Depends(get_db)):
    payroll = calculate_employee_payroll(employee_id, period_id, db, reason="manual_recalculation", force_history=True)
    db.commit()
    db.refresh(payroll)
    return {"message": "", "data": payroll, "status": True}


@router.post("/recalculate-period/{period_id}")
def recalculate_period(period_id: int, db: Session = Depends(get_db)):
    payrolls = recalculate_payroll_period(period_id, db)
    return {"message": "", "data": payrolls, "status": True}


@router.post("/approve/{employee_payroll_id}")
def approve_payroll(employee_payroll_id: int, approved_by: int | None = None, db: Session = Depends(get_db)):
    payroll = approve_employee_payroll(employee_payroll_id, db, approved_by=approved_by)
    return {"message": "", "data": payroll, "status": True}


@router.post("/mark-paid/{employee_payroll_id}")
def mark_paid(employee_payroll_id: int, paid_by: int | None = None, db: Session = Depends(get_db)):
    payroll = mark_employee_payroll_paid(employee_payroll_id, db, paid_by=paid_by)
    return {"message": "", "data": payroll, "status": True}


@router.get("/history/{employee_payroll_id}")
def get_history(employee_payroll_id: int, db: Session = Depends(get_db)):
    history = get_payroll_history(employee_payroll_id, db)
    return {"message": "", "data": history, "status": True}


@router.get("/discrepancies/{period_id}")
def get_discrepancy_list(period_id: int, db: Session = Depends(get_db)):
    discrepancies = get_payroll_discrepancies(period_id, db)
    return {"message": "", "data": discrepancies, "status": True}


@router.post("/discrepancy/{discrepancy_id}/resolve")
def resolve_discrepancy(discrepancy_id: int, req: PayrollDiscrepancyResolveRequest, db: Session = Depends(get_db)):
    discrepancy = resolve_payroll_discrepancy(discrepancy_id, req.resolution_note, db, resolved_by=req.resolved_by)
    return {"message": "", "data": discrepancy, "status": True}


@router.post("/adjustment")
def create_adjustment(req: PayrollAdjustmentCreate, db: Session = Depends(get_db)):
    adjustment = add_payroll_adjustment(req, db)
    return {"message": "", "data": adjustment, "status": True}
