from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

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
    target_status: Optional[str] = None
    options: dict[str, Any] = Field(default_factory=dict)
    original_event_id: Optional[int] = None
    reason: str
    corrected_by: Optional[int] = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("reason is required")
        return value.strip()

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

    @model_validator(mode="after")
    def validate_correction_payload(self):
        if self.correction_type == "field" and not self.field_changed:
            raise ValueError("field_changed is required for field corrections")
        if self.correction_type == "smart_status" and not self.target_status:
            raise ValueError("target_status is required for smart status corrections")
        return self


class AttendanceSmartCorrectionRequest(BaseModel):
    target_status: str
    reason: str
    options: dict[str, Any] = Field(default_factory=dict)
    corrected_by: Optional[int] = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("reason is required")
        return value.strip()


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
    break_minutes: int = 0
    weekly_off_days: list[str] = Field(default_factory=lambda: ["friday", "saturday"])
    timezone: str = "Africa/Algiers"
    is_default: bool = True

    @model_validator(mode="after")
    def validate_times(self):
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be after start_time")
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
    auto_recalculate_draft_payroll: bool = True
    lock_payroll_after_payment: bool = True
    holidays_json: list[str] = Field(default_factory=list)

    @field_validator("default_currency")
    @classmethod
    def validate_default_currency(cls, value: str) -> str:
        normalized = value.upper().strip()
        if normalized == "ILS":
            raise ValueError("default_currency is not allowed")
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValueError("default_currency must be a 3-letter ISO currency code")
        return normalized


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
