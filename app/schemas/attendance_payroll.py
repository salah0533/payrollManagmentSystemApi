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
    field_changed: str
    new_value: Optional[str] = None
    original_event_id: Optional[int] = None
    reason: str
    corrected_by: Optional[int] = None

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("reason is required")
        return value.strip()

    @field_validator("field_changed")
    @classmethod
    def validate_field_changed(cls, value: str) -> str:
        valid = {"check_in_time", "break_start_time", "break_end_time", "check_out_time", "status"}
        if value not in valid:
            raise ValueError(f"field_changed must be one of {sorted(valid)}")
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
    weekly_off_days: list[str] = Field(default_factory=lambda: ["friday"])
    timezone: str = "UTC"
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
    allowed_late_minutes: int = 0
    default_currency: str = "USD"
    significant_change_threshold: Decimal = Decimal("1.00")
    paid_vacation_counts_for_daily: bool = True
    overtime_enabled: bool = True
    late_makeup_enabled: bool = True
    late_deduction_enabled: bool = True
    auto_recalculate_draft_payroll: bool = True
    lock_payroll_after_payment: bool = True
    holidays_json: list[str] = Field(default_factory=list)


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
    status: str
    calculated_at: datetime
    reviewed_at: Optional[datetime]
    approved_at: Optional[datetime]
    paid_at: Optional[datetime]
    notes: Optional[str]

    model_config = {"from_attributes": True}


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
