from datetime import date, datetime, time
from decimal import Decimal
from calendar import monthrange
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.attendance_payroll import (
    DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE,
    MONTHLY_PAYROLL_CALCULATION_MODES,
)
from app.utility.reference_codes import ATTENDANCE_EVENT_TYPE_CODES, PAYROLL_ADJUSTMENT_TYPE_CODES

ATTENDANCE_EVENT_TYPES = set(ATTENDANCE_EVENT_TYPE_CODES)
PAYROLL_FINAL_STATUSES = {"approved", "paid", "locked"}


class AttendanceEventCreate(BaseModel):
    employee_id: int
    event_time: datetime
    source: str = "system"
    note: Optional[str] = None
    created_by: Optional[int] = None


class AttendanceActionRequest(BaseModel):
    employee_id: int
    event_time: Optional[datetime] = None
    source: str = "system"
    note: Optional[str] = None
    created_by: Optional[int] = None


class AttendanceCorrectionRequest(BaseModel):
    employee_id: int
    work_date: date
    correction_type: str = "field"
    field_changed: Optional[str] = None
    new_value: Optional[str] = None
    new_values_json: dict[str, Optional[str]] = Field(default_factory=dict)
    target_status: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)
    original_event_id: Optional[int] = None
    reason: str = ""
    corrected_by: Optional[int] = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("correction_type")
    @classmethod
    def validate_correction_type(cls, value: str) -> str:
        valid = {"field", "smart_status"}
        if value not in valid:
            raise ValueError(f"correction_type must be one of {sorted(valid)}")
        return value

    @field_validator("field_changed")
    @classmethod
    def validate_field_changed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        valid = {"check_in_time", "break_start_time", "break_end_time", "check_out_time", "status"}
        if value not in valid:
            raise ValueError(f"field_changed must be one of {sorted(valid)}")
        return value

    @field_validator("new_values_json")
    @classmethod
    def validate_new_values_json(cls, value: dict[str, Optional[str]]) -> dict[str, Optional[str]]:
        valid = {"check_in_time", "break_start_time", "break_end_time", "check_out_time"}
        invalid = sorted(key for key in value.keys() if key not in valid)
        if invalid:
            raise ValueError(f"new_values_json keys must be a subset of {sorted(valid)}")
        return value

    @model_validator(mode="after")
    def validate_correction_payload(self):
        if self.correction_type == "field" and not self.field_changed and not self.new_values_json:
            raise ValueError("field_changed or new_values_json is required for field corrections")
        if self.correction_type == "smart_status" and not self.target_status:
            raise ValueError("target_status is required for smart status corrections")
        return self


class AttendanceSmartCorrectionRequest(BaseModel):
    target_status: str
    reason: str = ""
    options: dict[str, Any] = Field(default_factory=dict)
    corrected_by: Optional[int] = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return (value or "").strip()


class AttendanceReviewRequest(BaseModel):
    review_status: str
    note: Optional[str] = None
    reviewed_by: Optional[int] = None

    @field_validator("review_status")
    @classmethod
    def validate_review_status(cls, value: str) -> str:
        valid = {"draft", "needs_review", "approved", "locked"}
        if value not in valid:
            raise ValueError(f"review_status must be one of {sorted(valid)}")
        return value


class AttendanceRecalculateResponse(BaseModel):
    employee_id: int
    start_date: date
    end_date: date
    recalculated_days: int


class AttendanceEventRead(BaseModel):
    id: int
    employee_id: int
    attendance_day_id: Optional[int]
    event_type: str
    event_time: datetime
    source: str
    note: Optional[str]
    created_at: datetime
    created_by: Optional[int]

    model_config = {"from_attributes": True}


