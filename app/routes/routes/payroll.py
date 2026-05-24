from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_permissions, require_self_or_permission
from app.models.auth import User
from app.schemas.attendance_payroll import (
    LedgerTransactionCreate,
    LedgerTransactionUpdate,
    PeriodLockRequest,
    PayrollDiscrepancyResolveRequest,
)
from app.services.payroll_calculation_service import (
    calculate_employee_payroll,
    create_ledger_transaction,
    delete_ledger_transaction,
    get_employee_financial_total,
    get_employee_ledger,
    get_employee_payroll_by_period,
    get_employee_payroll_history,
    get_payroll_balance_report,
    get_payroll_discrepancies,
    get_payroll_history,
    get_payroll_period,
    list_payroll_periods,
    lock_payroll_period,
    recalculate_payroll_period,
    resolve_payroll_discrepancy,
    unlock_payroll_period,
    update_ledger_transaction,
)


router = APIRouter()


@router.get("/periods")
def get_period_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    return api_success(list_payroll_periods(db))


@router.get("/period/{period_id}")
def get_period(
    period_id: int,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    return api_success(get_payroll_period(period_id, db, include_archived=include_archived))


@router.post("/period/{period_id}/lock")
def lock_period(
    period_id: int,
    req: PeriodLockRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.lock")),
):
    return api_success(lock_payroll_period(period_id, db, locked_by=current_user.id))


@router.post("/period/{period_id}/unlock")
def unlock_period(
    period_id: int,
    req: PeriodLockRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.lock")),
):
    return api_success(unlock_payroll_period(period_id, db, unlocked_by=current_user.id))


@router.get("/report")
def get_balance_report(
    period_id: int | None = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    return api_success(get_payroll_balance_report(db, period_id=period_id, include_archived=include_archived))


@router.get("/employee-history/{employee_id}")
def get_employee_history(
    employee_id: int,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    return api_success(get_employee_payroll_history(employee_id, db, page=page, page_size=page_size))


@router.get("/employee/{employee_id}/{period_id}")
def get_employee_period_payroll(
    employee_id: int,
    period_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_permission("payroll.read_all")),
):
    return api_success(get_employee_payroll_by_period(employee_id, period_id, db))


@router.get("/ledger/{employee_id}")
def get_employee_ledger_view(
    employee_id: int,
    page: int = 1,
    page_size: int = 20,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_permission("payroll.read_all", employee_param="employee_id")),
):
    return api_success(get_employee_ledger(employee_id, db, page=page, page_size=page_size, start_date=start_date, end_date=end_date))


@router.get("/total/{employee_id}")
def get_employee_total_view(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_self_or_permission("payroll.read_all", employee_param="employee_id")),
):
    return api_success(get_employee_financial_total(employee_id, db))


@router.post("/transaction")
def create_transaction(
    req: LedgerTransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    req.created_by = current_user.id
    return api_success(create_ledger_transaction(req, db), status_code=201)


@router.put("/transaction/{transaction_id}")
def update_transaction(
    transaction_id: int,
    req: LedgerTransactionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    return api_success(update_ledger_transaction(transaction_id, req, db, updated_by=current_user.id))


@router.delete("/transaction/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    return api_success(delete_ledger_transaction(transaction_id, db, deleted_by=current_user.id))


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
    return api_success(recalculate_payroll_period(period_id, db, created_by=current_user.id))


@router.get("/history/{employee_payroll_id}")
def get_history(
    employee_payroll_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    return api_success(get_payroll_history(employee_payroll_id, db))


@router.get("/discrepancies/{period_id}")
def get_discrepancy_list(
    period_id: int,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.read_all")),
):
    return api_success(get_payroll_discrepancies(period_id, db, include_archived=include_archived))


@router.post("/discrepancy/{discrepancy_id}/resolve")
def resolve_discrepancy(
    discrepancy_id: int,
    req: PayrollDiscrepancyResolveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("payroll.adjust")),
):
    return api_success(resolve_payroll_discrepancy(discrepancy_id, req.resolution_note, db, resolved_by=current_user.id))
