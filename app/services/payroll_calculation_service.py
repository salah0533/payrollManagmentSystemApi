import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session, selectinload, with_loader_criteria

from app.exceptions.base_exception import BadRequestException, ResourceNotFoundException
from app.models.attendance_payroll import (
    AttendanceDay,
    DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE,
    EmployeePayroll,
    MONTHLY_PAYROLL_CALCULATION_MODE_CALENDAR_DAYS,
    MONTHLY_PAYROLL_CALCULATION_MODE_WORKING_DAYS,
    PayrollAdjustment,
    PayrollCalculationHistory,
    PayrollDiscrepancy,
    PayrollPeriod,
)
from app.models.payments import Payments
from app.models.auth import User
from app.models.employees import Employees
from app.models.types.vacationStatus import VacationStatuses
from app.models.vacation import Vacation
from app.services.notification_service import NotificationService
from app.services.policy_service import (
    WEEKDAY_NAMES,
    get_employee_compensation,
    get_employee_holiday_dates,
    get_employee_schedule,
    get_or_create_payroll_policy,
    get_working_days,
    save_audit_log,
)


FINAL_PAYROLL_STATUSES = {"approved", "partially_paid", "paid", "locked"}
RECALCULABLE_PAYROLL_STATUSES = {"draft", "needs_review"}
MANAGED_DISCREPANCY_TYPES = {
    "missing_attendance",
    "missing_checkout",
    "missing_checkin",
    "attendance_requires_review",
    "vacation_overlap",
}
MONTHLY_RATE_REVIEW_MULTIPLIER = Decimal("2.00")
DUE_SETTLEMENT_ADJUSTMENT_TYPE = "due_settlement"


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


def _decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _minutes_between_times(start_value, end_value) -> int:
    start_dt = datetime.combine(date.today(), start_value)
    end_dt = datetime.combine(date.today(), end_value)
    return max(0, int((end_dt - start_dt).total_seconds() // 60))


def _divide_decimal(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == Decimal("0.00"):
        return Decimal("0.00")
    return numerator / denominator


def _int(value) -> int:
    return int(value or 0)


def _requires_minimum_attendance_review(day: AttendanceDay, minimum_auto_pay_minutes: int) -> bool:
    if minimum_auto_pay_minutes <= 0:
        return False
    if day.status not in {"present", "late"}:
        return False
    return 0 < _int(day.actual_work_minutes) < minimum_auto_pay_minutes


def _build_payroll_amount_snapshot(
    *,
    earned_net_salary: Decimal,
    payable_amount: Decimal | None = None,
    held_for_review_amount: Decimal | None = None,
) -> dict[str, Decimal]:
    earned = _money(earned_net_salary)
    payable = _money(payable_amount if payable_amount is not None else earned)
    approved_payable = earned
    held = _money(
        held_for_review_amount if held_for_review_amount is not None else max(Decimal("0.00"), approved_payable - payable)
    )
    if held > approved_payable:
        held = approved_payable
    return {
        "earned_net_salary": earned,
        "payable_amount": payable,
        "approved_payable_amount": approved_payable,
        "held_for_review_amount": held,
    }


def _apply_payroll_snapshot_fields(payroll: EmployeePayroll, calculation_data_json: dict | None) -> EmployeePayroll:
    snapshot = calculation_data_json or {}
    payroll.calculation_data_json = snapshot
    payroll.attendance_deduction_amount = _money(_decimal(snapshot.get("attendance_deduction")))
    payroll.manual_deduction_amount = _money(_decimal(snapshot.get("manual_deduction_amount")))
    payroll.late_penalty_amount = _money(_decimal(snapshot.get("late_penalty_amount"), default=str(_decimal(payroll.late_deduction_amount))))
    payroll.due_settlement_amount = _money(_decimal(snapshot.get("due_settlement_amount")))
    payroll.employee_due_balance = _money(_decimal(snapshot.get("employee_due_balance")))
    payroll.settled_due_amount = _money(_decimal(snapshot.get("settled_due_amount")))
    payroll.remaining_due_settlement_amount = _money(_decimal(snapshot.get("remaining_due_settlement_amount")))
    payroll.remaining_due_balance_after_settlement = _money(_decimal(snapshot.get("remaining_due_balance_after_settlement")))
    review_reasons = snapshot.get("needs_review_reasons") or []
    payroll.needs_review_reason = "; ".join(str(item) for item in review_reasons if str(item).strip()) or None
    return payroll


def _sum_adjustments_by_type(adjustments: list[PayrollAdjustment], adjustment_type: str) -> Decimal:
    return _money(
        sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == adjustment_type), Decimal("0.00"))
    )


def _get_due_settlement_paid_amount(due_settlement_amount: Decimal, paid_amount: Decimal) -> Decimal:
    if due_settlement_amount <= Decimal("0.00") or paid_amount <= Decimal("0.00"):
        return Decimal("0.00")
    return _money(min(_money(due_settlement_amount), _money(paid_amount)))


def _get_due_settlement_remaining_amount(due_settlement_amount: Decimal, paid_amount: Decimal) -> Decimal:
    return _money(max(Decimal("0.00"), _money(due_settlement_amount) - _get_due_settlement_paid_amount(due_settlement_amount, paid_amount)))


def _build_due_state_values(*, employee_due_balance: Decimal, due_settlement_amount: Decimal, paid_amount: Decimal) -> dict[str, Decimal]:
    current_due_balance = _money(employee_due_balance)
    due_settlement_total = _money(due_settlement_amount)
    settled_due_amount = _get_due_settlement_paid_amount(due_settlement_total, paid_amount)
    remaining_due_settlement_amount = _money(max(Decimal("0.00"), due_settlement_total - settled_due_amount))
    remaining_due_balance_after_settlement = _money(max(Decimal("0.00"), current_due_balance - remaining_due_settlement_amount))
    return {
        "employee_due_balance": current_due_balance,
        "due_settlement_amount": due_settlement_total,
        "settled_due_amount": settled_due_amount,
        "remaining_due_settlement_amount": remaining_due_settlement_amount,
        "remaining_due_balance_after_settlement": remaining_due_balance_after_settlement,
    }


def _get_employee_due_commitments(employee_id: int, db: Session, *, exclude_adjustment_id: int | None = None) -> dict[int, Decimal]:
    rows = db.scalars(
        select(PayrollAdjustment)
        .options(selectinload(PayrollAdjustment.employee_payroll))
        .where(
            PayrollAdjustment.employee_id == employee_id,
            PayrollAdjustment.adjustment_type == DUE_SETTLEMENT_ADJUSTMENT_TYPE,
        )
    ).all()

    totals_by_payroll: dict[int, Decimal] = {}
    paid_by_payroll: dict[int, Decimal] = {}
    for row in rows:
        if exclude_adjustment_id is not None and row.id == exclude_adjustment_id:
            continue
        payroll = row.employee_payroll or db.get(EmployeePayroll, row.employee_payroll_id)
        totals_by_payroll[row.employee_payroll_id] = totals_by_payroll.get(row.employee_payroll_id, Decimal("0.00")) + _decimal(row.amount)
        paid_by_payroll[row.employee_payroll_id] = _decimal(payroll.paid_amount) if payroll else Decimal("0.00")

    commitments: dict[int, Decimal] = {}
    for payroll_id, total_amount in totals_by_payroll.items():
        total_due_settlement = _money(total_amount)
        commitments[payroll_id] = _money(
            max(Decimal("0.00"), total_due_settlement - _get_due_settlement_paid_amount(total_due_settlement, paid_by_payroll.get(payroll_id, Decimal("0.00"))))
        )
    return commitments


def _validate_due_settlement_amount(
    *,
    payroll: EmployeePayroll,
    employee_id: int,
    amount: Decimal,
    db: Session,
    exclude_adjustment_id: int | None = None,
) -> None:
    employee = db.get(Employees, employee_id)
    if not employee or employee.deleted_at is not None:
        raise ResourceNotFoundException("Employee")

    commitments = _get_employee_due_commitments(employee_id, db, exclude_adjustment_id=exclude_adjustment_id)
    other_commitments = sum((value for payroll_id, value in commitments.items() if payroll_id != payroll.id), Decimal("0.00"))
    current_payroll_commitment = commitments.get(payroll.id, Decimal("0.00"))
    available_due_balance = _money(max(Decimal("0.00"), _money(_decimal(employee.dues)) - _money(other_commitments)))
    proposed_current_commitment = _money(current_payroll_commitment + _money(_decimal(amount)))

    if proposed_current_commitment > available_due_balance:
        raise BadRequestException(
            f"Due settlement amount cannot exceed the employee's available due balance of {available_due_balance}"
        )


def _apply_due_state_fields(payroll: EmployeePayroll, db: Session) -> EmployeePayroll:
    employee = payroll.employee if getattr(payroll, "employee", None) is not None else db.get(Employees, payroll.employee_id)
    adjustments = _load_adjustments(payroll.id, db)
    due_state = _build_due_state_values(
        employee_due_balance=_decimal(getattr(employee, "dues", 0)),
        due_settlement_amount=_sum_adjustments_by_type(adjustments, DUE_SETTLEMENT_ADJUSTMENT_TYPE),
        paid_amount=_decimal(payroll.paid_amount),
    )
    payroll.due_settlement_amount = due_state["due_settlement_amount"]
    payroll.employee_due_balance = due_state["employee_due_balance"]
    payroll.settled_due_amount = due_state["settled_due_amount"]
    payroll.remaining_due_settlement_amount = due_state["remaining_due_settlement_amount"]
    payroll.remaining_due_balance_after_settlement = due_state["remaining_due_balance_after_settlement"]
    return payroll


def _normalize_monthly_payroll_calculation_mode(value: str | None) -> str:
    normalized = (value or DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE).strip().lower()
    if normalized not in {
        MONTHLY_PAYROLL_CALCULATION_MODE_WORKING_DAYS,
        MONTHLY_PAYROLL_CALCULATION_MODE_CALENDAR_DAYS,
    }:
        return DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE
    return normalized


def _expand_date_range(start_date: date, end_date: date) -> list[date]:
    current = start_date
    result: list[date] = []
    while current <= end_date:
        result.append(current)
        current += timedelta(days=1)
    return result


def _resolve_monthly_rates(compensation, base_monthly_salary: Decimal, expected_day_minutes: int, basis_days_count: int) -> dict[str, object]:
    period_expected_minutes = basis_days_count * expected_day_minutes
    auto_daily_rate = _divide_decimal(base_monthly_salary, Decimal(basis_days_count)) if basis_days_count else Decimal("0.00")
    auto_hourly_rate = _divide_decimal(base_monthly_salary * Decimal("60"), Decimal(period_expected_minutes)) if period_expected_minutes else Decimal("0.00")
    auto_minute_rate = _divide_decimal(base_monthly_salary, Decimal(period_expected_minutes)) if period_expected_minutes else Decimal("0.00")

    configured_overtime_rate = _decimal_or_none(getattr(compensation, "overtime_rate", None))
    if configured_overtime_rate is not None and configured_overtime_rate <= Decimal("0.00"):
        configured_overtime_rate = None
    daily_override = _decimal_or_none(getattr(compensation, "daily_rate_override", None))
    hourly_override = _decimal_or_none(getattr(compensation, "hourly_rate_override", None))
    overtime_override = _decimal_or_none(getattr(compensation, "overtime_rate_override", None))
    late_override = _decimal_or_none(getattr(compensation, "late_deduction_rate_override", None))

    resolved_daily_rate = daily_override if daily_override is not None else auto_daily_rate
    resolved_hourly_rate = hourly_override if hourly_override is not None else auto_hourly_rate
    if daily_override is not None:
        resolved_minute_rate = _divide_decimal(daily_override, Decimal(expected_day_minutes))
        minute_rate_source = "override"
    elif hourly_override is not None:
        resolved_minute_rate = _divide_decimal(hourly_override, Decimal("60"))
        minute_rate_source = "override"
    else:
        resolved_minute_rate = auto_minute_rate
        minute_rate_source = "auto"

    resolved_late_deduction_rate = late_override if late_override is not None else auto_minute_rate
    if overtime_override is not None:
        resolved_overtime_rate = overtime_override
        overtime_rate_source = "override"
    elif configured_overtime_rate is not None:
        resolved_overtime_rate = configured_overtime_rate
        overtime_rate_source = "configured"
    else:
        resolved_overtime_rate = auto_hourly_rate
        overtime_rate_source = "auto"

    rate_sources = {
        "daily_rate": "override" if daily_override is not None else "auto",
        "hourly_rate": "override" if hourly_override is not None else "auto",
        "minute_rate": minute_rate_source,
        "late_deduction_rate": "override" if late_override is not None else "auto",
        "overtime_rate": overtime_rate_source,
    }

    review_warnings: list[str] = []
    review_candidates = [
        ("daily_rate", _decimal(compensation.daily_rate), auto_daily_rate),
        ("hourly_rate", _decimal(compensation.hourly_rate), auto_hourly_rate),
        ("daily_rate_override", daily_override, auto_daily_rate),
        ("hourly_rate_override", hourly_override, auto_hourly_rate),
    ]
    for field_name, configured_rate, auto_rate in review_candidates:
        if configured_rate is None or configured_rate <= Decimal("0.00") or auto_rate <= Decimal("0.00"):
            continue
        if configured_rate >= auto_rate * MONTHLY_RATE_REVIEW_MULTIPLIER:
            review_warnings.append(
                f"{field_name}={_money(configured_rate)} exceeds the auto-calculated rate {_money(auto_rate)} by at least {MONTHLY_RATE_REVIEW_MULTIPLIER}x"
            )

    return {
        "basis_days_count": basis_days_count,
        "period_expected_minutes": period_expected_minutes,
        "auto_daily_rate": auto_daily_rate,
        "auto_hourly_rate": auto_hourly_rate,
        "auto_minute_rate": auto_minute_rate,
        "resolved_daily_rate": resolved_daily_rate,
        "resolved_hourly_rate": resolved_hourly_rate,
        "resolved_minute_rate": resolved_minute_rate,
        "resolved_late_deduction_rate": resolved_late_deduction_rate,
        "resolved_overtime_rate": resolved_overtime_rate,
        "rate_sources": rate_sources,
        "rate_source": "override" if any(source == "override" for source in rate_sources.values()) else "auto",
        "review_warnings": review_warnings,
    }


def _sync_payroll_balance(payroll: EmployeePayroll, payable_amount: Decimal | None = None) -> None:
    if payable_amount is None:
        payable_amount = _decimal(payroll.total_amount, default=str(_decimal(payroll.net_salary)))
    payroll.total_amount = _money(_decimal(payable_amount))
    payroll.paid_amount = _money(_decimal(payroll.paid_amount))
    payroll.balance_amount = _money(payroll.total_amount - payroll.paid_amount)


def _set_attendance_review_status_for_period(employee_id: int, period: PayrollPeriod, review_status: str, db: Session) -> None:
    days = _load_period_attendance(employee_id, period, db)
    for day in days:
        day.review_status = review_status
        if review_status == "locked":
            day.reviewed_at = _utc_now()
            day.locked_at = _utc_now()
        elif review_status == "approved":
            day.reviewed_at = _utc_now()
            day.locked_at = None
        else:
            day.reviewed_at = None
            day.locked_at = None
        db.add(day)


def _get_employee_user_id(employee_id: int, db: Session) -> int | None:
    return db.scalar(select(User.id).where(User.employee_id == employee_id, User.deleted_at.is_(None)))


def _notify_payroll_backoffice_status(payroll: EmployeePayroll, db: Session) -> None:
    service = NotificationService(db)
    if payroll.status == "needs_review":
        notification_type = "payroll_needs_review"
        title = "Payroll needs review"
        message = f"Payroll for employee #{payroll.employee_id} in period #{payroll.payroll_period_id} needs review."
        title_key = "notifications.payroll_needs_review_title"
        message_key = "notifications.payroll_needs_review_message"
    elif payroll.status == "draft":
        notification_type = "payroll_draft_ready"
        title = "Payroll draft ready"
        message = f"Payroll draft for employee #{payroll.employee_id} in period #{payroll.payroll_period_id} is ready."
        title_key = "notifications.payroll_draft_ready_title"
        message_key = "notifications.payroll_draft_ready_message"
    else:
        return

    if service.notification_exists(
        notification_type=notification_type,
        entity_type="employee_payroll",
        entity_id=payroll.id,
    ):
        return
    service.notify_role(
        role_codes=["hr", "admin"],
        notification_type=notification_type,
        title=title,
        message=message,
        title_key=title_key,
        message_key=message_key,
        translation_params={
            "employee_name": f"Employee #{payroll.employee_id}",
            "period_id": payroll.payroll_period_id,
        },
        is_system_content=True,
        entity_type="employee_payroll",
        entity_id=payroll.id,
        priority="normal",
        skip_if_no_recipients=True,
    )


def _notify_employee_payroll_status(
    *,
    payroll: EmployeePayroll,
    notification_type: str,
    title: str,
    message: str,
    title_key: str | None,
    message_key: str | None,
    translation_params: dict | None,
    actor_user_id: int | None,
    db: Session,
) -> None:
    user_id = _get_employee_user_id(payroll.employee_id, db)
    if user_id is None:
        return
    service = NotificationService(db)
    if service.notification_exists(
        notification_type=notification_type,
        entity_type="employee_payroll",
        entity_id=payroll.id,
        user_id=user_id,
    ):
        return
    service.notify_user(
        user_id=user_id,
        notification_type=notification_type,
        title=title,
        message=message,
        title_key=title_key,
        message_key=message_key,
        translation_params=translation_params,
        is_system_content=bool(title_key or message_key),
        entity_type="employee_payroll",
        entity_id=payroll.id,
        actor_user_id=actor_user_id,
        priority="normal",
    )


def _get_period_bounds(target_date: date) -> tuple[date, date]:
    last_day = calendar.monthrange(target_date.year, target_date.month)[1]
    return date(target_date.year, target_date.month, 1), date(target_date.year, target_date.month, last_day)


def _get_effective_payroll_cutoff_date(period: PayrollPeriod) -> date:
    if period.status in FINAL_PAYROLL_STATUSES:
        return period.end_date
    return min(period.end_date, _today())


def _get_payroll_accrual_window(period: PayrollPeriod) -> tuple[date, date] | None:
    cutoff = _get_effective_payroll_cutoff_date(period)
    if cutoff < period.start_date:
        return None
    return period.start_date, cutoff


def _should_send_payroll_discrepancy_notification(period: PayrollPeriod) -> bool:
    return period.status in FINAL_PAYROLL_STATUSES or _today() > period.end_date


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
        status="draft",
    )
    db.add(period)
    db.flush()
    return period


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


