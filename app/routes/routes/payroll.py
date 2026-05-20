from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_permissions, require_self_or_permission
from app.models.auth import User
from app.schemas.attendance_payroll import PayrollAdjustmentCreate, PayrollAdjustmentUpdate, PayrollDiscrepancyResolveRequest, PayrollPaymentRequest, PayrollReopenRequest
from app.services.payroll_calculation_service import (
    add_payroll_adjustment,
    approve_employee_payroll,
    get_employee_payroll_history,
    get_employee_payroll_by_period,
    delete_payroll_adjustment,
    get_payroll_adjustments,
    get_payroll_discrepancies,
    get_payroll_history,
    get_payroll_balance_report,
    get_payroll_period,
    list_payroll_periods,
    mark_employee_payroll_paid,
    reopen_locked_employee_payroll,
    recalculate_payroll_period,
    resolve_payroll_discrepancy,
    calculate_employee_payroll,
    unapprove_employee_payroll,
    update_payroll_adjustment,
)


router = APIRouter()


@router.get("/periods")
def get_period_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    periods = list_payroll_periods(db)
    return api_success(periods)


@router.get("/period/{period_id}")
def get_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    period = get_payroll_period(period_id, db)
    return api_success(period)


@router.get("/report")
def get_balance_report(
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    report = get_payroll_balance_report(db, period_id=period_id)
    return api_success(report)


@router.get("/employee-history/{employee_id}")
def get_employee_history(
    employee_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    report = get_employee_payroll_history(employee_id, db, page=page, page_size=page_size)
    return api_success(report)


@router.get("/employee/{employee_id}/{period_id}")
def get_employee_period_payroll(
    employee_id: int,
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_permission("payroll.read_all")),
):
    payroll = get_employee_payroll_by_period(employee_id, period_id, db)
    return api_success(payroll)


@router.post("/recalculate/{employee_id}/{period_id}")
def recalculate_employee_payroll(
    employee_id: int,
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.calculate")),
):
    payroll = calculate_employee_payroll(employee_id, period_id, db, reason="manual_recalculation", created_by=current_user.id, force_history=True)
    db.commit()
    db.refresh(payroll)
    return api_success(payroll)


@router.post("/recalculate-period/{period_id}")
def recalculate_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.calculate")),
):
    payrolls = recalculate_payroll_period(period_id, db, created_by=current_user.id)
    return api_success(payrolls)


@router.post("/approve/{employee_payroll_id}")
def approve_payroll(
    employee_payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.approve")),
):
    payroll = approve_employee_payroll(employee_payroll_id, db, approved_by=current_user.id)
    return api_success(payroll)


@router.post("/unapprove/{employee_payroll_id}")
def unapprove_payroll(
    employee_payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.approve")),
):
    payroll = unapprove_employee_payroll(employee_payroll_id, db, unapproved_by=current_user.id)
    return api_success(payroll)


@router.post("/mark-paid/{employee_payroll_id}")
def mark_paid(
    employee_payroll_id: int,
    req: PayrollPaymentRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.mark_paid")),
):
    payroll = mark_employee_payroll_paid(
        employee_payroll_id,
        db,
        paid_by=current_user.id,
        amount=req.amount if req else None,
        note=req.note if req else None,
    )
    return api_success(payroll)


@router.post("/reopen/{employee_payroll_id}")
def reopen_locked_payroll(
    employee_payroll_id: int,
    req: PayrollReopenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.mark_paid")),
):
    payroll = reopen_locked_employee_payroll(
        employee_payroll_id,
        db,
        reopened_by=current_user.id,
        reason=req.reason,
    )
    return api_success(payroll)


@router.get("/history/{employee_payroll_id}")
def get_history(
    employee_payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    history = get_payroll_history(employee_payroll_id, db)
    return api_success(history)


@router.get("/discrepancies/{period_id}")
def get_discrepancy_list(
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    discrepancies = get_payroll_discrepancies(period_id, db)
    return api_success(discrepancies)


@router.post("/discrepancy/{discrepancy_id}/resolve")
def resolve_discrepancy(
    discrepancy_id: int,
    req: PayrollDiscrepancyResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    discrepancy = resolve_payroll_discrepancy(discrepancy_id, req.resolution_note, db, resolved_by=current_user.id)
    return api_success(discrepancy)


@router.post("/adjustment")
def create_adjustment(
    req: PayrollAdjustmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    req.created_by = current_user.id
    adjustment = add_payroll_adjustment(req, db)
    return api_success(adjustment, status_code=201)


@router.get("/adjustments/{employee_payroll_id}")
def get_adjustments(
    employee_payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    adjustments = get_payroll_adjustments(employee_payroll_id, db)
    return api_success(adjustments)


@router.put("/adjustment/{adjustment_id}")
def update_adjustment(
    adjustment_id: int,
    req: PayrollAdjustmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    adjustment = update_payroll_adjustment(adjustment_id, req, db, updated_by=current_user.id)
    return api_success(adjustment)


@router.delete("/adjustment/{adjustment_id}")
def delete_adjustment(
    adjustment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    result = delete_payroll_adjustment(adjustment_id, db, deleted_by=current_user.id)
    return api_success(result)
