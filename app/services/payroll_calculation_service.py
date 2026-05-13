import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.exceptions.base_exception import BadRequestException, ResourceNotFoundException
from app.models.attendance_payroll import (
    AttendanceDay,
    EmployeePayroll,
    PayrollAdjustment,
    PayrollCalculationHistory,
    PayrollDiscrepancy,
    PayrollPeriod,
)
from app.models.auth import User
from app.models.employees import Employees
from app.models.types.vacationStatus import VacationStatuses
from app.models.vacation import Vacation
from app.services.notification_service import NotificationService
from app.services.policy_service import (
    WEEKDAY_NAMES,
    get_employee_compensation,
    get_employee_schedule,
    get_or_create_payroll_policy,
    get_working_days,
    parse_holidays,
    save_audit_log,
)


FINAL_PAYROLL_STATUSES = {"approved", "paid", "locked"}
RECALCULABLE_PAYROLL_STATUSES = {"draft", "needs_review"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _decimal(value, default: str = "0.00") -> Decimal:
    if value is None:
        return Decimal(default)
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_employee_user_id(employee_id: int, db: Session) -> int | None:
    return db.scalar(select(User.id).where(User.employee_id == employee_id, User.deleted_at.is_(None)))


def _notify_payroll_backoffice_status(payroll: EmployeePayroll, db: Session) -> None:
    service = NotificationService(db)
    if payroll.status == "needs_review":
        notification_type = "payroll_needs_review"
        title = "Payroll needs review"
        message = f"Payroll for employee #{payroll.employee_id} in period #{payroll.payroll_period_id} needs review."
    elif payroll.status == "draft":
        notification_type = "payroll_draft_ready"
        title = "Payroll draft ready"
        message = f"Payroll draft for employee #{payroll.employee_id} in period #{payroll.payroll_period_id} is ready."
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
        entity_type="employee_payroll",
        entity_id=payroll.id,
        actor_user_id=actor_user_id,
        priority="normal",
    )


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
    schedule = get_employee_schedule(payroll.employee_id, period.start_date, db)
    compensation = get_employee_compensation(payroll.employee_id, period.end_date, db)
    holidays = parse_holidays(policy.holidays_json)
    working_days = get_working_days(period.start_date, period.end_date, schedule, holidays)
    expected_day_minutes = max(
        1,
        int((datetime.combine(date.today(), schedule.end_time) - datetime.combine(date.today(), schedule.start_time)).total_seconds() // 60)
        - int(schedule.break_minutes or 0),
    )
    summary = _attendance_summary(days, expected_day_minutes)

    daily_rate = _decimal(compensation.daily_rate)
    if daily_rate == Decimal("0.00") and working_days:
        daily_rate = _decimal(compensation.base_monthly_salary) / Decimal(len(working_days))
    per_minute_rate = daily_rate / Decimal(expected_day_minutes)

    recorded_dates = {item.work_date for item in days}
    missing_workdays = [day for day in working_days if day not in recorded_dates]
    unpaid_missing_minutes = len(missing_workdays) * expected_day_minutes

    base_salary = _money(_decimal(compensation.base_monthly_salary))
    absence_deduction = _money(per_minute_rate * Decimal(summary["absence_minutes"] + unpaid_missing_minutes))
    unpaid_vacation_deduction = _money(per_minute_rate * Decimal(sum(day.expected_work_minutes for day in days if day.status == "unpaid_vacation")))
    unrecovered_late_minutes = max(0, summary["late_minutes"] + summary["early_leave_minutes"] - summary["late_makeup_minutes"])
    late_deduction_rate = _decimal(compensation.late_deduction_rate) if policy.late_deduction_enabled else Decimal("0.00")
    late_deduction_amount = _money(late_deduction_rate * Decimal(unrecovered_late_minutes))
    payable_overtime_minutes = summary["overtime_minutes"] if summary["overtime_minutes"] >= int(policy.minimum_overtime_minutes or 0) else 0
    overtime_amount = _money((_decimal(compensation.overtime_rate) / Decimal("60")) * Decimal(payable_overtime_minutes)) if policy.overtime_enabled else Decimal("0.00")

    adjustments = _load_adjustments(payroll.id, db)
    bonus_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "bonus"), Decimal("0.00")))
    manual_deduction_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "deduction"), Decimal("0.00")))
    correction_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "correction"), Decimal("0.00")))

    normal_amount = base_salary
    gross_salary = _money(normal_amount + overtime_amount + bonus_amount + correction_amount)
    deduction_amount = _money(absence_deduction + manual_deduction_amount)
    net_salary = _money(gross_salary - deduction_amount - late_deduction_amount - unpaid_vacation_deduction)

    calc_data = {
        **summary,
        "missing_attendance_days": len(missing_workdays),
        "base_salary": str(base_salary),
        "normal_amount": str(normal_amount),
        "overtime_amount": str(overtime_amount),
        "payable_overtime_minutes": payable_overtime_minutes,
        "bonus_amount": str(bonus_amount),
        "deduction_amount": str(deduction_amount),
        "late_deduction_amount": str(late_deduction_amount),
        "unpaid_vacation_deduction": str(unpaid_vacation_deduction),
        "adjustment_amount": str(correction_amount),
        "gross_salary": str(gross_salary),
        "net_salary": str(net_salary),
    }
    return {
        "salary_type": compensation.salary_type,
        "base_salary": base_salary,
        "normal_amount": normal_amount,
        "overtime_amount": overtime_amount,
        "bonus_amount": bonus_amount,
        "deduction_amount": deduction_amount,
        "late_deduction_amount": late_deduction_amount,
        "unpaid_vacation_deduction": unpaid_vacation_deduction,
        "adjustment_amount": correction_amount,
        "gross_salary": gross_salary,
        "net_salary": net_salary,
        "calculation_data_json": calc_data,
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
    bonus_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "bonus"), Decimal("0.00")))
    deduction_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "deduction"), Decimal("0.00")))
    correction_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "correction"), Decimal("0.00")))

    gross_salary = _money(normal_amount + overtime_amount + bonus_amount + correction_amount)
    net_salary = _money(gross_salary - deduction_amount)
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
        "deduction_amount": str(deduction_amount),
        "adjustment_amount": str(correction_amount),
        "gross_salary": str(gross_salary),
        "net_salary": str(net_salary),
    }
    return {
        "salary_type": compensation.salary_type,
        "base_salary": Decimal("0.00"),
        "normal_amount": normal_amount,
        "overtime_amount": overtime_amount,
        "bonus_amount": bonus_amount,
        "deduction_amount": deduction_amount,
        "late_deduction_amount": Decimal("0.00"),
        "unpaid_vacation_deduction": Decimal("0.00"),
        "adjustment_amount": correction_amount,
        "gross_salary": gross_salary,
        "net_salary": net_salary,
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
    bonus_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "bonus"), Decimal("0.00")))
    deduction_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "deduction"), Decimal("0.00")))
    correction_amount = _money(sum((_decimal(item.amount) for item in adjustments if item.adjustment_type == "correction"), Decimal("0.00")))

    gross_salary = _money(normal_amount + overtime_amount + bonus_amount + correction_amount)
    net_salary = _money(gross_salary - deduction_amount)
    calc_data = {
        **summary,
        "base_salary": "0.00",
        "normal_amount": str(normal_amount),
        "overtime_amount": str(overtime_amount),
        "payable_overtime_minutes": payable_overtime_minutes,
        "bonus_amount": str(bonus_amount),
        "deduction_amount": str(deduction_amount),
        "adjustment_amount": str(correction_amount),
        "gross_salary": str(gross_salary),
        "net_salary": str(net_salary),
    }
    return {
        "salary_type": compensation.salary_type,
        "base_salary": Decimal("0.00"),
        "normal_amount": normal_amount,
        "overtime_amount": overtime_amount,
        "bonus_amount": bonus_amount,
        "deduction_amount": deduction_amount,
        "late_deduction_amount": Decimal("0.00"),
        "unpaid_vacation_deduction": Decimal("0.00"),
        "adjustment_amount": correction_amount,
        "gross_salary": gross_salary,
        "net_salary": net_salary,
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
    if not notification_service.notification_exists(
        notification_type="payroll_discrepancy_detected",
        entity_type="payroll_discrepancy",
        entity_id=discrepancy.id,
    ):
        notification_service.notify_role(
            role_codes=["hr", "admin"],
            notification_type="payroll_discrepancy_detected",
            title="Payroll discrepancy detected",
            message=description,
            entity_type="payroll_discrepancy",
            entity_id=discrepancy.id,
            priority="high",
            skip_if_no_recipients=True,
        )
    return discrepancy


def detect_payroll_discrepancies(employee_id: int, payroll_period_id: int, db: Session):
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")

    payroll = _get_employee_payroll(employee_id, payroll_period_id, db)
    schedule = get_employee_schedule(employee_id, period.start_date, db)
    policy = get_or_create_payroll_policy(db)
    holidays = parse_holidays(policy.holidays_json)
    working_days = get_working_days(period.start_date, period.end_date, schedule, holidays)
    days = _load_period_attendance(employee_id, period, db)
    days_by_date = {item.work_date: item for item in days}

    for work_day in working_days:
        day = days_by_date.get(work_day)
        if not day:
            _upsert_discrepancy(
                payroll=payroll,
                period=period,
                employee_id=employee_id,
                discrepancy_type="missing_attendance",
                description=f"Missing attendance snapshot for {work_day.isoformat()}",
                severity="medium",
                db=db,
            )
            continue

        if day.status == "incomplete":
            discrepancy_type = "missing_checkout" if day.check_in_time and not day.check_out_time else "missing_checkin"
            _upsert_discrepancy(
                payroll=payroll,
                period=period,
                employee_id=employee_id,
                discrepancy_type=discrepancy_type,
                description=f"Incomplete attendance on {work_day.isoformat()}",
                severity="high",
                db=db,
            )

    vacations = db.scalars(
        select(Vacation).where(
            Vacation.employee_id == employee_id,
            Vacation.vacation_status == int(VacationStatuses.approved),
            Vacation.start_date <= period.end_date,
            Vacation.end_date >= period.start_date,
        )
    ).all()
    for vacation in vacations:
        current = max(vacation.start_date, period.start_date)
        last = min(vacation.end_date, period.end_date)
        while current <= last:
            day = days_by_date.get(current)
            if day and (day.check_in_time or day.check_out_time):
                _upsert_discrepancy(
                    payroll=payroll,
                    period=period,
                    employee_id=employee_id,
                    discrepancy_type="vacation_overlap",
                    description=f"Vacation overlaps attendance on {current.isoformat()}",
                    severity="medium",
                    db=db,
                )
            current += timedelta(days=1)

    return db.scalars(
        select(PayrollDiscrepancy)
        .where(
            PayrollDiscrepancy.payroll_period_id == payroll_period_id,
            PayrollDiscrepancy.employee_id == employee_id,
        )
        .order_by(PayrollDiscrepancy.created_at.desc(), PayrollDiscrepancy.id.desc())
    ).all()


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
        raise BadRequestException("Approved or paid payroll cannot be recalculated")

    old_gross_salary = _decimal(payroll.gross_salary)
    old_net_salary = _decimal(payroll.net_salary)
    days = _load_period_attendance(employee_id, period, db)
    compensation = get_employee_compensation(employee_id, period.end_date, db)

    if compensation.salary_type == "monthly":
        results = calculate_monthly_employee_payroll(payroll, period, days, db)
    elif compensation.salary_type == "daily":
        results = calculate_daily_employee_payroll(payroll, period, days, db)
    else:
        results = calculate_hourly_employee_payroll(payroll, period, days, db)

    for field_name, value in results.items():
        if field_name == "calculation_data_json":
            continue
        setattr(payroll, field_name, value)

    payroll.status = "draft"
    payroll.calculated_at = _utc_now()
    db.add(payroll)
    db.flush()

    discrepancies = detect_payroll_discrepancies(employee_id, payroll_period_id, db)
    if any(item.status == "open" and item.severity == "high" for item in discrepancies):
        payroll.status = "needs_review"
    elif any(item.status == "open" for item in discrepancies):
        payroll.status = "needs_review"

    threshold = _decimal(get_or_create_payroll_policy(db).significant_change_threshold)
    has_meaningful_change = abs(payroll.net_salary - old_net_salary) >= threshold or abs(payroll.gross_salary - old_gross_salary) >= threshold
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
        old_data_json={"gross_salary": str(old_gross_salary), "net_salary": str(old_net_salary)},
        new_data_json={"gross_salary": str(payroll.gross_salary), "net_salary": str(payroll.net_salary), "reason": reason},
        user_id=created_by,
    )
    db.flush()
    _notify_payroll_backoffice_status(payroll, db)
    return payroll


