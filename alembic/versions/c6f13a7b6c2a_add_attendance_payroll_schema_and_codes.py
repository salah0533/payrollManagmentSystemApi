"""add attendance payroll schema and stable reference codes

Revision ID: c6f13a7b6c2a
Revises: 98d0d62ed5ea
Create Date: 2026-05-13 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c6f13a7b6c2a"
down_revision: Union[str, Sequence[str], None] = "98d0d62ed5ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _ensure_code_column(table_name: str, index_name: str):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not _table_exists(inspector, table_name):
        return
    if not _column_exists(inspector, table_name, "code"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("code", sa.String(length=50), nullable=True))
    inspector = sa.inspect(bind)
    if not _index_exists(inspector, table_name, index_name):
        op.create_index(index_name, table_name, ["code"], unique=True)


def _ensure_index(table_name: str, index_name: str, columns: list[str], unique: bool = False):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _table_exists(inspector, table_name) and not _index_exists(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    _ensure_code_column("salary_type", "ux_salary_type_code")
    _ensure_code_column("attendence_types", "ux_attendence_types_code")
    _ensure_code_column("payment_types", "ux_payment_types_code")
    _ensure_code_column("vacation_types", "ux_vacation_types_code")
    _ensure_code_column("vacation_status", "ux_vacation_status_code")

    if not _table_exists(inspector, "employee_compensation"):
        op.create_table(
            "employee_compensation",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("salary_type", sa.String(length=20), nullable=False),
            sa.Column("base_monthly_salary", sa.Numeric(12, 2), nullable=True),
            sa.Column("daily_rate", sa.Numeric(12, 2), nullable=True),
            sa.Column("hourly_rate", sa.Numeric(12, 2), nullable=True),
            sa.Column("overtime_rate", sa.Numeric(12, 2), nullable=True),
            sa.Column("late_deduction_rate", sa.Numeric(12, 2), nullable=True),
            sa.Column("currency", sa.String(length=10), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "work_schedule"):
        op.create_table(
            "work_schedule",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("start_time", sa.Time(), nullable=False),
            sa.Column("end_time", sa.Time(), nullable=False),
            sa.Column("break_minutes", sa.Integer(), nullable=False),
            sa.Column("weekly_off_days", sa.JSON(), nullable=False),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "payroll_policy"):
        op.create_table(
            "payroll_policy",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("payroll_cycle", sa.String(length=20), nullable=False),
            sa.Column("minimum_overtime_minutes", sa.Integer(), nullable=False),
            sa.Column("allowed_late_minutes", sa.Integer(), nullable=False),
            sa.Column("default_currency", sa.String(length=10), nullable=False),
            sa.Column("significant_change_threshold", sa.Numeric(12, 2), nullable=False),
            sa.Column("paid_vacation_counts_for_daily", sa.Boolean(), nullable=False),
            sa.Column("overtime_enabled", sa.Boolean(), nullable=False),
            sa.Column("late_makeup_enabled", sa.Boolean(), nullable=False),
            sa.Column("late_deduction_enabled", sa.Boolean(), nullable=False),
            sa.Column("auto_recalculate_draft_payroll", sa.Boolean(), nullable=False),
            sa.Column("lock_payroll_after_payment", sa.Boolean(), nullable=False),
            sa.Column("holidays_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        payroll_policy_columns = {
            "payroll_cycle": sa.Column("payroll_cycle", sa.String(length=20), nullable=False, server_default="monthly"),
            "minimum_overtime_minutes": sa.Column("minimum_overtime_minutes", sa.Integer(), nullable=False, server_default="30"),
            "allowed_late_minutes": sa.Column("allowed_late_minutes", sa.Integer(), nullable=False, server_default="0"),
            "late_makeup_enabled": sa.Column("late_makeup_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            "auto_recalculate_draft_payroll": sa.Column("auto_recalculate_draft_payroll", sa.Boolean(), nullable=False, server_default=sa.true()),
            "lock_payroll_after_payment": sa.Column("lock_payroll_after_payment", sa.Boolean(), nullable=False, server_default=sa.true()),
        }
        for column_name, column in payroll_policy_columns.items():
            inspector = sa.inspect(bind)
            if not _column_exists(inspector, "payroll_policy", column_name):
                with op.batch_alter_table("payroll_policy") as batch_op:
                    batch_op.add_column(column)

    if not _table_exists(inspector, "attendance_day"):
        op.create_table(
            "attendance_day",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("work_schedule_id", sa.Integer(), nullable=True),
            sa.Column("check_in_time", sa.Time(), nullable=True),
            sa.Column("break_start_time", sa.Time(), nullable=True),
            sa.Column("break_end_time", sa.Time(), nullable=True),
            sa.Column("check_out_time", sa.Time(), nullable=True),
            sa.Column("expected_work_minutes", sa.Integer(), nullable=False),
            sa.Column("actual_work_minutes", sa.Integer(), nullable=False),
            sa.Column("break_minutes", sa.Integer(), nullable=False),
            sa.Column("normal_paid_minutes", sa.Integer(), nullable=False),
            sa.Column("late_minutes", sa.Integer(), nullable=False),
            sa.Column("early_leave_minutes", sa.Integer(), nullable=False),
            sa.Column("late_makeup_minutes", sa.Integer(), nullable=False),
            sa.Column("overtime_minutes", sa.Integer(), nullable=False),
            sa.Column("absence_minutes", sa.Integer(), nullable=False),
            sa.Column("unpaid_minutes", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("is_manually_corrected", sa.Boolean(), nullable=False),
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["work_schedule_id"], ["work_schedule.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "attendance_event"):
        op.create_table(
            "attendance_event",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("attendance_day_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(length=20), nullable=False),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source", sa.String(length=20), nullable=False),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["attendance_day_id"], ["attendance_day.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "attendance_correction"):
        op.create_table(
            "attendance_correction",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("attendance_day_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("original_event_id", sa.Integer(), nullable=True),
            sa.Column("field_changed", sa.String(length=50), nullable=False),
            sa.Column("old_value", sa.String(length=255), nullable=True),
            sa.Column("new_value", sa.String(length=255), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("corrected_by", sa.Integer(), nullable=True),
            sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["attendance_day_id"], ["attendance_day.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["original_event_id"], ["attendance_event.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "payroll_period"):
        op.create_table(
            "payroll_period",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "employee_payroll"):
        op.create_table(
            "employee_payroll",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("payroll_period_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("salary_type", sa.String(length=20), nullable=False),
            sa.Column("base_salary", sa.Numeric(12, 2), nullable=False),
            sa.Column("normal_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("overtime_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("bonus_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("deduction_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("late_deduction_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("unpaid_vacation_deduction", sa.Numeric(12, 2), nullable=False),
            sa.Column("adjustment_amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("gross_salary", sa.Numeric(12, 2), nullable=False),
            sa.Column("net_salary", sa.Numeric(12, 2), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["payroll_period_id"], ["payroll_period.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "payroll_adjustment"):
        op.create_table(
            "payroll_adjustment",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_payroll_id", sa.Integer(), nullable=False),
            sa.Column("payroll_period_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("adjustment_type", sa.String(length=20), nullable=False),
            sa.Column("amount", sa.Numeric(12, 2), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["employee_payroll_id"], ["employee_payroll.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["payroll_period_id"], ["payroll_period.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "payroll_discrepancy"):
        op.create_table(
            "payroll_discrepancy",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_payroll_id", sa.Integer(), nullable=True),
            sa.Column("payroll_period_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("discrepancy_type", sa.String(length=40), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("severity", sa.String(length=10), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by", sa.Integer(), nullable=True),
            sa.Column("resolution_note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["employee_payroll_id"], ["employee_payroll.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["payroll_period_id"], ["payroll_period.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "payroll_calculation_history"):
        op.create_table(
            "payroll_calculation_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("employee_payroll_id", sa.Integer(), nullable=False),
            sa.Column("payroll_period_id", sa.Integer(), nullable=False),
            sa.Column("employee_id", sa.Integer(), nullable=False),
            sa.Column("old_gross_salary", sa.Numeric(12, 2), nullable=True),
            sa.Column("new_gross_salary", sa.Numeric(12, 2), nullable=False),
            sa.Column("old_net_salary", sa.Numeric(12, 2), nullable=True),
            sa.Column("new_net_salary", sa.Numeric(12, 2), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=False),
            sa.Column("calculation_data_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["employee_payroll_id"], ["employee_payroll.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["payroll_period_id"], ["payroll_period.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _table_exists(inspector, "audit_log"):
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("action", sa.String(length=100), nullable=False),
            sa.Column("entity_type", sa.String(length=100), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("old_data_json", sa.JSON(), nullable=True),
            sa.Column("new_data_json", sa.JSON(), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    _ensure_index("employee_compensation", "ix_employee_compensation_id", ["id"])
    _ensure_index("employee_compensation", "ix_employee_compensation_employee_id", ["employee_id"])
    _ensure_index("employee_compensation", "ix_employee_compensation_effective_from", ["effective_from"])
    _ensure_index("employee_compensation", "ix_employee_compensation_effective_to", ["effective_to"])
    _ensure_index("work_schedule", "ix_work_schedule_id", ["id"])
    _ensure_index("payroll_policy", "ix_payroll_policy_id", ["id"])
    _ensure_index("attendance_day", "ix_attendance_day_id", ["id"])
    _ensure_index("attendance_day", "ix_attendance_day_employee_id", ["employee_id"])
    _ensure_index("attendance_day", "ix_attendance_day_work_date", ["work_date"])
    _ensure_index("attendance_event", "ix_attendance_event_id", ["id"])
    _ensure_index("attendance_event", "ix_attendance_event_employee_id", ["employee_id"])
    _ensure_index("attendance_event", "ix_attendance_event_attendance_day_id", ["attendance_day_id"])
    _ensure_index("attendance_event", "ix_attendance_event_event_time", ["event_time"])
    _ensure_index("attendance_correction", "ix_attendance_correction_id", ["id"])
    _ensure_index("attendance_correction", "ix_attendance_correction_attendance_day_id", ["attendance_day_id"])
    _ensure_index("attendance_correction", "ix_attendance_correction_employee_id", ["employee_id"])
    _ensure_index("payroll_period", "ix_payroll_period_id", ["id"])
    _ensure_index("payroll_period", "ix_payroll_period_start_date", ["start_date"])
    _ensure_index("payroll_period", "ix_payroll_period_end_date", ["end_date"])
    _ensure_index("employee_payroll", "ix_employee_payroll_id", ["id"])
    _ensure_index("employee_payroll", "ix_employee_payroll_payroll_period_id", ["payroll_period_id"])
    _ensure_index("employee_payroll", "ix_employee_payroll_employee_id", ["employee_id"])
    _ensure_index("payroll_adjustment", "ix_payroll_adjustment_id", ["id"])
    _ensure_index("payroll_adjustment", "ix_payroll_adjustment_employee_payroll_id", ["employee_payroll_id"])
    _ensure_index("payroll_adjustment", "ix_payroll_adjustment_payroll_period_id", ["payroll_period_id"])
    _ensure_index("payroll_adjustment", "ix_payroll_adjustment_employee_id", ["employee_id"])
    _ensure_index("payroll_discrepancy", "ix_payroll_discrepancy_id", ["id"])
    _ensure_index("payroll_discrepancy", "ix_payroll_discrepancy_employee_payroll_id", ["employee_payroll_id"])
    _ensure_index("payroll_discrepancy", "ix_payroll_discrepancy_payroll_period_id", ["payroll_period_id"])
    _ensure_index("payroll_discrepancy", "ix_payroll_discrepancy_employee_id", ["employee_id"])
    _ensure_index("payroll_calculation_history", "ix_payroll_calculation_history_id", ["id"])
    _ensure_index("payroll_calculation_history", "ix_payroll_calculation_history_employee_payroll_id", ["employee_payroll_id"])
    _ensure_index("payroll_calculation_history", "ix_payroll_calculation_history_payroll_period_id", ["payroll_period_id"])
    _ensure_index("payroll_calculation_history", "ix_payroll_calculation_history_employee_id", ["employee_id"])
    _ensure_index("audit_log", "ix_audit_log_id", ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name in [
        "audit_log",
        "payroll_calculation_history",
        "payroll_discrepancy",
        "payroll_adjustment",
        "employee_payroll",
        "payroll_period",
        "attendance_correction",
        "attendance_event",
        "attendance_day",
        "payroll_policy",
        "work_schedule",
        "employee_compensation",
    ]:
        if _table_exists(inspector, table_name):
            op.drop_table(table_name)
            inspector = sa.inspect(bind)
