from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time
from sqlalchemy.orm import relationship

from app.db.base import Base


def utc_now():
    return datetime.now(timezone.utc)


class EmployeeCompensation(Base):
    __tablename__ = "employee_compensation"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    salary_type = Column(String(20), nullable=False)
    base_monthly_salary = Column(Numeric(12, 2), nullable=True)
    daily_rate = Column(Numeric(12, 2), nullable=True)
    hourly_rate = Column(Numeric(12, 2), nullable=True)
    overtime_rate = Column(Numeric(12, 2), nullable=True)
    late_deduction_rate = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=False, default="USD")
    effective_from = Column(Date, nullable=False, index=True)
    effective_to = Column(Date, nullable=True, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(Integer, nullable=True)

    employee = relationship("Employees")


class WorkSchedule(Base):
    __tablename__ = "work_schedule"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_minutes = Column(Integer, nullable=False, default=0)
    weekly_off_days = Column(JSON, nullable=False, default=list)
    timezone = Column(String(64), nullable=False, default="UTC")
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class PayrollPolicy(Base):
    __tablename__ = "payroll_policy"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, default="default")
    payroll_cycle = Column(String(20), nullable=False, default="monthly")
    minimum_overtime_minutes = Column(Integer, nullable=False, default=30)
    allowed_late_minutes = Column(Integer, nullable=False, default=0)
    default_currency = Column(String(10), nullable=False, default="USD")
    significant_change_threshold = Column(Numeric(12, 2), nullable=False, default=1)
    paid_vacation_counts_for_daily = Column(Boolean, nullable=False, default=True)
    overtime_enabled = Column(Boolean, nullable=False, default=True)
    late_makeup_enabled = Column(Boolean, nullable=False, default=True)
    late_deduction_enabled = Column(Boolean, nullable=False, default=True)
    auto_recalculate_draft_payroll = Column(Boolean, nullable=False, default=True)
    lock_payroll_after_payment = Column(Boolean, nullable=False, default=True)
    holidays_json = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class AttendanceDay(Base):
    __tablename__ = "attendance_day"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    work_schedule_id = Column(Integer, ForeignKey("work_schedule.id"), nullable=True)
    check_in_time = Column(Time, nullable=True)
    break_start_time = Column(Time, nullable=True)
    break_end_time = Column(Time, nullable=True)
    check_out_time = Column(Time, nullable=True)
    expected_work_minutes = Column(Integer, nullable=False, default=0)
    actual_work_minutes = Column(Integer, nullable=False, default=0)
    break_minutes = Column(Integer, nullable=False, default=0)
    normal_paid_minutes = Column(Integer, nullable=False, default=0)
    late_minutes = Column(Integer, nullable=False, default=0)
    early_leave_minutes = Column(Integer, nullable=False, default=0)
    late_makeup_minutes = Column(Integer, nullable=False, default=0)
    overtime_minutes = Column(Integer, nullable=False, default=0)
    absence_minutes = Column(Integer, nullable=False, default=0)
    unpaid_minutes = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="absent")
    is_manually_corrected = Column(Boolean, nullable=False, default=False)
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    employee = relationship("Employees")
    work_schedule = relationship("WorkSchedule")
    events = relationship("AttendanceEvent", back_populates="attendance_day")
    corrections = relationship("AttendanceCorrection", back_populates="attendance_day")