def recalculate_payroll_period(payroll_period_id: int, db: Session, created_by: int | None = None):
    period = db.get(PayrollPeriod, payroll_period_id)
    if not period:
        raise ResourceNotFoundException("Payroll period")
    if period.status in FINAL_PAYROLL_STATUSES:
        raise BadRequestException("Approved or paid payroll period cannot be recalculated")

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

    db.commit()
    for payroll in payrolls:
        db.refresh(payroll)
    return payrolls


def sync_payroll_with_attendance_day(day: AttendanceDay, db: Session, trigger_reason: str = "attendance_change"):
    period = get_or_create_payroll_period_for_date(day.work_date, db)
    payroll = _get_employee_payroll(day.employee_id, period.id, db)
    policy = get_or_create_payroll_policy(db)

    if payroll.status in FINAL_PAYROLL_STATUSES or period.status in FINAL_PAYROLL_STATUSES:
        _upsert_discrepancy(
            payroll=payroll,
            period=period,
            employee_id=day.employee_id,
            discrepancy_type="attendance_changed_after_approval",
            description=f"Attendance changed on {day.work_date.isoformat()} after payroll was finalized",
            severity="high",
            db=db,
        )
        return payroll

    if not policy.auto_recalculate_draft_payroll:
        return payroll

    force_history = trigger_reason in {"attendance_correction", "vacation_approved", "vacation_rejected", "payroll_adjustment"}
    return calculate_employee_payroll(
        employee_id=day.employee_id,
        payroll_period_id=period.id,
        db=db,
        reason=trigger_reason,
        force_history=force_history,
    )


