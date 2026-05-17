from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions.base_exception import ConflictException, ResourceNotFoundException
from app.models.annual_vacation import AnnualVacations
from app.models.employees import Employees
from app.models.types.vacationStatus import VacationStatuses
from app.models.vacation import Vacation
from app.models.vacation_types import VacationTypes
from app.services.policy_service import get_or_create_payroll_policy


ANNUAL_VACATION_TYPE_CODES = {"paid", "annual", "annual_vacation", "yearly_vacation", "vacation"}


@dataclass(frozen=True)
class VacationLedgerEntry:
    id: int | None
    employee_id: int
    start_date: date
    end_date: date
    vacation_type: int
    vacation_status: int
    is_paid: bool


def _get_employee_or_404(employee_id: int, db: Session) -> Employees:
    employee = db.scalar(select(Employees).where(Employees.id == employee_id, Employees.deleted_at.is_(None)))
    if employee is None:
        raise ResourceNotFoundException("Employee", employee_id)
    return employee


def _get_employee_entitlements(employee_id: int, db: Session) -> dict[int, int]:
    rows = db.scalars(
        select(AnnualVacations).where(AnnualVacations.employee_id == employee_id)
    ).all()
    return {int(row.year): int(row.allowed_days) for row in rows if row.allowed_days is not None}


def _get_annual_vacation_type_ids(db: Session) -> set[int]:
    type_ids: set[int] = set()
    rows = db.execute(select(VacationTypes.id, VacationTypes.code, VacationTypes.vacation_type)).all()
    for type_id, code, label in rows:
        normalized_code = str(code or "").strip().lower()
        normalized_label = str(label or "").strip().lower()
        if normalized_code in ANNUAL_VACATION_TYPE_CODES or normalized_label in ANNUAL_VACATION_TYPE_CODES:
            type_ids.add(int(type_id))
    if not type_ids:
        type_ids.add(0)
    return type_ids


def _days_inclusive(start_date: date, end_date: date) -> int:
    return (end_date - start_date).days + 1