def _attendance_summary(days: list[AttendanceDay], expected_day_minutes: int) -> dict[str, int]:
    summary = {
        "actual_work_minutes": 0,
        "normal_paid_minutes": 0,
        "overtime_minutes": 0,
        "late_minutes": 0,
        "early_leave_minutes": 0,
        "late_makeup_minutes": 0,
        "absence_minutes": 0,
        "unpaid_minutes": 0,
        "absence_days": 0,
        "paid_vacation_days": 0,
        "unpaid_vacation_days": 0,
    }

    for day in days:
        summary["actual_work_minutes"] += _int(day.actual_work_minutes)
        summary["normal_paid_minutes"] += day.normal_paid_minutes
        summary["overtime_minutes"] += day.overtime_minutes
        summary["late_minutes"] += day.late_minutes
        summary["early_leave_minutes"] += day.early_leave_minutes
        summary["late_makeup_minutes"] += day.late_makeup_minutes
        summary["absence_minutes"] += day.absence_minutes
        summary["unpaid_minutes"] += day.unpaid_minutes
        if expected_day_minutes:
            summary["absence_days"] += 1 if day.status == "absent" else 0
            summary["paid_vacation_days"] += 1 if day.status == "paid_vacation" else 0
            summary["unpaid_vacation_days"] += 1 if day.status == "unpaid_vacation" else 0

    return summary


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


def _load_adjustments(employee_payroll_id: int, db: Session) -> list[PayrollAdjustment]:
    return db.scalars(
        select(PayrollAdjustment)
        .where(PayrollAdjustment.employee_payroll_id == employee_payroll_id)
        .order_by(PayrollAdjustment.created_at.asc(), PayrollAdjustment.id.asc())
    ).all()