def approve_employee_payroll(employee_payroll_id: int, db: Session, approved_by: int | None = None):
    payroll = db.scalar(
        select(EmployeePayroll)
        .options(selectinload(EmployeePayroll.discrepancies))
        .where(EmployeePayroll.id == employee_payroll_id)
    )
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")

    open_high = [item for item in payroll.discrepancies if item.status == "open" and item.severity == "high"]
    if open_high:
        raise BadRequestException("Resolve high-severity discrepancies before approval")

    old_status = payroll.status
    payroll.status = "approved"
    payroll.approved_at = _utc_now()
    create_payroll_history_snapshot(
        payroll,
        old_gross_salary=_decimal(payroll.gross_salary),
        old_net_salary=_decimal(payroll.net_salary),
        reason="payroll_approved",
        calculation_data_json={"status_before": old_status, "status_after": payroll.status},
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
        actor_user_id=approved_by,
        db=db,
    )
    db.commit()
    db.refresh(payroll)
    return payroll


def mark_employee_payroll_paid(employee_payroll_id: int, db: Session, paid_by: int | None = None):
    payroll = db.get(EmployeePayroll, employee_payroll_id)
    if not payroll:
        raise ResourceNotFoundException("Employee payroll")

    old_status = payroll.status
    policy = get_or_create_payroll_policy(db)
    payroll.status = "locked" if policy.lock_payroll_after_payment else "paid"
    payroll.paid_at = _utc_now()
    create_payroll_history_snapshot(
        payroll,
        old_gross_salary=_decimal(payroll.gross_salary),
        old_net_salary=_decimal(payroll.net_salary),
        reason="payroll_paid",
        calculation_data_json={"status_before": old_status, "status_after": payroll.status},
        db=db,
        created_by=paid_by,
    )
    save_audit_log(
        db,
        action="payroll_paid",
        entity_type="EmployeePayroll",
        entity_id=payroll.id,
        old_data_json={"status": old_status},
        new_data_json={"status": payroll.status},
        user_id=paid_by,
    )
    _notify_employee_payroll_status(
        payroll=payroll,
        notification_type="payroll_paid",
        title="Payroll paid",
        message=f"Your payroll for period #{payroll.payroll_period_id} was marked as paid.",
        actor_user_id=paid_by,
        db=db,
    )
    db.commit()
    db.refresh(payroll)
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


