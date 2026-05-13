DEFAULT_ROLE_CODES = ("admin", "hr", "employee")

SALARY_TYPE_CODES = ("monthly", "daily", "hourly")
PAYMENT_TYPE_CODES = ("payment", "bonus", "deduction", "attendance")

ATTENDANCE_EVENT_TYPE_CODES = ("check_in", "break_start", "break_end", "check_out", "manual_event")
ATTENDANCE_STATUS_CODES = (
    "present",
    "late",
    "absent",
    "incomplete",
    "weekly_off",
    "holiday",
    "paid_vacation",
    "unpaid_vacation",
    "sick_leave",
    "manually_corrected",
)

PAYROLL_PERIOD_STATUS_CODES = ("draft", "reviewed", "approved", "paid", "locked", "cancelled")
EMPLOYEE_PAYROLL_STATUS_CODES = ("draft", "needs_review", "approved", "paid", "locked")
PAYROLL_ADJUSTMENT_TYPE_CODES = ("bonus", "deduction", "correction")
PAYROLL_DISCREPANCY_TYPE_CODES = (
    "missing_checkout",
    "missing_checkin",
    "attendance_changed_after_approval",
    "overtime_conflict",
    "vacation_overlap",
    "missing_attendance",
)
PAYROLL_DISCREPANCY_STATUS_CODES = ("open", "resolved", "ignored")

VACATION_TYPE_CODES = ("paid", "unpaid", "sick", "emergency")
VACATION_STATUS_CODES = ("pending", "approved", "rejected", "cancelled")