def calculate_monthly_employee_payroll(payroll: EmployeePayroll, period: PayrollPeriod, days: list[AttendanceDay], db: Session):
    policy = get_or_create_payroll_policy(db)
    monthly_payroll_calculation_mode = _normalize_monthly_payroll_calculation_mode(
        getattr(policy, "monthly_payroll_calculation_mode", None)
    )
    schedule = get_employee_schedule(payroll.employee_id, period.start_date, db)
    compensation = get_employee_compensation(payroll.employee_id, period.end_date, db)
    holidays = get_employee_holiday_dates(payroll.employee_id, period.start_date, period.end_date, db)
    full_period_working_days = get_working_days(period.start_date, period.end_date, schedule, holidays)
    accrual_window = _get_payroll_accrual_window(period)
    accrued_working_days = (
        get_working_days(accrual_window[0], accrual_window[1], schedule, holidays)
        if accrual_window
        else []
    )
    accrued_days = (
        [day for day in days if accrual_window[0] <= day.work_date <= accrual_window[1]]
        if accrual_window
        else []
    )
    if monthly_payroll_calculation_mode == MONTHLY_PAYROLL_CALCULATION_MODE_CALENDAR_DAYS:
        full_period_basis_days = _expand_date_range(period.start_date, period.end_date)
        accrued_basis_days = _expand_date_range(accrual_window[0], accrual_window[1]) if accrual_window else []
    else:
        full_period_basis_days = full_period_working_days
        accrued_basis_days = accrued_working_days
    expected_day_minutes = max(
        1,
        _minutes_between_times(schedule.start_time, schedule.end_time) - int(schedule.break_minutes or 0),
    )
    minimum_auto_pay_minutes = max(0, int(getattr(policy, "minimum_auto_pay_minutes", 0) or 0))
    tiny_review_days = [
        day
        for day in accrued_days
        if _requires_minimum_attendance_review(day, minimum_auto_pay_minutes)
        and day.review_status not in {"approved", "locked"}
    ]
    for day in tiny_review_days:
        if day.review_status != "needs_review":
            day.review_status = "needs_review"
            day.reviewed_at = None
            day.reviewed_by = None
            db.add(day)

    summary = _attendance_summary(accrued_days, expected_day_minutes)
    base_monthly_salary = _decimal(compensation.base_monthly_salary)
    resolved_rates = _resolve_monthly_rates(
        compensation,
        base_monthly_salary=base_monthly_salary,
        expected_day_minutes=expected_day_minutes,
        basis_days_count=len(full_period_basis_days),
    )

    recorded_dates = {item.work_date for item in accrued_days}
    missing_workdays = [day for day in accrued_working_days if day not in recorded_dates]
    missing_workday_minutes = len(missing_workdays) * expected_day_minutes
    unpaid_vacation_minutes = sum(day.expected_work_minutes for day in accrued_days if day.status == "unpaid_vacation")
    partial_unpaid_minutes = sum(
        _int(day.unpaid_minutes)
        for day in accrued_days
        if day.status not in {"absent", "unpaid_vacation", "incomplete", "weekly_off", "holiday"}
    )
    review_held_paid_minutes = sum(_int(day.normal_paid_minutes) for day in tiny_review_days)
    full_period_expected_minutes = _int(resolved_rates["period_expected_minutes"])
    period_expected_minutes = len(accrued_basis_days) * expected_day_minutes
    earned_unpaid_minutes = min(period_expected_minutes, max(0, _int(summary["unpaid_minutes"]) + missing_workday_minutes))
    earned_paid_minutes = max(0, period_expected_minutes - earned_unpaid_minutes)
    raw_unpaid_minutes = earned_unpaid_minutes + review_held_paid_minutes
    unpaid_minutes = min(period_expected_minutes, max(0, raw_unpaid_minutes))
    paid_minutes = max(0, period_expected_minutes - unpaid_minutes)

    base_salary = _money(base_monthly_salary)
    normal_amount = _money(resolved_rates["auto_minute_rate"] * Decimal(period_expected_minutes))
    attendance_minute_rate = resolved_rates["auto_minute_rate"]
    earned_attendance_deduction = _money(min(base_salary, _money(attendance_minute_rate * Decimal(earned_unpaid_minutes))))
    attendance_deduction = _money(min(base_salary, _money(attendance_minute_rate * Decimal(unpaid_minutes))))
    late_penalty_eligible_minutes = 0
    late_penalty_enabled = False
    late_penalty_rate = Decimal("0.00")
    raw_late_penalty_amount = Decimal("0.00")
    late_penalty_amount = _money(min(raw_late_penalty_amount, max(Decimal("0.00"), base_salary - attendance_deduction)))
    payable_overtime_minutes = summary["overtime_minutes"] if summary["overtime_minutes"] >= int(policy.minimum_overtime_minutes or 0) else 0
    overtime_amount = _money((resolved_rates["resolved_overtime_rate"] / Decimal("60")) * Decimal(payable_overtime_minutes)) if policy.overtime_enabled else Decimal("0.00")

    adjustments = _load_adjustments(payroll.id, db)
    bonus_amount = _sum_adjustments_by_type(adjustments, "bonus")
    manual_deduction_amount = _sum_adjustments_by_type(adjustments, "deduction")
    correction_amount = _sum_adjustments_by_type(adjustments, "correction")
    due_settlement_amount = _sum_adjustments_by_type(adjustments, DUE_SETTLEMENT_ADJUSTMENT_TYPE)
    due_state = _build_due_state_values(
        employee_due_balance=_decimal((payroll.employee or db.get(Employees, payroll.employee_id)).dues),
        due_settlement_amount=due_settlement_amount,
        paid_amount=_decimal(payroll.paid_amount),
    )

    gross_salary = _money(normal_amount + overtime_amount + bonus_amount + correction_amount + due_settlement_amount)
    earned_deduction_amount = _money(earned_attendance_deduction + manual_deduction_amount)
    deduction_amount = _money(attendance_deduction + manual_deduction_amount)
    earned_net_salary = _money(gross_salary - earned_deduction_amount - late_penalty_amount)
    payable_net_salary = _money(gross_salary - deduction_amount - late_penalty_amount)
    amount_snapshot = _build_payroll_amount_snapshot(
        earned_net_salary=earned_net_salary,
        payable_amount=payable_net_salary,
    )

    needs_review_reasons = list(resolved_rates["review_warnings"])
    if tiny_review_days:
        held_dates = ", ".join(day.work_date.isoformat() for day in tiny_review_days[:5])
        if len(tiny_review_days) > 5:
            held_dates = f"{held_dates}, +{len(tiny_review_days) - 5} more"
        needs_review_reasons.append(
            f"Tiny attendance below the {minimum_auto_pay_minutes}-minute auto-pay threshold was held for review on {held_dates}"
        )

    calc_data = {
        **summary,
        "monthly_payroll_calculation_mode": monthly_payroll_calculation_mode,
        "working_days_count": len(accrued_working_days),
        "full_period_working_days_count": len(full_period_working_days),
        "payroll_basis_days_count": len(accrued_basis_days),
        "full_period_payroll_basis_days_count": resolved_rates["basis_days_count"],
        "expected_day_minutes": expected_day_minutes,
        "period_expected_minutes": period_expected_minutes,
        "full_period_expected_minutes": full_period_expected_minutes,
        "effective_cutoff_date": accrual_window[1].isoformat() if accrual_window else None,
        "missing_attendance_days": len(missing_workdays),
        "missing_workday_minutes": missing_workday_minutes,
        "earned_paid_minutes": earned_paid_minutes,
        "earned_unpaid_minutes": earned_unpaid_minutes,
        "paid_minutes": paid_minutes,
        "attendance_review_held_minutes": review_held_paid_minutes,
        "partial_unpaid_minutes": partial_unpaid_minutes,
        "unpaid_minutes_before_cap": raw_unpaid_minutes,
        "unpaid_minutes": unpaid_minutes,
        "unpaid_vacation_minutes": unpaid_vacation_minutes,
        "base_salary": str(base_salary),
        "auto_daily_rate": str(resolved_rates["auto_daily_rate"]),
        "auto_hourly_rate": str(resolved_rates["auto_hourly_rate"]),
        "auto_minute_rate": str(resolved_rates["auto_minute_rate"]),
        "resolved_daily_rate": str(resolved_rates["resolved_daily_rate"]),
        "resolved_hourly_rate": str(resolved_rates["resolved_hourly_rate"]),
        "resolved_minute_rate": str(resolved_rates["resolved_minute_rate"]),
        "resolved_late_deduction_rate": str(resolved_rates["resolved_late_deduction_rate"]),
        "resolved_overtime_rate": str(resolved_rates["resolved_overtime_rate"]),
        "rate_source": resolved_rates["rate_source"],
        "rate_sources": resolved_rates["rate_sources"],
        "rate_review_warnings": resolved_rates["review_warnings"],
        "minimum_auto_pay_minutes": minimum_auto_pay_minutes,
        "normal_amount": str(normal_amount),
        "overtime_amount": str(overtime_amount),
        "payable_overtime_minutes": payable_overtime_minutes,
        "bonus_amount": str(bonus_amount),
        "due_settlement_amount": str(due_settlement_amount),
        "attendance_deduction": str(attendance_deduction),
        "earned_attendance_deduction": str(earned_attendance_deduction),
        "manual_deduction_amount": str(manual_deduction_amount),
        "earned_deduction_amount": str(earned_deduction_amount),
        "deduction_amount": str(deduction_amount),
        "late_penalty_enabled": late_penalty_enabled,
        "late_penalty_rate": str(late_penalty_rate),
        "late_penalty_eligible_minutes": late_penalty_eligible_minutes,
        "late_penalty_amount": str(late_penalty_amount),
        "automatic_deduction_amount": str(_money(attendance_deduction + late_penalty_amount)),
        "unpaid_vacation_deduction": "0.00",
        "adjustment_amount": str(correction_amount),
        "gross_salary": str(gross_salary),
        "final_net_salary": str(earned_net_salary),
        "net_salary": str(earned_net_salary),
        "total_amount": str(amount_snapshot["payable_amount"]),
        "earned_net_salary": str(amount_snapshot["earned_net_salary"]),
        "payable_amount": str(amount_snapshot["payable_amount"]),
        "approved_payable_amount": str(amount_snapshot["approved_payable_amount"]),
        "held_for_review_amount": str(amount_snapshot["held_for_review_amount"]),
        "employee_due_balance": str(due_state["employee_due_balance"]),
        "settled_due_amount": str(due_state["settled_due_amount"]),
        "remaining_due_settlement_amount": str(due_state["remaining_due_settlement_amount"]),
        "remaining_due_balance_after_settlement": str(due_state["remaining_due_balance_after_settlement"]),
        "needs_review_reasons": needs_review_reasons,
    }
    return {
        "salary_type": compensation.salary_type,
        "base_salary": base_salary,
        "normal_amount": normal_amount,
        "overtime_amount": overtime_amount,
        "bonus_amount": bonus_amount,
        "attendance_deduction_amount": attendance_deduction,
        "manual_deduction_amount": manual_deduction_amount,
        "late_penalty_amount": late_penalty_amount,
        "due_settlement_amount": due_settlement_amount,
        "deduction_amount": deduction_amount,
        "late_deduction_amount": late_penalty_amount,
        "unpaid_vacation_deduction": Decimal("0.00"),
        "adjustment_amount": correction_amount,
        "gross_salary": gross_salary,
        "net_salary": amount_snapshot["earned_net_salary"],
        "total_amount": amount_snapshot["payable_amount"],
        "calculation_data_json": calc_data,
        "needs_review": bool(needs_review_reasons),
    }