def get_payroll_period(period_id: int, db: Session):
    period = db.scalar(
        select(PayrollPeriod)
        .options(selectinload(PayrollPeriod.payrolls))
        .where(PayrollPeriod.id == period_id)
    )
    if not period:
        raise ResourceNotFoundException("Payroll period")
    return period


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
    return payroll


def get_payroll_history(employee_payroll_id: int, db: Session):
    return db.scalars(
        select(PayrollCalculationHistory)
        .where(PayrollCalculationHistory.employee_payroll_id == employee_payroll_id)
        .order_by(PayrollCalculationHistory.created_at.desc(), PayrollCalculationHistory.id.desc())
    ).all()


def get_payroll_discrepancies(period_id: int, db: Session):
    return db.scalars(
        select(PayrollDiscrepancy)
        .where(PayrollDiscrepancy.payroll_period_id == period_id)
        .order_by(PayrollDiscrepancy.created_at.desc(), PayrollDiscrepancy.id.desc())
    ).all()


def sync_vacation_with_payroll(employee_id: int, start_date: date, end_date: date, db: Session, reason: str):
    current = start_date
    from app.services.attendance_calculation_service import calculate_attendance_day

    while current <= end_date:
        calculate_attendance_day(employee_id, current, db, trigger_reason=reason)
        current += timedelta(days=1)