class AttendanceEvent(Base):
    __tablename__ = "attendance_event"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    attendance_day_id = Column(Integer, ForeignKey("attendance_day.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(20), nullable=False)
    event_time = Column(DateTime(timezone=True), nullable=False, index=True)
    source = Column(String(20), nullable=False, default="system")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(Integer, nullable=True)

    employee = relationship("Employees")
    attendance_day = relationship("AttendanceDay", back_populates="events")


class AttendanceCorrection(Base):
    __tablename__ = "attendance_correction"

    id = Column(Integer, primary_key=True, index=True)
    attendance_day_id = Column(Integer, ForeignKey("attendance_day.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    original_event_id = Column(Integer, ForeignKey("attendance_event.id", ondelete="SET NULL"), nullable=True)
    field_changed = Column(String(50), nullable=False)
    old_value = Column(String(255), nullable=True)
    new_value = Column(String(255), nullable=True)
    reason = Column(Text, nullable=False)
    corrected_by = Column(Integer, nullable=True)
    corrected_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    attendance_day = relationship("AttendanceDay", back_populates="corrections")
    employee = relationship("Employees")
    original_event = relationship("AttendanceEvent")


class PayrollPeriod(Base):
    __tablename__ = "payroll_period"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    start_date = Column(Date, nullable=False, index=True)
    end_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="draft")
    generated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(Integer, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    locked_at = Column(DateTime(timezone=True), nullable=True)

    payrolls = relationship("EmployeePayroll", back_populates="payroll_period")


class EmployeePayroll(Base):
    __tablename__ = "employee_payroll"

    id = Column(Integer, primary_key=True, index=True)
    payroll_period_id = Column(Integer, ForeignKey("payroll_period.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    salary_type = Column(String(20), nullable=False)
    base_salary = Column(Numeric(12, 2), nullable=False, default=0)
    normal_amount = Column(Numeric(12, 2), nullable=False, default=0)
    overtime_amount = Column(Numeric(12, 2), nullable=False, default=0)
    bonus_amount = Column(Numeric(12, 2), nullable=False, default=0)
    deduction_amount = Column(Numeric(12, 2), nullable=False, default=0)
    late_deduction_amount = Column(Numeric(12, 2), nullable=False, default=0)
    unpaid_vacation_deduction = Column(Numeric(12, 2), nullable=False, default=0)
    adjustment_amount = Column(Numeric(12, 2), nullable=False, default=0)
    gross_salary = Column(Numeric(12, 2), nullable=False, default=0)
    net_salary = Column(Numeric(12, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="draft")
    calculated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    payroll_period = relationship("PayrollPeriod", back_populates="payrolls")
    employee = relationship("Employees")
    adjustments = relationship("PayrollAdjustment", back_populates="employee_payroll")
    discrepancies = relationship("PayrollDiscrepancy", back_populates="employee_payroll")
    history = relationship("PayrollCalculationHistory", back_populates="employee_payroll")


class PayrollAdjustment(Base):
    __tablename__ = "payroll_adjustment"

    id = Column(Integer, primary_key=True, index=True)
    employee_payroll_id = Column(Integer, ForeignKey("employee_payroll.id", ondelete="CASCADE"), nullable=False, index=True)
    payroll_period_id = Column(Integer, ForeignKey("payroll_period.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    adjustment_type = Column(String(20), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    reason = Column(Text, nullable=False)
    created_by = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    employee_payroll = relationship("EmployeePayroll", back_populates="adjustments")
    payroll_period = relationship("PayrollPeriod")
    employee = relationship("Employees")


class PayrollDiscrepancy(Base):
    __tablename__ = "payroll_discrepancy"

    id = Column(Integer, primary_key=True, index=True)
    employee_payroll_id = Column(Integer, ForeignKey("employee_payroll.id", ondelete="CASCADE"), nullable=True, index=True)
    payroll_period_id = Column(Integer, ForeignKey("payroll_period.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    discrepancy_type = Column(String(40), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(10), nullable=False, default="medium")
    status = Column(String(20), nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(Integer, nullable=True)
    resolution_note = Column(Text, nullable=True)

    employee_payroll = relationship("EmployeePayroll", back_populates="discrepancies")
    payroll_period = relationship("PayrollPeriod")
    employee = relationship("Employees")


class PayrollCalculationHistory(Base):
    __tablename__ = "payroll_calculation_history"

    id = Column(Integer, primary_key=True, index=True)
    employee_payroll_id = Column(Integer, ForeignKey("employee_payroll.id", ondelete="CASCADE"), nullable=False, index=True)
    payroll_period_id = Column(Integer, ForeignKey("payroll_period.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    old_gross_salary = Column(Numeric(12, 2), nullable=True)
    new_gross_salary = Column(Numeric(12, 2), nullable=False)
    old_net_salary = Column(Numeric(12, 2), nullable=True)
    new_net_salary = Column(Numeric(12, 2), nullable=False)
    reason = Column(String(255), nullable=False)
    calculation_data_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    created_by = Column(Integer, nullable=True)

    employee_payroll = relationship("EmployeePayroll", back_populates="history")
    payroll_period = relationship("PayrollPeriod")
    employee = relationship("Employees")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(Integer, nullable=False)
    old_data_json = Column(JSON, nullable=True)
    new_data_json = Column(JSON, nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