def calculate_daily_employee_payroll(payroll: EmployeePayroll, period: PayrollPeriod, days: list[AttendanceDay], db: Session):
    policy = get_or_create_payroll_policy(db)
    schedule = get_employee_schedule(payroll.employee_id, period.start_date, db)
    compensation = get_employee_compensation(payroll.employee_id, period.end_date, db)
    expected_day_minutes = max(
        1,
        int((datetime.combine(date.today(), schedule.end_time) - datetime.combine(date.today(), schedule.start_time)).total_seconds() // 60)
        - int(schedule.break_minutes or 0),
    )
    summary = _attendance_summary(days, expected_day_minutes)

    paid_day_equivalent = Decimal("0.00")
    for day in days:
        if day.status in {"present", "late"}:
            paid_day_equivalent += Decimal(day.normal_paid_minutes) / Decimal(expected_day_minutes)
        elif day.status == "paid_vacation" and policy.paid_vacation_counts_for_daily:
            paid_day_equivalent += Decimal("1.00")

    normal_amount = _money(_decimal(compensation.daily_rate) * paid_day_equivalent)
    payable_overtime_minutes = summary["overtime_minutes"] if summary["overtime_minutes"] >= int(policy.minimum_overtime_minutes or 0) else 0
    overtime_amount = _money((_decimal(compensation.overtime_rate) / Decimal("60")) * Decimal(payable_overtime_minutes)) if policy.overtime_enabled else Decimal("0.00")
    adjustments = _load_adjustments(payroll.id, db)
    bonus_amount = _sum_adjustments_by_type(adjustments, "bonus")
    deduction_amount = _sum_adjustments_by_type(adjustments, "deduction")
    correction_amount = _sum_adjustments_by_type(adjustments, "correction")
    due_settlement_amount = _sum_adjustments_by_type(adjustments, DUE_SETTLEMENT_ADJUSTMENT_TYPE)
    due_state = _build_due_state_values(
        employee_due_balance=_decimal(db.get(Employees, payroll.employee_id).dues),
        due_settlement_amount=due_settlement_amount,
        paid_amount=_decimal(payroll.paid_amount),
    )

    gross_salary = _money(normal_amount + overtime_amount + bonus_amount + correction_amount + due_settlement_amount)
    net_salary = _money(gross_salary - deduction_amount)
    amount_snapshot = _build_payroll_amount_snapshot(earned_net_salary=net_salary)
    calc_data = {
        **summary,
        "absence_days": summary["absence_days"],
        "paid_vacation_days": summary["paid_vacation_days"],
        "unpaid_vacation_days": summary["unpaid_vacation_days"],
        "base_salary": "0.00",
        "normal_amount": str(normal_amount),
        "overtime_amount": str(overtime_amount),
        "payable_overtime_minutes": payable_overtime_minutes,
        "bonus_amount": str(bonus_amount),
        "due_settlement_amount": str(due_settlement_amount),
        "attendance_deduction": "0.00",
        "manual_deduction_amount": str(deduction_amount),
        "deduction_amount": str(deduction_amount),
        "late_penalty_amount": "0.00",
        "adjustment_amount": str(correction_amount),
        "gross_salary": str(gross_salary),
        "final_net_salary": str(amount_snapshot["earned_net_salary"]),
        "net_salary": str(amount_snapshot["earned_net_salary"]),
        "total_amount": str(amount_snapshot["payable_amount"]),
        "earned_net_salary": str(amount_snapshot["earned_net_salary"]),
        "payable_amount": str(amount_snapshot["payable_amount"]),
        "approved_payable_amount": str(amount_snapshot["approved_payable_amount"]),
        "held_for_review_amount": str(amount_snapshot["held_for_review_amount"]),
        "employee_due_balance": str(due_state["employee_due_balance"]),
        "settled_due_amount": str(due_state["settled_due_amount"]),
        "remaining_due_settlement_amount": str(due_state["remaining_due_settlement_amount"]),
        "remaining_due_balance_after_settlement": str(due_state["remaining_due_balance_after_settlement"]),
    }
    return {
        "salary_type": compensation.salary_type,
        "base_salary": Decimal("0.00"),
        "normal_amount": normal_amount,
        "overtime_amount": overtime_amount,
        "bonus_amount": bonus_amount,
        "attendance_deduction_amount": Decimal("0.00"),
        "manual_deduction_amount": deduction_amount,
        "late_penalty_amount": Decimal("0.00"),
        "due_settlement_amount": due_settlement_amount,
        "deduction_amount": deduction_amount,
        "late_deduction_amount": Decimal("0.00"),
        "unpaid_vacation_deduction": Decimal("0.00"),
        "adjustment_amount": correction_amount,
        "gross_salary": gross_salary,
        "net_salary": amount_snapshot["earned_net_salary"],
        "total_amount": amount_snapshot["payable_amount"],
        "calculation_data_json": calc_data,
    }


def calculate_hourly_employee_payroll(payroll: EmployeePayroll, period: PayrollPeriod, days: list[AttendanceDay], db: Session):
    policy = get_or_create_payroll_policy(db)
    compensation = get_employee_compensation(payroll.employee_id, period.end_date, db)
    summary = _attendance_summary(days, 1)

    normal_amount = _money((_decimal(compensation.hourly_rate) / Decimal("60")) * Decimal(summary["normal_paid_minutes"]))
    payable_overtime_minutes = summary["overtime_minutes"] if summary["overtime_minutes"] >= int(policy.minimum_overtime_minutes or 0) else 0
    overtime_amount = _money((_decimal(compensation.overtime_rate) / Decimal("60")) * Decimal(payable_overtime_minutes)) if policy.overtime_enabled else Decimal("0.00")
    adjustments = _load_adjustments(payroll.id, db)
    bonus_amount = _sum_adjustments_by_type(adjustments, "bonus")
    deduction_amount = _sum_adjustments_by_type(adjustments, "deduction")
    correction_amount = _sum_adjustments_by_type(adjustments, "correction")
    due_settlement_amount = _sum_adjustments_by_type(adjustments, DUE_SETTLEMENT_ADJUSTMENT_TYPE)
    due_state = _build_due_state_values(
        employee_due_balance=_decimal(db.get(Employees, payroll.employee_id).dues),
        due_settlement_amount=due_settlement_amount,
        paid_amount=_decimal(payroll.paid_amount),
    )

    gross_salary = _money(normal_amount + overtime_amount + bonus_amount + correction_amount + due_settlement_amount)
    net_salary = _money(gross_salary - deduction_amount)
    amount_snapshot = _build_payroll_amount_snapshot(earned_net_salary=net_salary)
    calc_data = {
        **summary,
        "base_salary": "0.00",
        "normal_amount": str(normal_amount),
        "overtime_amount": str(overtime_amount),
        "payable_overtime_minutes": payable_overtime_minutes,
        "bonus_amount": str(bonus_amount),
        "due_settlement_amount": str(due_settlement_amount),
        "attendance_deduction": "0.00",
        "manual_deduction_amount": str(deduction_amount),
        "deduction_amount": str(deduction_amount),
        "late_penalty_amount": "0.00",
        "adjustment_amount": str(correction_amount),
        "gross_salary": str(gross_salary),
        "final_net_salary": str(amount_snapshot["earned_net_salary"]),
        "net_salary": str(amount_snapshot["earned_net_salary"]),
        "total_amount": str(amount_snapshot["payable_amount"]),
        "earned_net_salary": str(amount_snapshot["earned_net_salary"]),
        "payable_amount": str(amount_snapshot["payable_amount"]),
        "approved_payable_amount": str(amount_snapshot["approved_payable_amount"]),
        "held_for_review_amount": str(amount_snapshot["held_for_review_amount"]),
        "employee_due_balance": str(due_state["employee_due_balance"]),
        "settled_due_amount": str(due_state["settled_due_amount"]),
        "remaining_due_settlement_amount": str(due_state["remaining_due_settlement_amount"]),
        "remaining_due_balance_after_settlement": str(due_state["remaining_due_balance_after_settlement"]),
    }
    return {
        "salary_type": compensation.salary_type,
        "base_salary": Decimal("0.00"),
        "normal_amount": normal_amount,
        "overtime_amount": overtime_amount,
        "bonus_amount": bonus_amount,
        "attendance_deduction_amount": Decimal("0.00"),
        "manual_deduction_amount": deduction_amount,
        "late_penalty_amount": Decimal("0.00"),
        "due_settlement_amount": due_settlement_amount,
        "deduction_amount": deduction_amount,
        "late_deduction_amount": Decimal("0.00"),
        "unpaid_vacation_deduction": Decimal("0.00"),
        "adjustment_amount": correction_amount,
        "gross_salary": gross_salary,
        "net_salary": amount_snapshot["earned_net_salary"],
        "total_amount": amount_snapshot["payable_amount"],
        "calculation_data_json": calc_data,
    }


def create_payroll_history_snapshot(
    payroll: EmployeePayroll,
    old_gross_salary: Decimal | None,
    old_net_salary: Decimal | None,
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


def _upsert_discrepancy(
    *,
    payroll: EmployeePayroll | None,
    period: PayrollPeriod,
    employee_id: int,
    discrepancy_type: str,
    description: str,
    severity: str,
    db: Session,
):
    existing = db.scalar(
        select(PayrollDiscrepancy).where(
            PayrollDiscrepancy.payroll_period_id == period.id,
            PayrollDiscrepancy.employee_id == employee_id,
            PayrollDiscrepancy.discrepancy_type == discrepancy_type,
            PayrollDiscrepancy.description == description,
            PayrollDiscrepancy.status == "open",
        )
    )
    if existing:
        return existing

    discrepancy = PayrollDiscrepancy(
        employee_payroll_id=payroll.id if payroll else None,
        payroll_period_id=period.id,
        employee_id=employee_id,
        discrepancy_type=discrepancy_type,
        description=description,
        severity=severity,
        status="open",
    )
    db.add(discrepancy)
    db.flush()
    notification_service = NotificationService(db)
    if _should_send_payroll_discrepancy_notification(period) and not notification_service.notification_exists(
        notification_type="payroll_discrepancy_detected",
        entity_type="payroll_discrepancy",
        entity_id=discrepancy.id,
    ):
        notification_service.notify_role(
            role_codes=["hr", "admin"],
            notification_type="payroll_discrepancy_detected",
            title="Payroll discrepancy detected",
            message=description,
            title_key="notifications.payroll_discrepancy_detected_title",
            message_key="notifications.payroll_discrepancy_detected_message",
            translation_params={"description": description},
            is_system_content=True,
            entity_type="payroll_discrepancy",
            entity_id=discrepancy.id,
            priority="high",
            skip_if_no_recipients=True,
        )
    return discrepancy


def _resolve_discrepancy(
    discrepancy: PayrollDiscrepancy,
    resolution_note: str,
    db: Session,
    resolved_by: int | None = None,
) -> PayrollDiscrepancy:
    if discrepancy.status == "resolved":
        return discrepancy

    discrepancy.status = "resolved"
    discrepancy.resolution_note = resolution_note
    discrepancy.resolved_by = resolved_by
    discrepancy.resolved_at = _utc_now()
    db.add(discrepancy)
    save_audit_log(
        db,
        action="payroll_discrepancy_auto_resolved" if resolved_by is None else "payroll_discrepancy_resolved",
        entity_type="PayrollDiscrepancy",
        entity_id=discrepancy.id,
        old_data_json={"status": "open"},
        new_data_json={"status": discrepancy.status, "resolution_note": resolution_note},
        user_id=resolved_by,
    )
    return discrepancy


def detect_payroll_discrepancies(employee_id: int, payroll_period_id: int, db: Session):
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")

    payroll = _get_employee_payroll(employee_id, payroll_period_id, db)
    schedule = get_employee_schedule(employee_id, period.start_date, db)
    policy = get_or_create_payroll_policy(db)
    holidays = get_employee_holiday_dates(employee_id, period.start_date, period.end_date, db)
    accrual_window = _get_payroll_accrual_window(period)
    working_days = (
        get_working_days(accrual_window[0], accrual_window[1], schedule, holidays)
        if accrual_window
        else []
    )
    days = _load_period_attendance(employee_id, period, db)
    if accrual_window:
        days = [item for item in days if accrual_window[0] <= item.work_date <= accrual_window[1]]
    else:
        days = []
    days_by_date = {item.work_date: item for item in days}
    expected_open: dict[tuple[str, str], str] = {}

    def expect(discrepancy_type: str, description: str, severity: str) -> None:
        expected_open[(discrepancy_type, description)] = severity

    for work_day in working_days:
        day = days_by_date.get(work_day)
        if not day:
            expect("missing_attendance", f"Missing attendance snapshot for {work_day.isoformat()}", "medium")
            continue

        if day.status == "incomplete":
            discrepancy_type = "missing_checkout" if day.check_in_time and not day.check_out_time else "missing_checkin"
            expect(discrepancy_type, f"Incomplete attendance on {work_day.isoformat()}", "high")
        if day.review_status not in {"approved", "locked"}:
            expect(
                "attendance_requires_review",
                f"Attendance on {work_day.isoformat()} is not approved for payroll usage",
                "medium",
            )

    vacations = db.scalars(
        select(Vacation).where(
            Vacation.employee_id == employee_id,
            Vacation.vacation_status == int(VacationStatuses.approved),
            Vacation.start_date <= (accrual_window[1] if accrual_window else period.start_date),
            Vacation.end_date >= period.start_date,
        )
    ).all()
    for vacation in vacations:
        current = max(vacation.start_date, period.start_date)
        last = min(vacation.end_date, accrual_window[1]) if accrual_window else period.start_date - timedelta(days=1)
        while current <= last:
            day = days_by_date.get(current)
            if day and (day.check_in_time or day.check_out_time):
                expect("vacation_overlap", f"Vacation overlaps attendance on {current.isoformat()}", "medium")
            current += timedelta(days=1)

    open_discrepancies = db.scalars(
        select(PayrollDiscrepancy).where(
            PayrollDiscrepancy.payroll_period_id == payroll_period_id,
            PayrollDiscrepancy.employee_id == employee_id,
            PayrollDiscrepancy.status == "open",
        )
    ).all()
    existing_open = {
        (item.discrepancy_type, item.description): item
        for item in open_discrepancies
    }

    for (discrepancy_type, description), severity in expected_open.items():
        if (discrepancy_type, description) in existing_open:
            continue
        _upsert_discrepancy(
            payroll=payroll,
            period=period,
            employee_id=employee_id,
            discrepancy_type=discrepancy_type,
            description=description,
            severity=severity,
            db=db,
        )

    for discrepancy in open_discrepancies:
        key = (discrepancy.discrepancy_type, discrepancy.description)
        if discrepancy.discrepancy_type not in MANAGED_DISCREPANCY_TYPES:
            continue
        if key in expected_open:
            continue
        _resolve_discrepancy(discrepancy, "Automatically resolved during payroll reconciliation", db)

    return db.scalars(
        select(PayrollDiscrepancy)
        .where(
            PayrollDiscrepancy.payroll_period_id == payroll_period_id,
            PayrollDiscrepancy.employee_id == employee_id,
        )
        .order_by(PayrollDiscrepancy.created_at.desc(), PayrollDiscrepancy.id.desc())
    ).all()


def reconcile_payroll_period_discrepancies(payroll_period_id: int, db: Session) -> list[int]:
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")

    employee_ids = set(
        db.scalars(
            select(EmployeePayroll.employee_id).where(EmployeePayroll.payroll_period_id == payroll_period_id)
        ).all()
    )
    employee_ids.update(
        db.scalars(
            select(PayrollDiscrepancy.employee_id).where(PayrollDiscrepancy.payroll_period_id == payroll_period_id)
        ).all()
    )

    for employee_id in sorted(employee_ids):
        detect_payroll_discrepancies(employee_id, payroll_period_id, db)
    return sorted(employee_ids)


def calculate_employee_payroll(
    employee_id: int,
    payroll_period_id: int,
    db: Session,
    reason: str = "manual_recalculation",
    created_by: int | None = None,
    force_history: bool = False,
):
    employee = db.get(Employees, employee_id)
    if not employee:
        raise ResourceNotFoundException("Employee")

    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")

    payroll = _get_employee_payroll(employee_id, payroll_period_id, db)
    if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
        raise BadRequestException("Approved or paid payroll cannot be recalculated", message_key="errors.approved_or_paid_payroll_recalc")

    old_gross_salary = _decimal(payroll.gross_salary)
    old_net_salary = _decimal(payroll.net_salary)
    old_balance_amount = _decimal(payroll.balance_amount)
    days = _load_period_attendance(employee_id, period, db)
    compensation = get_employee_compensation(employee_id, period.end_date, db)

    if compensation.salary_type == "monthly":
        results = calculate_monthly_employee_payroll(payroll, period, days, db)
    elif compensation.salary_type == "daily":
        results = calculate_daily_employee_payroll(payroll, period, days, db)
    else:
        results = calculate_hourly_employee_payroll(payroll, period, days, db)

    for field_name, value in results.items():
        if field_name in {"calculation_data_json", "needs_review"}:
            continue
        setattr(payroll, field_name, value)
    _sync_payroll_balance(payroll, payable_amount=_decimal(results.get("total_amount"), default=str(_decimal(payroll.net_salary))))

    payroll.status = "draft"
    payroll.calculated_at = _utc_now()
    db.add(payroll)
    db.flush()

    discrepancies = detect_payroll_discrepancies(employee_id, payroll_period_id, db)
    if results.get("needs_review"):
        payroll.status = "needs_review"
    elif any(item.status == "open" and item.severity == "high" for item in discrepancies):
        payroll.status = "needs_review"
    elif any(item.status == "open" for item in discrepancies):
        payroll.status = "needs_review"

    threshold = _decimal(get_or_create_payroll_policy(db).significant_change_threshold)
    has_meaningful_change = (
        abs(payroll.net_salary - old_net_salary) >= threshold
        or abs(payroll.gross_salary - old_gross_salary) >= threshold
        or abs(payroll.balance_amount - old_balance_amount) >= threshold
    )
    if force_history or has_meaningful_change:
        create_payroll_history_snapshot(
            payroll,
            old_gross_salary=old_gross_salary,
            old_net_salary=old_net_salary,
            reason=reason,
            calculation_data_json=results["calculation_data_json"],
            db=db,
            created_by=created_by,
        )

    save_audit_log(
        db,
        action="payroll_recalculated",
        entity_type="EmployeePayroll",
        entity_id=payroll.id,
        old_data_json={"gross_salary": str(old_gross_salary), "net_salary": str(old_net_salary), "balance_amount": str(old_balance_amount)},
        new_data_json={
            "gross_salary": str(payroll.gross_salary),
            "net_salary": str(payroll.net_salary),
            "total_amount": str(payroll.total_amount),
            "paid_amount": str(payroll.paid_amount),
            "balance_amount": str(payroll.balance_amount),
            "reason": reason,
        },
        user_id=created_by,
    )
    db.flush()
    _apply_payroll_snapshot_fields(payroll, results["calculation_data_json"])
    _apply_due_state_fields(payroll, db)
    _notify_payroll_backoffice_status(payroll, db)
    return payroll


def recalculate_payroll_period(payroll_period_id: int, db: Session, created_by: int | None = None):
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")
    if period.status in FINAL_PAYROLL_STATUSES:
        raise BadRequestException("Approved or paid payroll period cannot be recalculated", message_key="errors.approved_or_paid_payroll_recalc")

    employees = db.scalars(select(Employees).where(Employees.is_active.is_(True))).all()
    payrolls: list[EmployeePayroll] = []
    for employee in employees:
        payrolls.append(
            calculate_employee_payroll(
                employee_id=employee.id,
                payroll_period_id=payroll_period_id,
                db=db,
                reason="period_recalculation",
                created_by=created_by,
            )
        )

    reconcile_payroll_period_discrepancies(payroll_period_id, db)
    db.commit()
    for payroll in payrolls:
        db.refresh(payroll)
    return payrolls


def reconcile_existing_payrolls_for_settings_change(
    db: Session,
    *,
    reason: str = "settings_change",
    created_by: int | None = None,
) -> dict[str, int]:
    payrolls = db.scalars(
        select(EmployeePayroll)
        .options(selectinload(EmployeePayroll.payroll_period))
        .order_by(EmployeePayroll.payroll_period_id.asc(), EmployeePayroll.employee_id.asc(), EmployeePayroll.id.asc())
    ).all()

    summary = {
        "recalculated": 0,
        "reconciled": 0,
        "skipped": 0,
    }

    for payroll in payrolls:
        period = payroll.payroll_period
        if not period or period.status == "cancelled":
            summary["skipped"] += 1
            continue

        if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
            detect_payroll_discrepancies(payroll.employee_id, payroll.payroll_period_id, db)
            summary["reconciled"] += 1
            continue

        calculate_employee_payroll(
            employee_id=payroll.employee_id,
            payroll_period_id=payroll.payroll_period_id,
            db=db,
            reason=reason,
            created_by=created_by,
        )
        summary["recalculated"] += 1

    return summary


def reconcile_existing_payrolls_for_employee_compensation_change(
    employee_id: int,
    db: Session,
    *,
    reason: str = "employee_compensation_updated",
    created_by: int | None = None,
) -> dict[str, int]:
    employee = db.get(Employees, employee_id)
    if not employee:
        raise ResourceNotFoundException("Employee")

    payrolls = db.scalars(
        select(EmployeePayroll)
        .options(selectinload(EmployeePayroll.payroll_period))
        .where(EmployeePayroll.employee_id == employee_id)
        .order_by(EmployeePayroll.payroll_period_id.asc(), EmployeePayroll.id.asc())
    ).all()

    summary = {
        "recalculated": 0,
        "reconciled": 0,
        "skipped": 0,
    }

    for payroll in payrolls:
        period = payroll.payroll_period
        if not period or period.status == "cancelled":
            summary["skipped"] += 1
            continue

        if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
            detect_payroll_discrepancies(payroll.employee_id, payroll.payroll_period_id, db)
            summary["reconciled"] += 1
            continue

        calculate_employee_payroll(
            employee_id=payroll.employee_id,
            payroll_period_id=payroll.payroll_period_id,
            db=db,
            reason=reason,
            created_by=created_by,
            force_history=True,
        )
        summary["recalculated"] += 1

    return summary


def reconcile_existing_payrolls_for_employee_due_change(
    employee_id: int,
    db: Session,
    *,
    reason: str = "employee_due_balance_updated",
    created_by: int | None = None,
) -> dict[str, int]:
    employee = db.get(Employees, employee_id)
    if not employee:
        raise ResourceNotFoundException("Employee")

    payrolls = db.scalars(
        select(EmployeePayroll)
        .options(selectinload(EmployeePayroll.payroll_period))
        .where(EmployeePayroll.employee_id == employee_id)
        .order_by(EmployeePayroll.payroll_period_id.asc(), EmployeePayroll.id.asc())
    ).all()

    summary = {
        "recalculated": 0,
        "refreshed": 0,
        "skipped": 0,
    }

    for payroll in payrolls:
        period = payroll.payroll_period
        if not period or period.status == "cancelled":
            summary["skipped"] += 1
            continue

        if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
            latest_snapshot = _latest_payroll_snapshot(payroll.id, db)
            due_settlement_amount = _sum_adjustments_by_type(_load_adjustments(payroll.id, db), DUE_SETTLEMENT_ADJUSTMENT_TYPE)
            updated_snapshot = {
                **latest_snapshot,
                **{
                    key: str(value)
                    for key, value in _build_due_state_values(
                        employee_due_balance=_decimal(getattr(employee, "dues", 0)),
                        due_settlement_amount=due_settlement_amount,
                        paid_amount=_decimal(payroll.paid_amount),
                    ).items()
                },
            }
            create_payroll_history_snapshot(
                payroll,
                old_gross_salary=_decimal(payroll.gross_salary),
                old_net_salary=_decimal(payroll.net_salary),
                reason=reason,
                calculation_data_json=updated_snapshot,
                db=db,
                created_by=created_by,
            )
            _apply_payroll_snapshot_fields(payroll, updated_snapshot)
            summary["refreshed"] += 1
            continue

        calculate_employee_payroll(
            employee_id=payroll.employee_id,
            payroll_period_id=payroll.payroll_period_id,
            db=db,
            reason=reason,
            created_by=created_by,
            force_history=True,
        )
        summary["recalculated"] += 1

    return summary


def sync_payroll_with_attendance_context(employee_id: int, work_date: date, db: Session, trigger_reason: str = "attendance_change") -> dict[str, object]:
    period = get_or_create_payroll_period_for_date(work_date, db)
    payroll = _get_employee_payroll(employee_id, period.id, db)
    policy = get_or_create_payroll_policy(db)

    if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
        _upsert_discrepancy(
            payroll=payroll,
            period=period,
            employee_id=employee_id,
            discrepancy_type="attendance_changed_after_approval",
            description=f"Attendance changed on {work_date.isoformat()} after payroll was finalized",
            severity="high",
            db=db,
        )
        return {
            "status": "discrepancy_created",
            "payroll_id": payroll.id,
            "payroll_status": payroll.status,
            "payroll_period_id": period.id,
        }

    if not policy.auto_recalculate_draft_payroll:
        return {
            "status": "skipped",
            "payroll_id": payroll.id,
            "payroll_status": payroll.status,
            "payroll_period_id": period.id,
        }

    force_history = trigger_reason in {
        "attendance_correction",
        "attendance_delete",
        "smart_status_correction",
        "vacation_approved",
        "vacation_rejected",
        "payroll_adjustment",
    }
    payroll = calculate_employee_payroll(
        employee_id=employee_id,
        payroll_period_id=period.id,
        db=db,
        reason=trigger_reason,
        force_history=force_history,
    )
    return {
        "status": "recalculated",
        "payroll_id": payroll.id,
        "payroll_status": payroll.status,
        "payroll_period_id": period.id,
    }


def _has_payroll_payments(employee_payroll_id: int, db: Session) -> bool:
    return db.scalar(
        select(Payments.id)
        .where(Payments.employee_payroll_id == employee_payroll_id)
        .limit(1)
    ) is not None


def _has_payroll_adjustments(employee_payroll_id: int, db: Session) -> bool:
    return db.scalar(
        select(PayrollAdjustment.id)
        .where(PayrollAdjustment.employee_payroll_id == employee_payroll_id)
        .limit(1)
    ) is not None


def _latest_non_settlement_payroll_snapshot(employee_payroll_id: int, db: Session) -> dict:
    history = db.scalar(
        select(PayrollCalculationHistory.calculation_data_json)
        .where(
            PayrollCalculationHistory.employee_payroll_id == employee_payroll_id,
            ~PayrollCalculationHistory.reason.in_(
                ("payroll_approved", "payroll_payment_recorded", "payroll_unapproved", "payroll_reopened")
            ),
        )
        .order_by(PayrollCalculationHistory.created_at.desc(), PayrollCalculationHistory.id.desc())
    )
    return history or {}


def _delete_auto_payroll(payroll: EmployeePayroll, db: Session) -> None:
    db.execute(
        delete(PayrollCalculationHistory)
        .where(PayrollCalculationHistory.employee_payroll_id == payroll.id)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        delete(PayrollDiscrepancy)
        .where(PayrollDiscrepancy.employee_payroll_id == payroll.id)
        .execution_options(synchronize_session=False)
    )
    db.execute(
        delete(EmployeePayroll)
        .where(EmployeePayroll.id == payroll.id)
        .execution_options(synchronize_session=False)
    )
    db.flush()


def sync_payroll_after_attendance_delete(employee_id: int, work_date: date, db: Session, deleted_by: int | None = None) -> dict[str, object]:
    period = get_or_create_payroll_period_for_date(work_date, db)
    payroll = _get_employee_payroll(employee_id, period.id, db)

    if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
        _upsert_discrepancy(
            payroll=payroll,
            period=period,
            employee_id=employee_id,
            discrepancy_type="attendance_changed_after_approval",
            description=f"Attendance deleted on {work_date.isoformat()} after payroll was finalized",
            severity="high",
            db=db,
        )
        return {
            "status": "discrepancy_created",
            "payroll_id": payroll.id,
            "payroll_status": payroll.status,
            "payroll_period_id": period.id,
        }

    remaining_days = _load_period_attendance(employee_id, period, db)
    if (
        not remaining_days
        and not _has_payroll_adjustments(payroll.id, db)
        and not _has_payroll_payments(payroll.id, db)
    ):
        payroll_id = payroll.id
        _delete_auto_payroll(payroll, db)
        save_audit_log(
            db,
            action="employee_payroll_deleted_after_attendance_delete",
            entity_type="EmployeePayroll",
            entity_id=payroll_id,
            old_data_json={
                "employee_id": employee_id,
                "payroll_period_id": period.id,
                "work_date": work_date.isoformat(),
            },
            user_id=deleted_by,
        )
        return {
            "status": "deleted_empty_payroll",
            "payroll_id": payroll_id,
            "payroll_period_id": period.id,
            "remaining_attendance_days": 0,
        }

    policy = get_or_create_payroll_policy(db)
    if not policy.auto_recalculate_draft_payroll:
        detect_payroll_discrepancies(employee_id, period.id, db)
        return {
            "status": "skipped",
            "payroll_id": payroll.id,
            "payroll_status": payroll.status,
            "payroll_period_id": period.id,
            "remaining_attendance_days": len(remaining_days),
        }

    payroll = calculate_employee_payroll(
        employee_id=employee_id,
        payroll_period_id=period.id,
        db=db,
        reason="attendance_delete",
        created_by=deleted_by,
        force_history=True,
    )
    return {
        "status": "recalculated",
        "payroll_id": payroll.id,
        "payroll_status": payroll.status,
        "payroll_period_id": period.id,
        "remaining_attendance_days": len(remaining_days),
    }


def sync_payroll_with_attendance_review(employee_id: int, work_date: date, db: Session) -> dict[str, object]:
    period = get_or_create_payroll_period_for_date(work_date, db)
    payroll = _get_employee_payroll(employee_id, period.id, db)

    if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
        detect_payroll_discrepancies(employee_id, period.id, db)
        return {
            "status": "review_reconciled",
            "payroll_id": payroll.id,
            "payroll_status": payroll.status,
            "payroll_period_id": period.id,
        }

    payroll = calculate_employee_payroll(
        employee_id=employee_id,
        payroll_period_id=period.id,
        db=db,
        reason="attendance_review",
        force_history=False,
    )
    return {
        "status": "recalculated",
        "payroll_id": payroll.id,
        "payroll_status": payroll.status,
        "payroll_period_id": period.id,
    }


def sync_payroll_with_attendance_day(day: AttendanceDay, db: Session, trigger_reason: str = "attendance_change"):
    result = sync_payroll_with_attendance_context(
        employee_id=day.employee_id,
        work_date=day.work_date,
        db=db,
        trigger_reason=trigger_reason,
    )
    payroll_id = result.get("payroll_id")
    return db.get(EmployeePayroll, payroll_id) if payroll_id else None


def approve_employee_payroll(employee_payroll_id: int, db: Session, approved_by: int | None = None):
    payroll = db.scalar(
        select(EmployeePayroll)
        .options(selectinload(EmployeePayroll.discrepancies))
        .where(EmployeePayroll.id == employee_payroll_id)
    )
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")

    open_high = [
        item
        for item in detect_payroll_discrepancies(payroll.employee_id, payroll.payroll_period_id, db)
        if item.status == "open" and item.severity == "high"
    ]
    if open_high:
        raise BadRequestException("Resolve high-severity discrepancies before approval", message_key="errors.resolve_high_severity_first")

    old_status = payroll.status
    latest_snapshot = _latest_payroll_snapshot(payroll.id, db)
    employee = db.get(Employees, payroll.employee_id)
    due_settlement_amount = _sum_adjustments_by_type(_load_adjustments(payroll.id, db), DUE_SETTLEMENT_ADJUSTMENT_TYPE)
    released_payable_amount = _money(
        _decimal(latest_snapshot.get("approved_payable_amount"), default=str(_decimal(payroll.net_salary)))
    )
    payroll.status = "approved"
    payroll.approved_at = _utc_now()
    _sync_payroll_balance(payroll, payable_amount=released_payable_amount)
    create_payroll_history_snapshot(
        payroll,
        old_gross_salary=_decimal(payroll.gross_salary),
        old_net_salary=_decimal(payroll.net_salary),
        reason="payroll_approved",
        calculation_data_json={
            **latest_snapshot,
            **{
                key: str(value)
                for key, value in _build_due_state_values(
                    employee_due_balance=_decimal(getattr(employee, "dues", 0)),
                    due_settlement_amount=due_settlement_amount,
                    paid_amount=_decimal(payroll.paid_amount),
                ).items()
            },
            "status_before": old_status,
            "status_after": payroll.status,
            "payable_amount": str(released_payable_amount),
            "approved_payable_amount": str(released_payable_amount),
            "held_for_review_amount": "0.00",
        },
        db=db,
        created_by=approved_by,
    )
    save_audit_log(
        db,
        action="payroll_approved",
        entity_type="EmployeePayroll",
        entity_id=payroll.id,
        old_data_json={"status": old_status},
        new_data_json={"status": payroll.status},
        user_id=approved_by,
    )
    _notify_employee_payroll_status(
        payroll=payroll,
        notification_type="payroll_approved",
        title="Payroll approved",
        message=f"Your payroll for period #{payroll.payroll_period_id} was approved.",
        title_key="notifications.payroll_approved_title",
        message_key="notifications.payroll_approved_message",
        translation_params={"period_id": payroll.payroll_period_id},
        actor_user_id=approved_by,
        db=db,
    )
    db.commit()
    db.refresh(payroll)
    _apply_payroll_snapshot_fields(
        payroll,
        {
            **latest_snapshot,
            **{
                key: str(value)
                for key, value in _build_due_state_values(
                    employee_due_balance=_decimal(getattr(employee, "dues", 0)),
                    due_settlement_amount=due_settlement_amount,
                    paid_amount=_decimal(payroll.paid_amount),
                ).items()
            },
            "payable_amount": str(released_payable_amount),
            "approved_payable_amount": str(released_payable_amount),
            "held_for_review_amount": "0.00",
        },
    )
    _apply_due_state_fields(payroll, db)
    return payroll


def unapprove_employee_payroll(employee_payroll_id: int, db: Session, unapproved_by: int | None = None):
    payroll = db.scalar(
        select(EmployeePayroll)
        .options(selectinload(EmployeePayroll.discrepancies))
        .where(EmployeePayroll.id == employee_payroll_id)
    )
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")

    if payroll.status != "approved":
        raise BadRequestException("Only approved payroll can have approval removed")

    if _decimal(payroll.paid_amount) > Decimal("0.00") or _has_payroll_payments(payroll.id, db):
        raise BadRequestException("Approval cannot be removed after payroll payments have been recorded")

    old_status = payroll.status
    old_approved_at = payroll.approved_at
    base_snapshot = _latest_non_settlement_payroll_snapshot(payroll.id, db)
    open_items = detect_payroll_discrepancies(payroll.employee_id, payroll.payroll_period_id, db)
    payable_amount = _money(_decimal(base_snapshot.get("payable_amount"), default=str(_decimal(payroll.net_salary))))

    payroll.status = "needs_review" if any(item.status == "open" for item in open_items) or (base_snapshot.get("needs_review_reasons") or []) else "draft"
    payroll.approved_at = None
    _sync_payroll_balance(payroll, payable_amount=payable_amount)

    create_payroll_history_snapshot(
        payroll,
        old_gross_salary=_decimal(payroll.gross_salary),
        old_net_salary=_decimal(payroll.net_salary),
        reason="payroll_unapproved",
        calculation_data_json={
            **base_snapshot,
            "status_before": old_status,
            "status_after": payroll.status,
            "payable_amount": str(payable_amount),
        },
        db=db,
        created_by=unapproved_by,
    )
    save_audit_log(
        db,
        action="payroll_unapproved",
        entity_type="EmployeePayroll",
        entity_id=payroll.id,
        old_data_json={"status": old_status, "approved_at": str(old_approved_at) if old_approved_at else None},
        new_data_json={"status": payroll.status, "approved_at": None},
        user_id=unapproved_by,
    )
    db.commit()
    db.refresh(payroll)
    _apply_payroll_snapshot_fields(payroll, base_snapshot)
    _apply_due_state_fields(payroll, db)
    return payroll


def reopen_locked_employee_payroll(
    employee_payroll_id: int,
    db: Session,
    reopened_by: int | None = None,
    reason: str | None = None,
):
    payroll = db.get(EmployeePayroll, employee_payroll_id)
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")

    if payroll.status not in {"locked", "paid"}:
        raise BadRequestException("Only paid or locked payroll can be reopened")

    reversal_reason = (reason or "").strip()
    if not reversal_reason:
        raise BadRequestException("A reopen reason is required")

    reversed_amount = _money(_decimal(payroll.paid_amount))
    if reversed_amount <= Decimal("0.00"):
        raise BadRequestException("Locked payroll has no paid amount to reverse")

    old_status = payroll.status
    old_paid_amount = _decimal(payroll.paid_amount)
    old_balance_amount = _decimal(payroll.balance_amount)
    old_paid_at = payroll.paid_at
    old_approved_at = payroll.approved_at
    employee = db.get(Employees, payroll.employee_id)
    due_settlement_amount = _sum_adjustments_by_type(_load_adjustments(payroll.id, db), DUE_SETTLEMENT_ADJUSTMENT_TYPE)
    old_settled_due_amount = _get_due_settlement_paid_amount(due_settlement_amount, old_paid_amount)

    base_snapshot = _latest_non_settlement_payroll_snapshot(payroll.id, db)
    open_items = detect_payroll_discrepancies(payroll.employee_id, payroll.payroll_period_id, db)
    payable_amount = _money(_decimal(base_snapshot.get("payable_amount"), default=str(_decimal(payroll.net_salary))))

    payroll.paid_amount = _money(_decimal(payroll.paid_amount) - reversed_amount)
    new_settled_due_amount = _get_due_settlement_paid_amount(due_settlement_amount, _decimal(payroll.paid_amount))
    reversed_due_amount = _money(max(Decimal("0.00"), old_settled_due_amount - new_settled_due_amount))
    if employee is not None and reversed_due_amount > Decimal("0.00"):
        employee.dues = _money(_decimal(employee.dues) + reversed_due_amount)
        db.add(employee)
    payroll.status = "needs_review" if any(item.status == "open" for item in open_items) or (base_snapshot.get("needs_review_reasons") or []) else "draft"
    payroll.paid_at = None
    payroll.approved_at = None
    _sync_payroll_balance(payroll, payable_amount=payable_amount)

    period = db.get(PayrollPeriod, payroll.payroll_period_id)
    if period:
        _set_attendance_review_status_for_period(payroll.employee_id, period, "approved", db)

    reversal_record = Payments(
        employee_id=payroll.employee_id,
        employee_payroll_id=payroll.id,
        date=_utc_now(),
        amount=_money(-reversed_amount),
        payment_type=0,
        description=f"Payroll payment reversal for period #{payroll.payroll_period_id}: {reversal_reason}",
        start=period.start_date if period else None,
        end=period.end_date if period else None,
    )
    db.add(reversal_record)
    create_payroll_history_snapshot(
        payroll,
        old_gross_salary=_decimal(payroll.gross_salary),
        old_net_salary=_decimal(payroll.net_salary),
        reason="payroll_reopened",
        calculation_data_json={
            **base_snapshot,
            **{
                key: str(value)
                for key, value in _build_due_state_values(
                    employee_due_balance=_decimal(getattr(employee, "dues", 0)),
                    due_settlement_amount=due_settlement_amount,
                    paid_amount=_decimal(payroll.paid_amount),
                ).items()
            },
            "status_before": old_status,
            "status_after": payroll.status,
            "reversed_payment_amount": str(reversed_amount),
            "reversed_due_amount": str(reversed_due_amount),
            "old_paid_amount": str(old_paid_amount),
            "new_paid_amount": str(payroll.paid_amount),
            "old_balance_amount": str(old_balance_amount),
            "new_balance_amount": str(payroll.balance_amount),
            "old_paid_at": old_paid_at.isoformat() if old_paid_at else None,
            "old_approved_at": old_approved_at.isoformat() if old_approved_at else None,
            "reopen_reason": reversal_reason,
            "payable_amount": str(payable_amount),
        },
        db=db,
        created_by=reopened_by,
    )
    save_audit_log(
        db,
        action="payroll_reopened",
        entity_type="EmployeePayroll",
        entity_id=payroll.id,
        old_data_json={
            "status": old_status,
            "paid_amount": str(old_paid_amount),
            "balance_amount": str(old_balance_amount),
            "paid_at": old_paid_at.isoformat() if old_paid_at else None,
            "approved_at": old_approved_at.isoformat() if old_approved_at else None,
        },
        new_data_json={
            "status": payroll.status,
            "paid_amount": str(payroll.paid_amount),
            "balance_amount": str(payroll.balance_amount),
            "paid_at": None,
            "approved_at": None,
            "reversed_payment_amount": str(reversed_amount),
            "reopen_reason": reversal_reason,
        },
        user_id=reopened_by,
    )
    db.commit()
    db.refresh(payroll)
    _apply_payroll_snapshot_fields(payroll, base_snapshot)
    _apply_due_state_fields(payroll, db)
    return payroll


def mark_employee_payroll_paid(employee_payroll_id: int, db: Session, paid_by: int | None = None, amount=None, note: str | None = None):
    payroll = db.get(EmployeePayroll, employee_payroll_id)
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")

    open_high = [
        item
        for item in detect_payroll_discrepancies(payroll.employee_id, payroll.payroll_period_id, db)
        if item.status == "open" and item.severity == "high"
    ]
    if open_high:
        raise BadRequestException(
            "Resolve high-severity discrepancies before payment",
            message_key="errors.resolve_high_severity_before_payment",
        )

    old_status = payroll.status
    old_paid_amount = _decimal(payroll.paid_amount)
    old_balance_amount = _decimal(payroll.balance_amount)
    _sync_payroll_balance(payroll)
    latest_snapshot = _latest_payroll_snapshot(payroll.id, db)
    employee = db.get(Employees, payroll.employee_id)
    due_settlement_amount = _sum_adjustments_by_type(_load_adjustments(payroll.id, db), DUE_SETTLEMENT_ADJUSTMENT_TYPE)
    old_settled_due_amount = _get_due_settlement_paid_amount(due_settlement_amount, old_paid_amount)

    payment_amount = _money(_decimal(amount)) if amount is not None else payroll.balance_amount
    if payment_amount == Decimal("0.00"):
        raise BadRequestException("Payment amount cannot be zero", message_key="errors.payment_amount_zero")
    if payment_amount < Decimal("0.00"):
        raise BadRequestException("Payment amount cannot be negative", message_key="errors.payment_amount_negative")
    if payment_amount > payroll.balance_amount:
        raise BadRequestException("Payment amount cannot exceed the remaining payroll balance", message_key="errors.payment_amount_exceeds_balance")

    payroll.paid_amount = _money(payroll.paid_amount + payment_amount)
    new_settled_due_amount = _get_due_settlement_paid_amount(due_settlement_amount, _decimal(payroll.paid_amount))
    newly_settled_due_amount = _money(max(Decimal("0.00"), new_settled_due_amount - old_settled_due_amount))
    if employee is not None and newly_settled_due_amount > Decimal("0.00"):
        employee.dues = _money(max(Decimal("0.00"), _decimal(employee.dues) - newly_settled_due_amount))
        db.add(employee)
    _sync_payroll_balance(payroll)

    is_settled = payroll.balance_amount == Decimal("0.00")
    payroll.status = "locked" if is_settled else "partially_paid"
    payroll.paid_at = _utc_now()
    period = db.get(PayrollPeriod, payroll.payroll_period_id)
    if period:
        _set_attendance_review_status_for_period(payroll.employee_id, period, "locked", db)
    payment_record = Payments(
        employee_id=payroll.employee_id,
        employee_payroll_id=payroll.id,
        date=_utc_now(),
        amount=payment_amount,
        payment_type=0,
        description=note or f"Payroll payment for period #{payroll.payroll_period_id}",
        start=period.start_date if period else None,
        end=period.end_date if period else None,
    )
    db.add(payment_record)
    create_payroll_history_snapshot(
        payroll,
        old_gross_salary=_decimal(payroll.gross_salary),
        old_net_salary=_decimal(payroll.net_salary),
        reason="payroll_payment_recorded",
        calculation_data_json={
            **latest_snapshot,
            **{
                key: str(value)
                for key, value in _build_due_state_values(
                    employee_due_balance=_decimal(getattr(employee, "dues", 0)),
                    due_settlement_amount=due_settlement_amount,
                    paid_amount=_decimal(payroll.paid_amount),
                ).items()
            },
            "status_before": old_status,
            "status_after": payroll.status,
            "payment_amount": str(payment_amount),
            "newly_settled_due_amount": str(newly_settled_due_amount),
            "old_paid_amount": str(old_paid_amount),
            "new_paid_amount": str(payroll.paid_amount),
            "old_balance_amount": str(old_balance_amount),
            "new_balance_amount": str(payroll.balance_amount),
            "note": note,
        },
        db=db,
        created_by=paid_by,
    )
    save_audit_log(
        db,
        action="payroll_payment_recorded",
        entity_type="EmployeePayroll",
        entity_id=payroll.id,
        old_data_json={"status": old_status, "paid_amount": str(old_paid_amount), "balance_amount": str(old_balance_amount)},
        new_data_json={
            "status": payroll.status,
            "payment_amount": str(payment_amount),
            "paid_amount": str(payroll.paid_amount),
            "balance_amount": str(payroll.balance_amount),
            "note": note,
        },
        user_id=paid_by,
    )
    _notify_employee_payroll_status(
        payroll=payroll,
        notification_type="payroll_paid",
        title="Payroll payment recorded",
        message=f"A payroll payment of {payment_amount} was recorded for period #{payroll.payroll_period_id}. Remaining balance: {payroll.balance_amount}.",
        title_key="notifications.payroll_paid_title",
        message_key="notifications.payroll_paid_message",
        translation_params={
            "payment_amount": payment_amount,
            "period_id": payroll.payroll_period_id,
            "balance_amount": payroll.balance_amount,
        },
        actor_user_id=paid_by,
        db=db,
    )
    db.commit()
    db.refresh(payroll)
    _apply_due_state_fields(payroll, db)
    return payroll


def resolve_payroll_discrepancy(discrepancy_id: int, resolution_note: str, db: Session, resolved_by: int | None = None):
    discrepancy = db.get(PayrollDiscrepancy, discrepancy_id)
    if not discrepancy:
        raise ResourceNotFoundException("Payroll discrepancy")

    discrepancy.status = "resolved"
    discrepancy.resolution_note = resolution_note
    discrepancy.resolved_by = resolved_by
    discrepancy.resolved_at = _utc_now()
    save_audit_log(
        db,
        action="payroll_discrepancy_resolved",
        entity_type="PayrollDiscrepancy",
        entity_id=discrepancy.id,
        old_data_json={"status": "open"},
        new_data_json={"status": discrepancy.status, "resolution_note": resolution_note},
        user_id=resolved_by,
    )
    db.commit()
    db.refresh(discrepancy)
    return discrepancy


def add_payroll_adjustment(payload, db: Session):
    payroll = db.get(EmployeePayroll, payload.employee_payroll_id)
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")
    if payroll.employee_id != payload.employee_id:
        raise BadRequestException("Payroll row does not belong to the provided employee")
    if payroll.payroll_period_id != payload.payroll_period_id:
        raise BadRequestException("Payroll row does not belong to the provided payroll period")
    if payload.adjustment_type == DUE_SETTLEMENT_ADJUSTMENT_TYPE:
        _validate_due_settlement_amount(
            payroll=payroll,
            employee_id=payload.employee_id,
            amount=payload.amount,
            db=db,
        )

    adjustment = PayrollAdjustment(
        employee_payroll_id=payload.employee_payroll_id,
        payroll_period_id=payload.payroll_period_id,
        employee_id=payload.employee_id,
        adjustment_type=payload.adjustment_type,
        amount=payload.amount,
        reason=payload.reason,
        created_by=payload.created_by,
    )
    db.add(adjustment)
    db.flush()

    if payroll.status in FINAL_PAYROLL_STATUSES:
        period = db.get(PayrollPeriod, payroll.payroll_period_id)
        _upsert_discrepancy(
            payroll=payroll,
            period=period,
            employee_id=payroll.employee_id,
            discrepancy_type="attendance_changed_after_approval",
            description="Manual payroll adjustment added after payroll was finalized",
            severity="high",
            db=db,
        )
        db.commit()
        db.refresh(adjustment)
        return adjustment

    calculate_employee_payroll(
        employee_id=payroll.employee_id,
        payroll_period_id=payroll.payroll_period_id,
        db=db,
        reason="payroll_adjustment",
        created_by=payload.created_by,
        force_history=True,
    )
    save_audit_log(
        db,
        action="payroll_adjustment_created",
        entity_type="PayrollAdjustment",
        entity_id=adjustment.id,
        new_data_json={"adjustment_type": payload.adjustment_type, "amount": str(payload.amount), "reason": payload.reason},
        user_id=payload.created_by,
    )
    db.commit()
    db.refresh(adjustment)
    return adjustment


def get_payroll_adjustments(employee_payroll_id: int, db: Session):
    payroll = db.get(EmployeePayroll, employee_payroll_id)
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")
    return _load_adjustments(employee_payroll_id, db)


def _get_editable_payroll_for_adjustment(adjustment: PayrollAdjustment, db: Session) -> EmployeePayroll:
    payroll = db.get(EmployeePayroll, adjustment.employee_payroll_id)
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")
    period = db.get(PayrollPeriod, payroll.payroll_period_id)
    if payroll.status in FINAL_PAYROLL_STATUSES or (period and period.status in FINAL_PAYROLL_STATUSES):
        raise BadRequestException("Approved, paid, or locked payroll adjustments cannot be changed", message_key="errors.locked_adjustments_immutable")
    return payroll


def update_payroll_adjustment(adjustment_id: int, payload, db: Session, updated_by: int | None = None):
    adjustment = db.get(PayrollAdjustment, adjustment_id)
    if not adjustment:
        raise ResourceNotFoundException("Payroll adjustment")

    payroll = _get_editable_payroll_for_adjustment(adjustment, db)
    old_data = {
        "adjustment_type": adjustment.adjustment_type,
        "amount": str(adjustment.amount),
        "reason": adjustment.reason,
    }

    update_data = payload.model_dump(exclude_unset=True)
    next_adjustment_type = update_data.get("adjustment_type", adjustment.adjustment_type)
    next_amount = update_data.get("amount", adjustment.amount)
    if next_adjustment_type == DUE_SETTLEMENT_ADJUSTMENT_TYPE:
        _validate_due_settlement_amount(
            payroll=payroll,
            employee_id=adjustment.employee_id,
            amount=_decimal(next_amount),
            db=db,
            exclude_adjustment_id=adjustment.id,
        )
    for key, value in update_data.items():
        if value is not None:
            setattr(adjustment, key, value)

    db.add(adjustment)
    db.flush()
    calculate_employee_payroll(
        employee_id=payroll.employee_id,
        payroll_period_id=payroll.payroll_period_id,
        db=db,
        reason="payroll_adjustment_updated",
        created_by=updated_by,
        force_history=True,
    )
    save_audit_log(
        db,
        action="payroll_adjustment_updated",
        entity_type="PayrollAdjustment",
        entity_id=adjustment.id,
        old_data_json=old_data,
        new_data_json={
            "adjustment_type": adjustment.adjustment_type,
            "amount": str(adjustment.amount),
            "reason": adjustment.reason,
        },
        user_id=updated_by,
    )
    db.commit()
    db.refresh(adjustment)
    return adjustment


def delete_payroll_adjustment(adjustment_id: int, db: Session, deleted_by: int | None = None):
    adjustment = db.get(PayrollAdjustment, adjustment_id)
    if not adjustment:
        raise ResourceNotFoundException("Payroll adjustment")

    payroll = _get_editable_payroll_for_adjustment(adjustment, db)
    old_data = {
        "adjustment_type": adjustment.adjustment_type,
        "amount": str(adjustment.amount),
        "reason": adjustment.reason,
    }
    db.delete(adjustment)
    db.flush()
    calculate_employee_payroll(
        employee_id=payroll.employee_id,
        payroll_period_id=payroll.payroll_period_id,
        db=db,
        reason="payroll_adjustment_deleted",
        created_by=deleted_by,
        force_history=True,
    )
    save_audit_log(
        db,
        action="payroll_adjustment_deleted",
        entity_type="PayrollAdjustment",
        entity_id=adjustment_id,
        old_data_json=old_data,
        user_id=deleted_by,
    )
    db.commit()
    return {"deleted": True, "id": adjustment_id}


def _latest_payroll_snapshot(employee_payroll_id: int, db: Session) -> dict:
    history = db.scalar(
        select(PayrollCalculationHistory.calculation_data_json)
        .where(PayrollCalculationHistory.employee_payroll_id == employee_payroll_id)
        .order_by(PayrollCalculationHistory.created_at.desc(), PayrollCalculationHistory.id.desc())
    )
    return history or {}


def _hydrate_payroll_snapshot(payroll: EmployeePayroll, db: Session) -> EmployeePayroll:
    _apply_payroll_snapshot_fields(payroll, _latest_payroll_snapshot(payroll.id, db))
    return _apply_due_state_fields(payroll, db)


def _serialize_employee_payroll(payroll: EmployeePayroll) -> dict:
    return {
        "id": payroll.id,
        "payroll_period_id": payroll.payroll_period_id,
        "employee_id": payroll.employee_id,
        "salary_type": payroll.salary_type,
        "base_salary": _money(_decimal(payroll.base_salary)),
        "normal_amount": _money(_decimal(payroll.normal_amount)),
        "overtime_amount": _money(_decimal(payroll.overtime_amount)),
        "bonus_amount": _money(_decimal(payroll.bonus_amount)),
        "deduction_amount": _money(_decimal(payroll.deduction_amount)),
        "late_deduction_amount": _money(_decimal(payroll.late_deduction_amount)),
        "unpaid_vacation_deduction": _money(_decimal(payroll.unpaid_vacation_deduction)),
        "adjustment_amount": _money(_decimal(payroll.adjustment_amount)),
        "gross_salary": _money(_decimal(payroll.gross_salary)),
        "net_salary": _money(_decimal(payroll.net_salary)),
        "total_amount": _money(_decimal(payroll.total_amount)),
        "paid_amount": _money(_decimal(payroll.paid_amount)),
        "balance_amount": _money(_decimal(payroll.balance_amount)),
        "status": payroll.status,
        "calculated_at": payroll.calculated_at,
        "reviewed_at": payroll.reviewed_at,
        "approved_at": payroll.approved_at,
        "paid_at": payroll.paid_at,
        "notes": payroll.notes,
        "attendance_deduction_amount": _money(_decimal(getattr(payroll, "attendance_deduction_amount", None))),
        "manual_deduction_amount": _money(_decimal(getattr(payroll, "manual_deduction_amount", None))),
        "late_penalty_amount": _money(_decimal(getattr(payroll, "late_penalty_amount", None))),
        "due_settlement_amount": _money(_decimal(getattr(payroll, "due_settlement_amount", None))),
        "employee_due_balance": _money(_decimal(getattr(payroll, "employee_due_balance", None))),
        "settled_due_amount": _money(_decimal(getattr(payroll, "settled_due_amount", None))),
        "remaining_due_settlement_amount": _money(_decimal(getattr(payroll, "remaining_due_settlement_amount", None))),
        "remaining_due_balance_after_settlement": _money(_decimal(getattr(payroll, "remaining_due_balance_after_settlement", None))),
        "calculation_data_json": payroll.calculation_data_json or {},
        "needs_review_reason": getattr(payroll, "needs_review_reason", None),
    }


def get_payroll_period(period_id: int, db: Session, *, include_archived: bool = False):
    options = [
        selectinload(PayrollPeriod.payrolls).selectinload(EmployeePayroll.employee),
    ]
    if not include_archived:
        options.append(
            with_loader_criteria(
                EmployeePayroll,
                EmployeePayroll.employee.has(Employees.deleted_at.is_(None)),
                include_aliases=True,
            )
        )
    period = db.scalar(
        select(PayrollPeriod)
        .options(*options)
        .where(PayrollPeriod.id == period_id)
        .execution_options(populate_existing=True)
    )
    if not period:
        raise ResourceNotFoundException("Payroll period")
    for payroll in period.payrolls:
        _hydrate_payroll_snapshot(payroll, db)
    return period


def list_payroll_periods(db: Session):
    return db.scalars(
        select(PayrollPeriod)
        .order_by(PayrollPeriod.start_date.desc(), PayrollPeriod.id.desc())
    ).all()


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
    paid_amount = Decimal("0.00")
    balance_amount = Decimal("0.00")

    for payroll in payrolls:
        row_total = _money(_decimal(payroll.total_amount))
        if row_total == Decimal("0.00") and _decimal(payroll.net_salary) != Decimal("0.00"):
            row_total = _money(_decimal(payroll.net_salary))
        row_paid = _money(_decimal(payroll.paid_amount))
        row_balance = _money(row_total - row_paid)

        total_amount += row_total
        paid_amount += row_paid
        balance_amount += row_balance

        employee_name = getattr(payroll.employee, "fullname", None) or f"Employee #{payroll.employee_id}"
        employee_row = employees.setdefault(
            payroll.employee_id,
            {
                "employee_id": payroll.employee_id,
                "employee_name": employee_name,
                "total_amount": Decimal("0.00"),
                "paid_amount": Decimal("0.00"),
                "balance_amount": Decimal("0.00"),
                "payroll_count": 0,
            },
        )
        employee_row["total_amount"] += row_total
        employee_row["paid_amount"] += row_paid
        employee_row["balance_amount"] += row_balance
        employee_row["payroll_count"] += 1

    company_owes_employees = _money(sum((row["balance_amount"] for row in employees.values() if row["balance_amount"] > 0), Decimal("0.00")))
    employees_owe_company = _money(sum((abs(row["balance_amount"]) for row in employees.values() if row["balance_amount"] < 0), Decimal("0.00")))

    return {
        "period_id": period_id,
        "total_amount": _money(total_amount),
        "paid_amount": _money(paid_amount),
        "balance_amount": _money(balance_amount),
        "company_owes_employees": company_owes_employees,
        "employees_owe_company": employees_owe_company,
        "employees": [
            {
                **row,
                "total_amount": _money(row["total_amount"]),
                "paid_amount": _money(row["paid_amount"]),
                "balance_amount": _money(row["balance_amount"]),
            }
            for row in sorted(employees.values(), key=lambda item: (item["employee_name"].lower(), item["employee_id"]))
        ],
    }


def get_employee_payroll_history(employee_id: int, db: Session, page: int = 1, page_size: int = 20):
    employee = db.get(Employees, employee_id)
    if not employee or employee.deleted_at is not None:
        raise ResourceNotFoundException("Employee")

    safe_page = max(1, int(page or 1))
    safe_page_size = max(1, min(int(page_size or 20), 100))

    total_records = int(
        db.scalar(
            select(func.count(EmployeePayroll.id))
            .where(EmployeePayroll.employee_id == employee_id)
        )
        or 0
    )
    total_pages = (total_records + safe_page_size - 1) // safe_page_size if total_records else 0
    if total_pages and safe_page > total_pages:
        safe_page = total_pages

    summary_row = db.execute(
        select(
            func.coalesce(func.sum(EmployeePayroll.net_salary), 0),
            func.coalesce(func.sum(EmployeePayroll.total_amount), 0),
            func.coalesce(func.sum(EmployeePayroll.paid_amount), 0),
            func.coalesce(func.sum(EmployeePayroll.balance_amount), 0),
            func.count(EmployeePayroll.id),
        )
        .where(EmployeePayroll.employee_id == employee_id)
    ).one()

    payrolls = db.scalars(
        select(EmployeePayroll)
        .join(PayrollPeriod, EmployeePayroll.payroll_period_id == PayrollPeriod.id)
        .options(selectinload(EmployeePayroll.payroll_period))
        .where(EmployeePayroll.employee_id == employee_id)
        .order_by(PayrollPeriod.start_date.desc(), EmployeePayroll.id.desc())
        .offset((safe_page - 1) * safe_page_size if total_records else 0)
        .limit(safe_page_size)
    ).all()

    items: list[dict] = []
    for payroll in payrolls:
        hydrated = _hydrate_payroll_snapshot(payroll, db)
        items.append(
            {
                **_serialize_employee_payroll(hydrated),
                "period_name": hydrated.payroll_period.name,
                "period_start_date": hydrated.payroll_period.start_date,
                "period_end_date": hydrated.payroll_period.end_date,
            }
        )

    return {
        "employee_id": employee.id,
        "employee_name": employee.fullname,
        "employee_status": employee.status,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_records": total_records,
        "total_pages": total_pages,
        "summary": {
            "net_salary_total": _money(_decimal(summary_row[0])),
            "payable_total": _money(_decimal(summary_row[1])),
            "paid_amount_total": _money(_decimal(summary_row[2])),
            "remaining_amount_total": _money(_decimal(summary_row[3])),
            "payroll_count": int(summary_row[4] or 0),
        },
        "items": items,
    }


def get_employee_payroll_by_period(employee_id: int, period_id: int, db: Session):
    payroll = db.scalar(
        select(EmployeePayroll).where(
            EmployeePayroll.employee_id == employee_id,
            EmployeePayroll.payroll_period_id == period_id,
        )
    )
    if not payroll:
        payroll = calculate_employee_payroll(employee_id, period_id, db)
        db.commit()
        db.refresh(payroll)
    return _hydrate_payroll_snapshot(payroll, db)


def get_payroll_history(employee_payroll_id: int, db: Session):
    return db.scalars(
        select(PayrollCalculationHistory)
        .where(PayrollCalculationHistory.employee_payroll_id == employee_payroll_id)
        .order_by(PayrollCalculationHistory.created_at.desc(), PayrollCalculationHistory.id.desc())
    ).all()


def get_payroll_discrepancies(period_id: int, db: Session, *, include_archived: bool = False):
    reconcile_payroll_period_discrepancies(period_id, db)
    db.commit()
    query = (
        select(PayrollDiscrepancy)
        .join(Employees, PayrollDiscrepancy.employee_id == Employees.id)
        .where(PayrollDiscrepancy.payroll_period_id == period_id)
    )
    if not include_archived:
        query = query.where(Employees.deleted_at.is_(None))
    return db.scalars(query.order_by(PayrollDiscrepancy.created_at.desc(), PayrollDiscrepancy.id.desc())).all()


def sync_vacation_with_payroll(employee_id: int, start_date: date, end_date: date, db: Session, reason: str):
    current = start_date
    from app.services.attendance_calculation_service import calculate_attendance_day

    while current <= end_date:
        calculate_attendance_day(employee_id, current, db, trigger_reason=reason)
        current += timedelta(days=1)
