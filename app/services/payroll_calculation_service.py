import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, with_loader_criteria

from app.exceptions.base_exception import BadRequestException, ResourceNotFoundException
from app.models.attendance_payroll import (
    AttendanceDay,
    EmployeeFinancialTotal,
    EmployeeLedgerTransaction,
    EmployeePayroll,
    PayrollCalculationHistory,
    PayrollDiscrepancy,
    PayrollPeriod,
)
from app.models.employees import Employees
from app.services.policy_service import (
    get_employee_compensation,
    get_employee_holiday_dates,
    get_employee_schedule,
    get_or_create_payroll_policy,
    get_working_days,
    save_audit_log,
)


PERIOD_STATUS_OPEN = "open"
PERIOD_STATUS_LOCKED = "locked"
LEDGER_TYPES = {"payment", "bonus", "deduction"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utc_now().date()


def _decimal(value, default: str = "0.00") -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _minutes_between_times(start_value, end_value) -> int:
    start_dt = datetime.combine(date.today(), start_value)
    end_dt = datetime.combine(date.today(), end_value)
    return max(0, int((end_dt - start_dt).total_seconds() // 60))


def _get_period_bounds(target_date: date) -> tuple[date, date]:
    last_day = calendar.monthrange(target_date.year, target_date.month)[1]
    return date(target_date.year, target_date.month, 1), date(target_date.year, target_date.month, last_day)


def get_or_create_payroll_period_for_date(target_date: date, db: Session) -> PayrollPeriod:
    start_date, end_date = _get_period_bounds(target_date)
    period = db.scalar(
        select(PayrollPeriod).where(
            PayrollPeriod.start_date == start_date,
            PayrollPeriod.end_date == end_date,
        )
    )
    if period:
        return period
    period = PayrollPeriod(
        name=target_date.strftime("%B %Y payroll"),
        start_date=start_date,
        end_date=end_date,
        status=PERIOD_STATUS_OPEN,
    )
    db.add(period)
    db.flush()
    return period


def _require_period_open(period: PayrollPeriod) -> None:
    if period.status == PERIOD_STATUS_LOCKED:
        raise BadRequestException("Payroll period is locked; attendance cannot be changed in this period")


def assert_period_open_for_date(work_date: date, db: Session) -> PayrollPeriod:
    period = get_or_create_payroll_period_for_date(work_date, db)
    _require_period_open(period)
    return period


def assert_periods_open_for_range(start_date: date, end_date: date, db: Session) -> None:
    cursor = date(start_date.year, start_date.month, 1)
    final = date(end_date.year, end_date.month, 1)
    while cursor <= final:
        period = get_or_create_payroll_period_for_date(cursor, db)
        _require_period_open(period)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)


def _get_employee_payroll(employee_id: int, payroll_period_id: int, db: Session) -> EmployeePayroll:
    payroll = db.scalar(
        select(EmployeePayroll).where(
            EmployeePayroll.employee_id == employee_id,
            EmployeePayroll.payroll_period_id == payroll_period_id,
        )
    )
    if payroll:
        return payroll
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")
    compensation = get_employee_compensation(employee_id, period.end_date, db)
    payroll = EmployeePayroll(
        payroll_period_id=payroll_period_id,
        employee_id=employee_id,
        salary_type=compensation.salary_type,
        status="draft",
    )
    db.add(payroll)
    db.flush()
    return payroll


def _load_period_attendance(employee_id: int, period: PayrollPeriod, db: Session) -> list[AttendanceDay]:
    return db.scalars(
        select(AttendanceDay)
        .where(
            AttendanceDay.employee_id == employee_id,
            AttendanceDay.work_date >= period.start_date,
            AttendanceDay.work_date <= period.end_date,
        )
        .order_by(AttendanceDay.work_date.asc())
    ).all()


def _attendance_summary(days: list[AttendanceDay]) -> dict[str, int]:
    return {
        "actual_work_minutes": sum(int(day.actual_work_minutes or 0) for day in days),
        "normal_paid_minutes": sum(int(day.normal_paid_minutes or 0) for day in days),
        "overtime_minutes": sum(int(day.overtime_minutes or 0) for day in days),
        "late_minutes": sum(int(day.late_minutes or 0) for day in days),
        "early_leave_minutes": sum(int(day.early_leave_minutes or 0) for day in days),
        "absence_minutes": sum(int(day.absence_minutes or 0) for day in days),
        "unpaid_minutes": sum(int(day.unpaid_minutes or 0) for day in days),
        "absence_days": sum(1 for day in days if day.status == "absent"),
        "paid_vacation_days": sum(1 for day in days if day.status == "paid_vacation"),
        "unpaid_vacation_days": sum(1 for day in days if day.status == "unpaid_vacation"),
        "incomplete_days": sum(1 for day in days if day.status == "incomplete"),
        "review_days": sum(1 for day in days if day.review_status == "needs_review"),
    }


def _period_cutoff(period: PayrollPeriod) -> date:
    return period.end_date if period.status == PERIOD_STATUS_LOCKED else min(period.end_date, _today())


def _calculate_amounts(payroll: EmployeePayroll, period: PayrollPeriod, days: list[AttendanceDay], db: Session) -> dict:
    policy = get_or_create_payroll_policy(db)
    compensation = get_employee_compensation(payroll.employee_id, period.end_date, db)
    schedule = get_employee_schedule(payroll.employee_id, period.start_date, db)
    holidays = get_employee_holiday_dates(payroll.employee_id, period.start_date, period.end_date, db)
    expected_day_minutes = max(
        1,
        _minutes_between_times(schedule.start_time, schedule.end_time) - int(schedule.break_minutes or 0),
    )
    summary = _attendance_summary(days)
    cutoff = _period_cutoff(period)
    accrued_days = [day for day in days if day.work_date <= cutoff]
    accrued_summary = _attendance_summary(accrued_days)
    missing_workdays = [
        day
        for day in get_working_days(period.start_date, cutoff, schedule, holidays)
        if day not in {item.work_date for item in accrued_days}
    ]
    missing_minutes = len(missing_workdays) * expected_day_minutes

    salary_type = compensation.salary_type
    base_salary = _money(_decimal(compensation.base_monthly_salary))
    if salary_type == "monthly":
        basis_days = max(1, calendar.monthrange(period.start_date.year, period.start_date.month)[1])
        period_basis_days = max(0, (cutoff - period.start_date).days + 1)
        minute_rate = base_salary / Decimal(basis_days * expected_day_minutes)
        normal_amount = _money(min(base_salary, minute_rate * Decimal(period_basis_days * expected_day_minutes)))
    elif salary_type == "daily":
        minute_rate = _decimal(compensation.daily_rate) / Decimal(expected_day_minutes)
        normal_amount = _money(minute_rate * Decimal(accrued_summary["normal_paid_minutes"]))
        base_salary = _money(_decimal(compensation.daily_rate) * Decimal(max(1, len(missing_workdays) + len(accrued_days))))
    else:
        minute_rate = _decimal(compensation.hourly_rate) / Decimal("60")
        normal_amount = _money(minute_rate * Decimal(accrued_summary["normal_paid_minutes"]))
        base_salary = _money(normal_amount)

    overtime_rate = _decimal(compensation.overtime_rate)
    overtime_minutes = accrued_summary["overtime_minutes"]
    payable_overtime_minutes = overtime_minutes if overtime_minutes >= int(policy.minimum_overtime_minutes or 0) else 0
    overtime_amount = _money((overtime_rate / Decimal("60")) * Decimal(payable_overtime_minutes)) if policy.overtime_enabled else Decimal("0.00")
    attendance_deduction_amount = _money(min(base_salary, minute_rate * Decimal(accrued_summary["unpaid_minutes"] + missing_minutes)))
    unpaid_vacation_deduction = _money(minute_rate * Decimal(sum(int(day.expected_work_minutes or 0) for day in accrued_days if day.status == "unpaid_vacation")))
    gross_salary = _money(normal_amount + overtime_amount)
    net_salary = _money(gross_salary - attendance_deduction_amount)
    needs_review_reasons: list[str] = []
    if missing_workdays:
        needs_review_reasons.append(f"{len(missing_workdays)} missing attendance day(s)")
    if summary["review_days"]:
        needs_review_reasons.append(f"{summary['review_days']} attendance day(s) need review")
    if summary["incomplete_days"]:
        needs_review_reasons.append(f"{summary['incomplete_days']} incomplete attendance day(s)")

    calculation_data_json = {
        **summary,
        "effective_cutoff_date": cutoff.isoformat(),
        "expected_day_minutes": expected_day_minutes,
        "missing_attendance_days": len(missing_workdays),
        "missing_workday_minutes": missing_minutes,
        "payable_overtime_minutes": payable_overtime_minutes,
        "normal_amount": str(normal_amount),
        "overtime_amount": str(overtime_amount),
        "attendance_deduction": str(attendance_deduction_amount),
        "unpaid_vacation_deduction": str(unpaid_vacation_deduction),
        "gross_salary": str(gross_salary),
        "net_salary": str(net_salary),
        "total_amount": str(net_salary),
        "needs_review_reasons": needs_review_reasons,
    }
    return {
        "salary_type": salary_type,
        "base_salary": base_salary,
        "normal_amount": normal_amount,
        "overtime_amount": overtime_amount,
        "attendance_deduction_amount": attendance_deduction_amount,
        "unpaid_vacation_deduction": unpaid_vacation_deduction,
        "gross_salary": gross_salary,
        "net_salary": net_salary,
        "total_amount": net_salary,
        "status": "needs_review" if needs_review_reasons else "draft",
        "calculation_data_json": calculation_data_json,
        "needs_review_reason": "; ".join(needs_review_reasons) or None,
    }


def create_payroll_history_snapshot(
    payroll: EmployeePayroll,
    *,
    old_gross_salary: Decimal | None = None,
    old_net_salary: Decimal | None = None,
    reason: str,
    calculation_data_json: dict,
    db: Session,
    created_by: int | None = None,
):
    history = PayrollCalculationHistory(
        employee_payroll_id=payroll.id,
        payroll_period_id=payroll.payroll_period_id,
        employee_id=payroll.employee_id,
        old_gross_salary=old_gross_salary,
        new_gross_salary=payroll.gross_salary,
        old_net_salary=old_net_salary,
        new_net_salary=payroll.net_salary,
        reason=reason,
        calculation_data_json=calculation_data_json,
        created_by=created_by,
    )
    db.add(history)
    db.flush()
    return history


def calculate_employee_payroll(
    employee_id: int,
    payroll_period_id: int,
    db: Session,
    reason: str = "manual_recalculation",
    created_by: int | None = None,
    force_history: bool = False,
):
    employee = db.get(Employees, employee_id)
    if not employee or employee.deleted_at is not None:
        raise ResourceNotFoundException("Employee")
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")
    _require_period_open(period)

    payroll = _get_employee_payroll(employee_id, payroll_period_id, db)
    old_gross_salary = _decimal(payroll.gross_salary)
    old_net_salary = _decimal(payroll.net_salary)
    results = _calculate_amounts(payroll, period, _load_period_attendance(employee_id, period, db), db)
    calculation_data_json = results.pop("calculation_data_json")
    needs_review_reason = results.pop("needs_review_reason")
    for field_name, value in results.items():
        setattr(payroll, field_name, value)
    payroll.calculated_at = _utc_now()
    db.add(payroll)
    db.flush()
    if force_history or old_net_salary != payroll.net_salary or old_gross_salary != payroll.gross_salary:
        create_payroll_history_snapshot(
            payroll,
            old_gross_salary=old_gross_salary,
            old_net_salary=old_net_salary,
            reason=reason,
            calculation_data_json=calculation_data_json,
            db=db,
            created_by=created_by,
        )
    payroll.calculation_data_json = calculation_data_json
    payroll.needs_review_reason = needs_review_reason
    recalculate_employee_financial_total(employee_id, db)
    save_audit_log(
        db,
        action="payroll_recalculated",
        entity_type="EmployeePayroll",
        entity_id=payroll.id,
        old_data_json={"gross_salary": str(old_gross_salary), "net_salary": str(old_net_salary)},
        new_data_json={"gross_salary": str(payroll.gross_salary), "net_salary": str(payroll.net_salary), "reason": reason},
        user_id=created_by,
    )
    return payroll


def recalculate_payroll_period(payroll_period_id: int, db: Session, created_by: int | None = None):
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")
    _require_period_open(period)
    employees = db.scalars(select(Employees).where(Employees.is_active.is_(True), Employees.deleted_at.is_(None))).all()
    payrolls = [
        calculate_employee_payroll(employee.id, period.id, db, reason="period_recalculation", created_by=created_by)
        for employee in employees
    ]
    db.commit()
    for payroll in payrolls:
        db.refresh(payroll)
        _hydrate_payroll_snapshot(payroll, db)
    return payrolls


def _latest_payroll_snapshot(employee_payroll_id: int, db: Session) -> dict:
    history = db.scalar(
        select(PayrollCalculationHistory.calculation_data_json)
        .where(PayrollCalculationHistory.employee_payroll_id == employee_payroll_id)
        .order_by(PayrollCalculationHistory.created_at.desc(), PayrollCalculationHistory.id.desc())
    )
    return history or {}


def _hydrate_payroll_snapshot(payroll: EmployeePayroll, db: Session) -> EmployeePayroll:
    snapshot = _latest_payroll_snapshot(payroll.id, db)
    payroll.calculation_data_json = snapshot
    payroll.needs_review_reason = "; ".join(snapshot.get("needs_review_reasons") or []) or None
    return payroll


def get_employee_payroll_by_period(employee_id: int, period_id: int, db: Session):
    payroll = db.scalar(
        select(EmployeePayroll).where(EmployeePayroll.employee_id == employee_id, EmployeePayroll.payroll_period_id == period_id)
    )
    if not payroll:
        payroll = calculate_employee_payroll(employee_id, period_id, db)
        db.commit()
        db.refresh(payroll)
    return _hydrate_payroll_snapshot(payroll, db)


def get_payroll_period(period_id: int, db: Session, *, include_archived: bool = False):
    options = [selectinload(PayrollPeriod.payrolls).selectinload(EmployeePayroll.employee)]
    if not include_archived:
        options.append(
            with_loader_criteria(
                EmployeePayroll,
                EmployeePayroll.employee.has(Employees.deleted_at.is_(None)),
                include_aliases=True,
            )
        )
    period = db.scalar(select(PayrollPeriod).options(*options).where(PayrollPeriod.id == period_id))
    if not period:
        raise ResourceNotFoundException("Payroll period")
    for payroll in period.payrolls:
        _hydrate_payroll_snapshot(payroll, db)
    return period


def list_payroll_periods(db: Session):
    return db.scalars(select(PayrollPeriod).order_by(PayrollPeriod.start_date.desc(), PayrollPeriod.id.desc())).all()


def _period_ledger_date(period: PayrollPeriod) -> datetime:
    return datetime.combine(period.start_date, time(23, 59, 59), tzinfo=timezone.utc)


def _ledger_sort_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _period_description(payroll: EmployeePayroll, snapshot: dict | None = None) -> str:
    snapshot = snapshot or {}
    issues = []
    if int(snapshot.get("missing_attendance_days") or 0):
        issues.append(f"{snapshot['missing_attendance_days']} missing attendance day(s)")
    if int(snapshot.get("review_days") or 0):
        issues.append(f"{snapshot['review_days']} day(s) need review")
    if int(snapshot.get("incomplete_days") or 0):
        issues.append(f"{snapshot['incomplete_days']} incomplete day(s)")
    issue_text = ", ".join(issues) if issues else "Attendance calculated"
    period = payroll.payroll_period
    return f"{period.start_date.isoformat()} to {period.end_date.isoformat()}: {issue_text}"


def _transaction_balance(row: EmployeeLedgerTransaction) -> Decimal:
    amount = _money(_decimal(row.amount))
    if row.type == "deduction":
        return -abs(amount)
    return amount


def _period_balance(payroll: EmployeePayroll) -> Decimal:
    return _money(_decimal(payroll.total_amount, default=str(_decimal(payroll.net_salary))))


def _employee_ledger_entries(employee_id: int, db: Session) -> list[dict]:
    payrolls = db.scalars(
        select(EmployeePayroll)
        .join(PayrollPeriod, EmployeePayroll.payroll_period_id == PayrollPeriod.id)
        .options(selectinload(EmployeePayroll.payroll_period))
        .where(EmployeePayroll.employee_id == employee_id)
        .order_by(PayrollPeriod.start_date.asc(), EmployeePayroll.id.asc())
    ).all()
    transactions = db.scalars(
        select(EmployeeLedgerTransaction)
        .where(EmployeeLedgerTransaction.employee_id == employee_id)
        .order_by(EmployeeLedgerTransaction.transaction_date.asc(), EmployeeLedgerTransaction.id.asc())
    ).all()
    entries: list[dict] = []
    for payroll in payrolls:
        snapshot = _latest_payroll_snapshot(payroll.id, db)
        entries.append(
            {
                "sort_date": _period_ledger_date(payroll.payroll_period),
                "sort_id": payroll.id,
                "id": f"period-{payroll.id}",
                "source_id": payroll.id,
                "employee_id": employee_id,
                "type": "period",
                "date": _period_ledger_date(payroll.payroll_period),
                "status": payroll.payroll_period.status,
                "description": _period_description(payroll, snapshot),
                "balance": _period_balance(payroll),
                "period_id": payroll.payroll_period_id,
                "details": {
                    "period_name": payroll.payroll_period.name,
                    "period_start_date": payroll.payroll_period.start_date.isoformat(),
                    "period_end_date": payroll.payroll_period.end_date.isoformat(),
                    "locked_at": payroll.payroll_period.locked_at.isoformat() if payroll.payroll_period.locked_at else None,
                    **_serialize_employee_payroll(payroll),
                    "calculation_data_json": snapshot,
                    "needs_review_reason": "; ".join(snapshot.get("needs_review_reasons") or []) or None,
                },
            }
        )
    for row in transactions:
        entries.append(
            {
                "sort_date": row.transaction_date,
                "sort_id": row.id,
                "id": f"transaction-{row.id}",
                "source_id": row.id,
                "employee_id": employee_id,
                "type": row.type,
                "date": row.transaction_date,
                "status": row.status,
                "description": row.description,
                "balance": _transaction_balance(row),
                "period_id": None,
                "details": {},
            }
        )
    entries.sort(key=lambda item: (_ledger_sort_datetime(item["sort_date"]), item["sort_id"]))
    running = Decimal("0.00")
    for entry in entries:
        running = _money(running + _decimal(entry["balance"]))
        entry["running_total"] = running
        entry.pop("sort_date", None)
        entry.pop("sort_id", None)
    return entries


def recalculate_employee_financial_total(employee_id: int, db: Session) -> EmployeeFinancialTotal:
    total = Decimal("0.00")
    for entry in _employee_ledger_entries(employee_id, db):
        total = _decimal(entry["running_total"])
    row = db.get(EmployeeFinancialTotal, employee_id)
    if not row:
        row = EmployeeFinancialTotal(employee_id=employee_id)
    row.total_balance = _money(total)
    row.recalculated_at = _utc_now()
    db.add(row)
    db.flush()
    return row


def get_employee_financial_total(employee_id: int, db: Session) -> EmployeeFinancialTotal:
    employee = db.get(Employees, employee_id)
    if not employee or employee.deleted_at is not None:
        raise ResourceNotFoundException("Employee")
    return recalculate_employee_financial_total(employee_id, db)


def get_employee_ledger(
    employee_id: int,
    db: Session,
    *,
    page: int = 1,
    page_size: int = 20,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    employee = db.get(Employees, employee_id)
    if not employee or employee.deleted_at is not None:
        raise ResourceNotFoundException("Employee")
    total = recalculate_employee_financial_total(employee_id, db)
    entries = _employee_ledger_entries(employee_id, db)
    if start_date is not None:
        entries = [entry for entry in entries if entry["date"].date() >= start_date]
    if end_date is not None:
        entries = [entry for entry in entries if entry["date"].date() <= end_date]
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    total_records = len(entries)
    total_pages = (total_records + safe_page_size - 1) // safe_page_size if total_records else 0
    offset = (safe_page - 1) * safe_page_size if total_records else 0
    return {
        "employee_id": employee_id,
        "employee_name": employee.fullname,
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "items": entries[offset : offset + safe_page_size],
    }


def create_ledger_transaction(payload, db: Session):
    employee = db.get(Employees, payload.employee_id)
    if not employee or employee.deleted_at is not None:
        raise ResourceNotFoundException("Employee")
    row = EmployeeLedgerTransaction(
        employee_id=payload.employee_id,
        type=payload.type,
        transaction_date=payload.transaction_date,
        amount=_money(_decimal(payload.amount)),
        description=payload.description,
        created_by=payload.created_by,
    )
    db.add(row)
    db.flush()
    recalculate_employee_financial_total(payload.employee_id, db)
    db.commit()
    db.refresh(row)
    return row


def update_ledger_transaction(transaction_id: int, payload, db: Session, updated_by: int | None = None):
    row = db.get(EmployeeLedgerTransaction, transaction_id)
    if not row:
        raise ResourceNotFoundException("Ledger transaction")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key == "amount" and value is not None:
            value = _money(_decimal(value))
        if value is not None:
            setattr(row, key, value)
    row.status = "changed"
    row.updated_by = updated_by
    row.updated_at = _utc_now()
    db.add(row)
    db.flush()
    recalculate_employee_financial_total(row.employee_id, db)
    db.commit()
    db.refresh(row)
    return row


def delete_ledger_transaction(transaction_id: int, db: Session, deleted_by: int | None = None):
    row = db.get(EmployeeLedgerTransaction, transaction_id)
    if not row:
        raise ResourceNotFoundException("Ledger transaction")
    employee_id = row.employee_id
    db.delete(row)
    db.flush()
    recalculate_employee_financial_total(employee_id, db)
    db.commit()
    return {"deleted": True, "id": transaction_id}


def lock_payroll_period(period_id: int, db: Session, locked_by: int | None = None):
    period = db.get(PayrollPeriod, period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")
    period.status = PERIOD_STATUS_LOCKED
    period.locked_at = _utc_now()
    period.locked_by = locked_by
    days = db.scalars(
        select(AttendanceDay).where(AttendanceDay.work_date >= period.start_date, AttendanceDay.work_date <= period.end_date)
    ).all()
    for day in days:
        day.review_status = "locked"
        day.locked_at = period.locked_at
        day.reviewed_at = period.locked_at
        day.reviewed_by = locked_by
        db.add(day)
    db.add(period)
    db.flush()
    for payroll in db.scalars(select(EmployeePayroll).where(EmployeePayroll.payroll_period_id == period.id)).all():
        recalculate_employee_financial_total(payroll.employee_id, db)
    db.commit()
    db.refresh(period)
    return period


def unlock_payroll_period(period_id: int, db: Session, unlocked_by: int | None = None):
    period = db.get(PayrollPeriod, period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")
    period.status = PERIOD_STATUS_OPEN
    period.locked_at = None
    period.locked_by = None
    days = db.scalars(
        select(AttendanceDay).where(AttendanceDay.work_date >= period.start_date, AttendanceDay.work_date <= period.end_date)
    ).all()
    for day in days:
        if day.review_status == "locked":
            day.review_status = "approved" if day.reviewed_at else "draft"
        day.locked_at = None
        db.add(day)
    db.add(period)
    db.flush()
    for payroll in db.scalars(select(EmployeePayroll).where(EmployeePayroll.payroll_period_id == period.id)).all():
        calculate_employee_payroll(payroll.employee_id, period.id, db, reason="period_unlocked", created_by=unlocked_by)
    db.commit()
    db.refresh(period)
    return period


def get_payroll_balance_report(
    db: Session,
    period_id: int | None = None,
    employee_id: int | None = None,
    *,
    include_archived: bool = False,
):
    query = select(EmployeePayroll).join(Employees, EmployeePayroll.employee_id == Employees.id).options(selectinload(EmployeePayroll.employee))
    if not include_archived:
        query = query.where(Employees.deleted_at.is_(None))
    if period_id is not None:
        query = query.where(EmployeePayroll.payroll_period_id == period_id)
    if employee_id is not None:
        query = query.where(EmployeePayroll.employee_id == employee_id)
    payrolls = db.scalars(query.order_by(EmployeePayroll.employee_id.asc(), EmployeePayroll.payroll_period_id.asc())).all()
    employees: dict[int, dict] = {}
    total_amount = Decimal("0.00")
    for payroll in payrolls:
        row_total = _period_balance(payroll)
        total_amount += row_total
        total = recalculate_employee_financial_total(payroll.employee_id, db)
        employee_name = getattr(payroll.employee, "fullname", None) or f"Employee #{payroll.employee_id}"
        employee_row = employees.setdefault(
            payroll.employee_id,
            {
                "employee_id": payroll.employee_id,
                "employee_name": employee_name,
                "total_amount": Decimal("0.00"),
                "payroll_count": 0,
                "ledger_balance": total.total_balance,
            },
        )
        employee_row["total_amount"] += row_total
        employee_row["payroll_count"] += 1
        employee_row["ledger_balance"] = total.total_balance
    company_owes_employees = _money(sum((row["ledger_balance"] for row in employees.values() if row["ledger_balance"] > 0), Decimal("0.00")))
    employees_owe_company = _money(sum((abs(row["ledger_balance"]) for row in employees.values() if row["ledger_balance"] < 0), Decimal("0.00")))
    return {
        "period_id": period_id,
        "total_amount": _money(total_amount),
        "company_owes_employees": company_owes_employees,
        "employees_owe_company": employees_owe_company,
        "employees": [
            {**row, "total_amount": _money(row["total_amount"]), "ledger_balance": _money(row["ledger_balance"])}
            for row in sorted(employees.values(), key=lambda item: (item["employee_name"].lower(), item["employee_id"]))
        ],
    }


def get_employee_payroll_history(employee_id: int, db: Session, page: int = 1, page_size: int = 20):
    employee = db.get(Employees, employee_id)
    if not employee or employee.deleted_at is not None:
        raise ResourceNotFoundException("Employee")
    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))
    total_records = int(db.scalar(select(func.count(EmployeePayroll.id)).where(EmployeePayroll.employee_id == employee_id)) or 0)
    total_pages = (total_records + safe_page_size - 1) // safe_page_size if total_records else 0
    payrolls = db.scalars(
        select(EmployeePayroll)
        .join(PayrollPeriod, EmployeePayroll.payroll_period_id == PayrollPeriod.id)
        .options(selectinload(EmployeePayroll.payroll_period))
        .where(EmployeePayroll.employee_id == employee_id)
        .order_by(PayrollPeriod.start_date.desc(), EmployeePayroll.id.desc())
        .offset((safe_page - 1) * safe_page_size if total_records else 0)
        .limit(safe_page_size)
    ).all()
    items = []
    for payroll in payrolls:
        _hydrate_payroll_snapshot(payroll, db)
        items.append(
            {
                **_serialize_employee_payroll(payroll),
                "period_name": payroll.payroll_period.name,
                "period_start_date": payroll.payroll_period.start_date,
                "period_end_date": payroll.payroll_period.end_date,
            }
        )
    ledger_total = recalculate_employee_financial_total(employee_id, db).total_balance
    return {
        "employee_id": employee.id,
        "employee_name": employee.fullname,
        "employee_status": employee.status,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "summary": {
            "net_salary_total": _money(sum((_decimal(item.net_salary) for item in payrolls), Decimal("0.00"))),
            "payable_total": _money(sum((_decimal(item.total_amount) for item in payrolls), Decimal("0.00"))),
            "ledger_total": _money(ledger_total),
            "payroll_count": total_records,
        },
        "items": items,
    }


def _serialize_employee_payroll(payroll: EmployeePayroll) -> dict:
    return {
        "id": payroll.id,
        "payroll_period_id": payroll.payroll_period_id,
        "employee_id": payroll.employee_id,
        "salary_type": payroll.salary_type,
        "base_salary": _money(_decimal(payroll.base_salary)),
        "normal_amount": _money(_decimal(payroll.normal_amount)),
        "overtime_amount": _money(_decimal(payroll.overtime_amount)),
        "attendance_deduction_amount": _money(_decimal(payroll.attendance_deduction_amount)),
        "unpaid_vacation_deduction": _money(_decimal(payroll.unpaid_vacation_deduction)),
        "gross_salary": _money(_decimal(payroll.gross_salary)),
        "net_salary": _money(_decimal(payroll.net_salary)),
        "total_amount": _money(_decimal(payroll.total_amount)),
        "status": payroll.status,
        "calculated_at": payroll.calculated_at,
        "notes": payroll.notes,
        "calculation_data_json": getattr(payroll, "calculation_data_json", {}) or {},
        "needs_review_reason": getattr(payroll, "needs_review_reason", None),
    }


def get_payroll_history(employee_payroll_id: int, db: Session):
    return db.scalars(
        select(PayrollCalculationHistory)
        .where(PayrollCalculationHistory.employee_payroll_id == employee_payroll_id)
        .order_by(PayrollCalculationHistory.created_at.desc(), PayrollCalculationHistory.id.desc())
    ).all()


def get_payroll_discrepancies(period_id: int, db: Session, *, include_archived: bool = False):
    query = (
        select(PayrollDiscrepancy)
        .join(Employees, PayrollDiscrepancy.employee_id == Employees.id)
        .where(PayrollDiscrepancy.payroll_period_id == period_id)
    )
    if not include_archived:
        query = query.where(Employees.deleted_at.is_(None))
    return db.scalars(query.order_by(PayrollDiscrepancy.created_at.desc(), PayrollDiscrepancy.id.desc())).all()


def resolve_payroll_discrepancy(discrepancy_id: int, resolution_note: str, db: Session, resolved_by: int | None = None):
    discrepancy = db.get(PayrollDiscrepancy, discrepancy_id)
    if not discrepancy:
        raise ResourceNotFoundException("Payroll discrepancy")
    discrepancy.status = "resolved"
    discrepancy.resolution_note = resolution_note
    discrepancy.resolved_by = resolved_by
    discrepancy.resolved_at = _utc_now()
    db.commit()
    db.refresh(discrepancy)
    return discrepancy


def sync_payroll_with_attendance_context(employee_id: int, work_date: date, db: Session, trigger_reason: str = "attendance_change") -> dict[str, object]:
    period = get_or_create_payroll_period_for_date(work_date, db)
    _require_period_open(period)
    payroll = calculate_employee_payroll(employee_id, period.id, db, reason=trigger_reason, force_history=trigger_reason != "attendance_review")
    return {"status": "recalculated", "payroll_id": payroll.id, "payroll_status": payroll.status, "payroll_period_id": period.id}


def sync_payroll_after_attendance_delete(employee_id: int, work_date: date, db: Session, deleted_by: int | None = None) -> dict[str, object]:
    return sync_payroll_with_attendance_context(employee_id, work_date, db, trigger_reason="attendance_delete")


def sync_payroll_with_attendance_review(employee_id: int, work_date: date, db: Session) -> dict[str, object]:
    return sync_payroll_with_attendance_context(employee_id, work_date, db, trigger_reason="attendance_review")


def sync_payroll_with_attendance_day(day: AttendanceDay, db: Session, trigger_reason: str = "attendance_change"):
    result = sync_payroll_with_attendance_context(day.employee_id, day.work_date, db, trigger_reason=trigger_reason)
    payroll_id = result.get("payroll_id")
    return db.get(EmployeePayroll, payroll_id) if payroll_id else None


def sync_vacation_with_payroll(employee_id: int, start_date: date, end_date: date, db: Session, reason: str):
    current = start_date
    from app.services.attendance_calculation_service import calculate_attendance_day

    while current <= end_date:
        calculate_attendance_day(employee_id, current, db, trigger_reason=reason)
        current += timedelta(days=1)


def reconcile_existing_payrolls_for_settings_change(db: Session, *, reason: str = "settings_change", created_by: int | None = None):
    payrolls = db.scalars(select(EmployeePayroll).join(PayrollPeriod).where(PayrollPeriod.status == PERIOD_STATUS_OPEN)).all()
    count = 0
    for payroll in payrolls:
        calculate_employee_payroll(payroll.employee_id, payroll.payroll_period_id, db, reason=reason, created_by=created_by)
        count += 1
    db.commit()
    return {"recalculated": count, "skipped": 0, "discrepancies": 0}


def reconcile_existing_payrolls_for_employee_compensation_change(employee_id: int, db: Session, *, reason: str = "employee_compensation_updated", created_by: int | None = None):
    payrolls = db.scalars(select(EmployeePayroll).join(PayrollPeriod).where(EmployeePayroll.employee_id == employee_id, PayrollPeriod.status == PERIOD_STATUS_OPEN)).all()
    for payroll in payrolls:
        calculate_employee_payroll(employee_id, payroll.payroll_period_id, db, reason=reason, created_by=created_by)
    return {"recalculated": len(payrolls), "skipped": 0, "discrepancies": 0}


def reconcile_existing_payrolls_for_employee_due_change(*args, **kwargs):
    return {"recalculated": 0, "skipped": 0, "discrepancies": 0}