class AttendanceDayRead(BaseModel):
    id: int
    employee_id: int
    work_date: date
    work_schedule_id: Optional[int]
    check_in_time: Optional[time]
    break_start_time: Optional[time]
    break_end_time: Optional[time]
    check_out_time: Optional[time]
    expected_work_minutes: int
    actual_work_minutes: int
    break_minutes: int
    normal_paid_minutes: int
    late_minutes: int
    early_leave_minutes: int
    late_makeup_minutes: int
    overtime_minutes: int
    absence_minutes: int
    unpaid_minutes: int
    status: str
    review_status: str
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[int]
    locked_at: Optional[datetime]
    is_manually_corrected: bool
    calculated_at: datetime
    created_at: datetime
    updated_at: datetime
    events: list[AttendanceEventRead] = []

    model_config = {"from_attributes": True}


class WorkSchedulePayload(BaseModel):
    name: str = "Default Schedule"
    start_time: time
    end_time: time
    break_start_time: Optional[time] = None
    break_end_time: Optional[time] = None
    break_minutes: int = 0
    weekly_off_days: list[str] = Field(default_factory=lambda: ["friday", "saturday"])
    timezone: str = "Africa/Algiers"
    is_default: bool = True

    @model_validator(mode="after")
    def validate_times(self):
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be after start_time")
        if self.break_minutes < 0:
            raise ValueError("break_minutes cannot be negative")

        has_break_start = self.break_start_time is not None
        has_break_end = self.break_end_time is not None
        if has_break_start != has_break_end:
            raise ValueError("break_start_time and break_end_time must both be provided together")

        if self.break_start_time and self.break_end_time:
            if self.break_start_time <= self.start_time:
                raise ValueError("break_start_time must be after start_time")
            if self.break_end_time >= self.end_time:
                raise ValueError("break_end_time must be before end_time")
            if self.break_start_time >= self.break_end_time:
                raise ValueError("break_end_time must be after break_start_time")

            break_start_dt = datetime.combine(date.today(), self.break_start_time)
            break_end_dt = datetime.combine(date.today(), self.break_end_time)
            self.break_minutes = int((break_end_dt - break_start_dt).total_seconds() // 60)
        else:
            total_shift_minutes = int(
                (datetime.combine(date.today(), self.end_time) - datetime.combine(date.today(), self.start_time)).total_seconds()
                // 60
            )
            if self.break_minutes >= total_shift_minutes:
                raise ValueError("break_minutes must be shorter than the scheduled shift")
        return self


class WorkScheduleRead(WorkSchedulePayload):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PayrollPolicyPayload(BaseModel):
    name: str = "default"
    payroll_cycle: str = "monthly"
    minimum_overtime_minutes: int = 30
    minimum_auto_pay_minutes: int = 0
    allowed_late_minutes: int = 0
    default_currency: str = "DZD"
    significant_change_threshold: Decimal = Decimal("1.00")
    paid_vacation_counts_for_daily: bool = True
    overtime_enabled: bool = True
    late_makeup_enabled: bool = True
    late_deduction_enabled: bool = False
    monthly_payroll_calculation_mode: str = DEFAULT_MONTHLY_PAYROLL_CALCULATION_MODE
    auto_recalculate_draft_payroll: bool = True
    lock_payroll_after_payment: bool = True
    annual_vacation_days_by_year: dict[str, int] = Field(default_factory=dict)
    allow_vacation_carryover: bool = True
    max_vacation_carryover_days: Optional[int] = None
    carryover_expiry_month: Optional[int] = None
    carryover_expiry_day: Optional[int] = None
    reserve_vacation_days_on_pending: bool = False

    @field_validator("default_currency")
    @classmethod
    def validate_default_currency(cls, value: str) -> str:
        normalized = value.upper().strip()
        if normalized == "ILS":
            raise ValueError("default_currency is not allowed")
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("default_currency must be a 3-letter ISO currency code")
        return normalized

    @field_validator("monthly_payroll_calculation_mode")
    @classmethod
    def validate_monthly_payroll_calculation_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in MONTHLY_PAYROLL_CALCULATION_MODES:
            raise ValueError(
                f"monthly_payroll_calculation_mode must be one of {sorted(MONTHLY_PAYROLL_CALCULATION_MODES)}"
            )
        return normalized

    @field_validator("annual_vacation_days_by_year", mode="before")
    @classmethod
    def normalize_annual_vacation_days_by_year(cls, value: Any) -> dict[str, int]:
        if value in (None, ""):
            return {}
        if not isinstance(value, dict):
            raise ValueError("annual_vacation_days_by_year must be an object keyed by year")

        normalized: dict[str, int] = {}
        for raw_year, raw_days in value.items():
            year = str(raw_year).strip()
            if not year.isdigit() or len(year) != 4:
                raise ValueError("annual_vacation_days_by_year keys must be 4-digit years")
            days = int(raw_days)
            if days <= 0:
                raise ValueError("annual vacation days must be greater than zero")
            normalized[year] = days
        return normalized

    @field_validator("max_vacation_carryover_days")
    @classmethod
    def validate_max_vacation_carryover_days(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 0:
            raise ValueError("max_vacation_carryover_days cannot be negative")
        return value

    @field_validator("carryover_expiry_month")
    @classmethod
    def validate_carryover_expiry_month(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and not 1 <= value <= 12:
            raise ValueError("carryover_expiry_month must be between 1 and 12")
        return value

    @field_validator("carryover_expiry_day")
    @classmethod
    def validate_carryover_expiry_day(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and not 1 <= value <= 31:
            raise ValueError("carryover_expiry_day must be between 1 and 31")
        return value

    @model_validator(mode="after")
    def validate_vacation_policy(self):
        if (self.carryover_expiry_month is None) != (self.carryover_expiry_day is None):
            raise ValueError("carryover_expiry_month and carryover_expiry_day must both be provided together")

        if self.carryover_expiry_month is not None and self.carryover_expiry_day is not None:
            max_day = monthrange(2025, self.carryover_expiry_month)[1]
            if self.carryover_expiry_day > max_day:
                raise ValueError("carryover_expiry_day is not valid for the selected month")

        if not self.allow_vacation_carryover:
            self.max_vacation_carryover_days = None
            self.carryover_expiry_month = None
            self.carryover_expiry_day = None

        return self


class PayrollPolicyRead(PayrollPolicyPayload):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PayrollAdjustmentCreate(BaseModel):
    employee_payroll_id: int
    payroll_period_id: int
    employee_id: int
    adjustment_type: str
    amount: Decimal
    reason: str
    created_by: Optional[int] = None

    @field_validator("adjustment_type")
    @classmethod
    def validate_adjustment_type(cls, value: str) -> str:
        valid = set(PAYROLL_ADJUSTMENT_TYPE_CODES)
        if value not in valid:
            raise ValueError(f"adjustment_type must be one of {sorted(valid)}")
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Decimal) -> Decimal:
        if value <= 0:
            raise ValueError("amount must be greater than zero")
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("reason is required")
        return value.strip()


class PayrollAdjustmentUpdate(BaseModel):
    adjustment_type: Optional[str] = None
    amount: Optional[Decimal] = None
    reason: Optional[str] = None

    @field_validator("adjustment_type")
    @classmethod
    def validate_adjustment_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        valid = set(PAYROLL_ADJUSTMENT_TYPE_CODES)
        if value not in valid:
            raise ValueError(f"adjustment_type must be one of {sorted(valid)}")
        return value

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        if value is not None and value <= 0:
            raise ValueError("amount must be greater than zero")
        return value

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("reason cannot be empty")
        return value.strip()


class PayrollAdjustmentRead(BaseModel):
    id: int
    employee_payroll_id: int
    payroll_period_id: int
    employee_id: int
    adjustment_type: str
    amount: Decimal
    reason: str
    created_by: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class PayrollPaymentRequest(BaseModel):
    amount: Optional[Decimal] = None
    note: Optional[str] = None


class PayrollReopenRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("reason is required")
        return value.strip()


class PayrollDiscrepancyResolveRequest(BaseModel):
    resolution_note: str
    resolved_by: Optional[int] = None


class EmployeePayrollRead(BaseModel):
    id: int
    payroll_period_id: int
    employee_id: int
    salary_type: str
    base_salary: Decimal
    normal_amount: Decimal
    overtime_amount: Decimal
    bonus_amount: Decimal
    deduction_amount: Decimal
    late_deduction_amount: Decimal
    unpaid_vacation_deduction: Decimal
    adjustment_amount: Decimal
    gross_salary: Decimal
    net_salary: Decimal
    total_amount: Decimal
    paid_amount: Decimal
    balance_amount: Decimal
    status: str
    calculated_at: datetime
    reviewed_at: Optional[datetime]
    approved_at: Optional[datetime]
    paid_at: Optional[datetime]
    notes: Optional[str]
    attendance_deduction_amount: Decimal = Decimal("0.00")
    manual_deduction_amount: Decimal = Decimal("0.00")
    late_penalty_amount: Decimal = Decimal("0.00")
    calculation_data_json: dict[str, Any] = Field(default_factory=dict)
    needs_review_reason: Optional[str] = None

    model_config = {"from_attributes": True}


class PayrollEmployeeBalanceRead(BaseModel):
    employee_id: int
    employee_name: str
    total_amount: Decimal
    paid_amount: Decimal
    balance_amount: Decimal
    payroll_count: int


class PayrollBalanceReportRead(BaseModel):
    period_id: Optional[int] = None
    total_amount: Decimal
    paid_amount: Decimal
    balance_amount: Decimal
    company_owes_employees: Decimal
    employees_owe_company: Decimal
    employees: list[PayrollEmployeeBalanceRead]


class PayrollEmployeeHistorySummaryRead(BaseModel):
    net_salary_total: Decimal
    payable_total: Decimal
    paid_amount_total: Decimal
    remaining_amount_total: Decimal
    payroll_count: int


class PayrollEmployeeHistoryItemRead(EmployeePayrollRead):
    period_name: str
    period_start_date: date
    period_end_date: date


class PayrollEmployeeHistoryRead(BaseModel):
    employee_id: int
    employee_name: str
    employee_status: str
    page: int
    page_size: int
    total_records: int
    total_pages: int
    summary: PayrollEmployeeHistorySummaryRead
    items: list[PayrollEmployeeHistoryItemRead] = []


class PayrollPeriodRead(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    status: str
    generated_at: datetime
    reviewed_at: Optional[datetime]
    approved_at: Optional[datetime]
    approved_by: Optional[int]
    paid_at: Optional[datetime]
    locked_at: Optional[datetime]
    payrolls: list[EmployeePayrollRead] = []

    model_config = {"from_attributes": True}


class PayrollPeriodSummaryRead(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    status: str
    generated_at: datetime
    reviewed_at: Optional[datetime]
    approved_at: Optional[datetime]
    approved_by: Optional[int]
    paid_at: Optional[datetime]
    locked_at: Optional[datetime]

    model_config = {"from_attributes": True}


class PayrollDiscrepancyRead(BaseModel):
    id: int
    employee_payroll_id: Optional[int]
    payroll_period_id: int
    employee_id: int
    discrepancy_type: str
    description: str
    severity: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    resolved_by: Optional[int]
    resolution_note: Optional[str]

    model_config = {"from_attributes": True}


class PayrollHistoryRead(BaseModel):
    id: int
    employee_payroll_id: int
    payroll_period_id: int
    employee_id: int
    old_gross_salary: Optional[Decimal]
    new_gross_salary: Decimal
    old_net_salary: Optional[Decimal]
    new_net_salary: Decimal
    reason: str
    calculation_data_json: dict[str, Any]
    created_at: datetime
    created_by: Optional[int]

    model_config = {"from_attributes": True}


class AuditLogRead(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    entity_type: str
    entity_id: Optional[int]
    old_data_json: Optional[dict[str, Any]]
    new_data_json: Optional[dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