def _year_bounds(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def _get_carryover_expiry_date(policy, year: int) -> date | None:
    month = getattr(policy, "carryover_expiry_month", None)
    day = getattr(policy, "carryover_expiry_day", None)
    if month is None or day is None:
        return None
    try:
        return date(year, int(month), int(day))
    except ValueError:
        return None


def _vacation_counts_toward_balance(
    entry: VacationLedgerEntry,
    *,
    annual_type_ids: set[int],
    reserve_pending: bool,
) -> bool:
    if not entry.is_paid:
        return False
    if int(entry.vacation_type) not in annual_type_ids:
        return False
    if int(entry.vacation_status) == int(VacationStatuses.approved):
        return True
    return reserve_pending and int(entry.vacation_status) == int(VacationStatuses.pending)


def _load_ledger_entries(
    employee_id: int,
    db: Session,
    *,
    exclude_vacation_id: int | None = None,
    extra_entries: list[VacationLedgerEntry] | None = None,
) -> list[VacationLedgerEntry]:
    rows = db.scalars(select(Vacation).where(Vacation.employee_id == employee_id)).all()
    entries = [
        VacationLedgerEntry(
            id=row.id,
            employee_id=row.employee_id,
            start_date=row.start_date,
            end_date=row.end_date,
            vacation_type=row.vacation_type,
            vacation_status=row.vacation_status,
            is_paid=bool(row.is_paid),
        )
        for row in rows
        if exclude_vacation_id is None or row.id != exclude_vacation_id
    ]
    if extra_entries:
        entries.extend(extra_entries)
    return entries


def _resolve_entitlement_days(
    year: int,
    *,
    employee: Employees,
    employee_entitlements: dict[int, int],
) -> tuple[int, int | None, str]:
    if year in employee_entitlements:
        return employee_entitlements[year], year, "employee_year"

    eligible_previous_years = [configured_year for configured_year in employee_entitlements.keys() if configured_year <= year]
    if eligible_previous_years:
        source_year = max(eligible_previous_years)
        source = "employee_year" if source_year == year else "fallback_previous_employee_year"
        return employee_entitlements[source_year], source_year, source

    default_days = int(employee.vacation_days or 0)
    if default_days > 0 and not employee_entitlements:
        return default_days, None, "employee_default"

    return 0, None, "unconfigured"


def get_employee_vacation_balance(
    employee_id: int,
    db: Session,
    *,
    start_year: int | None = None,
    end_year: int | None = None,
    as_of: date | None = None,
    extra_entries: list[VacationLedgerEntry] | None = None,
    exclude_vacation_id: int | None = None,
):
    employee = _get_employee_or_404(employee_id, db)
    policy = get_or_create_payroll_policy(db)
    annual_type_ids = _get_annual_vacation_type_ids(db)
    employee_entitlements = _get_employee_entitlements(employee_id, db)
    ledger_entries = _load_ledger_entries(
        employee_id,
        db,
        exclude_vacation_id=exclude_vacation_id,
        extra_entries=extra_entries,
    )
    as_of_date = as_of or date.today()

    all_years: set[int] = {as_of_date.year}
    all_years.update(employee_entitlements.keys())
    for entry in ledger_entries:
        all_years.add(entry.start_date.year)
        all_years.add(entry.end_date.year)

    ledger_start_year = min(all_years) if all_years else as_of_date.year
    requested_start_year = start_year or ledger_start_year
    requested_end_year = end_year or max(all_years)
    if requested_end_year < requested_start_year:
        requested_start_year, requested_end_year = requested_end_year, requested_start_year

    year_metrics: dict[int, dict[str, int]] = {
        year: {
            "approved_days": 0,
            "approved_before_expiry_days": 0,
            "pending_days": 0,
            "pending_before_expiry_days": 0,
        }
        for year in range(ledger_start_year, requested_end_year + 1)
    }

    for entry in ledger_entries:
        if not entry.is_paid or int(entry.vacation_type) not in annual_type_ids:
            continue
        if int(entry.vacation_status) not in {int(VacationStatuses.approved), int(VacationStatuses.pending)}:
            continue

        current_year = entry.start_date.year
        while current_year <= entry.end_date.year:
            year_start, year_end = _year_bounds(current_year)
            segment_start = max(entry.start_date, year_start)
            segment_end = min(entry.end_date, year_end)
            if segment_start <= segment_end:
                total_days = _days_inclusive(segment_start, segment_end)
                expiry_date = _get_carryover_expiry_date(policy, current_year)
                if expiry_date is None:
                    before_expiry_days = total_days
                elif segment_start > expiry_date:
                    before_expiry_days = 0
                else:
                    before_expiry_days = _days_inclusive(segment_start, min(segment_end, expiry_date))

                metrics = year_metrics.setdefault(
                    current_year,
                    {
                        "approved_days": 0,
                        "approved_before_expiry_days": 0,
                        "pending_days": 0,
                        "pending_before_expiry_days": 0,
                    },
                )
                if int(entry.vacation_status) == int(VacationStatuses.approved):
                    metrics["approved_days"] += total_days
                    metrics["approved_before_expiry_days"] += before_expiry_days
                else:
                    metrics["pending_days"] += total_days
                    metrics["pending_before_expiry_days"] += before_expiry_days
            current_year += 1

    allow_carryover = bool(getattr(policy, "allow_vacation_carryover", True))
    max_carryover_days = getattr(policy, "max_vacation_carryover_days", None)
    reserve_pending = bool(getattr(policy, "reserve_vacation_days_on_pending", False))

    years: list[dict[str, object]] = []
    carryover_from_previous_year = 0
    for year in range(ledger_start_year, requested_end_year + 1):
        entitlement_days, source_year, source = _resolve_entitlement_days(
            year,
            employee=employee,
            employee_entitlements=employee_entitlements,
        )
        metrics = year_metrics.get(
            year,
            {
                "approved_days": 0,
                "approved_before_expiry_days": 0,
                "pending_days": 0,
                "pending_before_expiry_days": 0,
            },
        )
        pending_days = metrics["pending_days"]
        reserved_days = pending_days if reserve_pending else 0
        consumed_days = metrics["approved_days"] + reserved_days
        consumed_before_expiry_days = metrics["approved_before_expiry_days"] + (
            metrics["pending_before_expiry_days"] if reserve_pending else 0
        )

        carryover_used_days = min(carryover_from_previous_year, consumed_before_expiry_days)
        carryover_expiry_date = _get_carryover_expiry_date(policy, year)
        carryover_expired_days = 0
        active_carryover_days = carryover_from_previous_year
        if carryover_expiry_date is not None:
            if year < as_of_date.year or (year == as_of_date.year and as_of_date > carryover_expiry_date):
                carryover_expired_days = max(0, carryover_from_previous_year - carryover_used_days)
                active_carryover_days = carryover_from_previous_year - carryover_expired_days

        consumed_from_entitlement_days = max(0, consumed_days - carryover_used_days)
        remaining_entitlement_days = max(0, entitlement_days - consumed_from_entitlement_days)

        carryover_to_next_year = 0
        if allow_carryover:
            carryover_to_next_year = remaining_entitlement_days
            if max_carryover_days is not None:
                carryover_to_next_year = min(carryover_to_next_year, int(max_carryover_days))

        starting_balance_days = entitlement_days + active_carryover_days
        raw_available_days = starting_balance_days - consumed_days
        overdrawn_days = max(0, -raw_available_days)
        available_days = max(0, raw_available_days)

        years.append(
            {
                "year": year,
                "entitlement_days": entitlement_days,
                "entitlement_source_year": source_year,
                "entitlement_source": source,
                "carried_over_days": carryover_from_previous_year,
                "active_carryover_days": active_carryover_days,
                "carryover_used_days": carryover_used_days,
                "carryover_expired_days": carryover_expired_days,
                "carryover_expires_on": carryover_expiry_date.isoformat() if carryover_expiry_date else None,
                "starting_balance_days": starting_balance_days,
                "approved_days": metrics["approved_days"],
                "pending_request_days": pending_days,
                "reserved_days": reserved_days,
                "consumed_days": consumed_days,
                "remaining_entitlement_days": remaining_entitlement_days,
                "available_days": available_days,
                "overdrawn_days": overdrawn_days,
                "carryover_to_next_year": carryover_to_next_year,
            }
        )

        carryover_from_previous_year = carryover_to_next_year if allow_carryover else 0

    visible_years = [item for item in years if requested_start_year <= int(item["year"]) <= requested_end_year]
    current_year_balance = next((item for item in visible_years if int(item["year"]) == as_of_date.year), None)
    return {
        "employee_id": employee.id,
        "employee_name": employee.fullname,
        "as_of": as_of_date.isoformat(),
        "policy": {
            "allow_vacation_carryover": allow_carryover,
            "max_vacation_carryover_days": int(max_carryover_days) if max_carryover_days is not None else None,
            "carryover_expiry_month": getattr(policy, "carryover_expiry_month", None),
            "carryover_expiry_day": getattr(policy, "carryover_expiry_day", None),
            "reserve_vacation_days_on_pending": reserve_pending,
        },
        "current_year": as_of_date.year,
        "current_year_balance": current_year_balance,
        "years": visible_years,
    }


def ensure_vacation_balance_available(
    entry: VacationLedgerEntry,
    db: Session,
    *,
    exclude_vacation_id: int | None = None,
) -> None:
    policy = get_or_create_payroll_policy(db)
    annual_type_ids = _get_annual_vacation_type_ids(db)
    reserve_pending = bool(getattr(policy, "reserve_vacation_days_on_pending", False))
    if not _vacation_counts_toward_balance(entry, annual_type_ids=annual_type_ids, reserve_pending=reserve_pending):
        return

    balance = get_employee_vacation_balance(
        entry.employee_id,
        db,
        as_of=entry.end_date,
        extra_entries=[entry],
        exclude_vacation_id=exclude_vacation_id,
    )
    exceeded_years = [
        str(item["year"])
        for item in balance["years"]
        if int(item.get("overdrawn_days", 0) or 0) > 0
    ]
    if exceeded_years:
        years_label = ", ".join(exceeded_years)
        raise ConflictException(
            f"Vacation request exceeds the available annual balance for year(s): {years_label}",
            code="vacation_balance_exceeded",
        )
