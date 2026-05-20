DEFAULT_ROLE_CODES = ("admin", "hr", "employee")
ROLE_DEFINITIONS = (
    {
        "code": "admin",
        "name": "Administrator",
        "description": "Full system administrator with unrestricted access.",
        "is_system_role": True,
    },
    {
        "code": "hr",
        "name": "HR",
        "description": "Human resources user with employee and payroll management access.",
        "is_system_role": True,
    },
    {
        "code": "employee",
        "name": "Employee",
        "description": "Employee self-service user limited to their own data.",
        "is_system_role": True,
    },
)

PERMISSION_DEFINITIONS = (
    {"code": "users.read", "name": "Read users", "description": "View user accounts", "module": "users"},
    {"code": "users.create", "name": "Create users", "description": "Create user accounts", "module": "users"},
    {"code": "users.update", "name": "Update users", "description": "Update user accounts", "module": "users"},
    {"code": "users.delete", "name": "Delete users", "description": "Delete or permanently disable user accounts", "module": "users"},
    {"code": "users.assign_roles", "name": "Assign roles", "description": "Assign and remove user roles", "module": "users"},
    {"code": "employees.read", "name": "Read employees", "description": "View employee profiles", "module": "employees"},
    {"code": "employees.create", "name": "Create employees", "description": "Create employee profiles", "module": "employees"},
    {"code": "employees.update", "name": "Update employees", "description": "Update employee profiles", "module": "employees"},
    {"code": "employees.delete", "name": "Delete employees", "description": "Delete employee profiles", "module": "employees"},
    {"code": "attendance.read_all", "name": "Read all attendance", "description": "View attendance for all employees", "module": "attendance"},
    {"code": "attendance.read_own", "name": "Read own attendance", "description": "View the current user's attendance", "module": "attendance"},
    {"code": "attendance.check_in_own", "name": "Self attendance actions", "description": "Check in, break, and check out for the current user", "module": "attendance"},
    {"code": "attendance.correct", "name": "Correct attendance", "description": "Correct attendance records for employees", "module": "attendance"},
    {"code": "attendance.approve", "name": "Approve attendance", "description": "Approve or lock attendance review states", "module": "attendance"},
    {"code": "attendance.recalculate", "name": "Recalculate attendance", "description": "Recalculate attendance summaries", "module": "attendance"},
    {"code": "payroll.read_all", "name": "Read all payroll", "description": "View payroll for all employees", "module": "payroll"},
    {"code": "payroll.read_own", "name": "Read own payroll", "description": "View the current user's payroll", "module": "payroll"},
    {"code": "payroll.calculate", "name": "Calculate payroll", "description": "Calculate or recalculate payroll", "module": "payroll"},
    {"code": "payroll.adjust", "name": "Adjust payroll", "description": "Create payroll adjustments and resolve discrepancies", "module": "payroll"},
    {"code": "payroll.approve", "name": "Approve payroll", "description": "Approve payroll records", "module": "payroll"},
    {"code": "payroll.mark_paid", "name": "Mark payroll paid", "description": "Mark payroll records as paid", "module": "payroll"},
    {"code": "payroll.lock", "name": "Lock payroll", "description": "Lock finalized payroll records", "module": "payroll"},
    {"code": "vacations.read_all", "name": "Read all vacations", "description": "View vacation requests for all employees", "module": "vacations"},
    {"code": "vacations.read_own", "name": "Read own vacations", "description": "View the current user's vacations", "module": "vacations"},
    {"code": "vacations.request_own", "name": "Request own vacations", "description": "Create self-service vacation requests", "module": "vacations"},
    {"code": "vacations.approve", "name": "Approve vacations", "description": "Approve vacation requests", "module": "vacations"},
    {"code": "vacations.reject", "name": "Reject vacations", "description": "Reject vacation requests", "module": "vacations"},
    {"code": "notifications.read_own", "name": "Read own notifications", "description": "View the current user's in-app notifications", "module": "notifications"},
    {"code": "notifications.read_all", "name": "Read all notifications", "description": "View in-app notifications across users", "module": "notifications"},
    {"code": "notifications.send", "name": "Send notifications", "description": "Send in-app notifications to users or roles", "module": "notifications"},
    {"code": "settings.read", "name": "Read settings", "description": "View system settings", "module": "settings"},
    {"code": "settings.update", "name": "Update settings", "description": "Update system settings", "module": "settings"},
    {"code": "audit.read", "name": "Read audit log", "description": "View the audit log", "module": "audit"},
)

DEFAULT_ROLE_PERMISSIONS = {
    "admin": tuple(item["code"] for item in PERMISSION_DEFINITIONS),
    "hr": (
        "employees.read",
        "employees.create",
        "employees.update",
        "attendance.read_all",
        "attendance.correct",
        "attendance.approve",
        "attendance.recalculate",
        "payroll.read_all",
        "payroll.calculate",
        "payroll.adjust",
        "notifications.read_own",
        "notifications.read_all",
        "vacations.read_all",
        "vacations.approve",
        "vacations.reject",
        "settings.read",
    ),
    "employee": (
        "attendance.read_own",
        "attendance.check_in_own",
        "notifications.read_own",
        "payroll.read_own",
        "vacations.read_own",
        "vacations.request_own",
    ),
}

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
    "unpaid",
    "sick_leave",
    "manually_corrected",
)

PAYROLL_PERIOD_STATUS_CODES = ("draft", "reviewed", "approved", "paid", "locked", "cancelled")
EMPLOYEE_PAYROLL_STATUS_CODES = ("draft", "needs_review", "approved", "partially_paid", "paid", "locked")
PAYROLL_ADJUSTMENT_TYPE_CODES = ("bonus", "deduction", "correction")
PAYROLL_DISCREPANCY_TYPE_CODES = (
    "missing_checkout",
    "missing_checkin",
    "attendance_changed_after_approval",
    "attendance_requires_review",
    "overtime_conflict",
    "vacation_overlap",
    "missing_attendance",
)
PAYROLL_DISCREPANCY_STATUS_CODES = ("open", "resolved", "ignored")

VACATION_TYPE_CODES = ("paid", "unpaid", "sick", "emergency")
VACATION_STATUS_CODES = ("pending", "approved", "rejected", "cancelled")
