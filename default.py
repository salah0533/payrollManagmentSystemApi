from alembic import op
import sqlalchemy as sa



attendance_types = sa.table(
    "attendence_types",
    sa.column("id", sa.Integer),
    sa.column("attendence_type", sa.String),
)

payment_types = sa.table(
    "payment_types",
    sa.column("id", sa.Integer),
    sa.column("payment_type", sa.String),
)

salary_types = sa.table(
    "salary_types",
    sa.column("id", sa.Integer),
    sa.column("salary_type", sa.String),
)

roles = sa.table(
    "roles",
    sa.column("id", sa.Integer),
    sa.column("role_name", sa.String),
)

vacation_statuses = sa.table(
    "vacation_statuses",
    sa.column("id", sa.Integer),
    sa.column("vacation_status", sa.String),
)

vacation_types = sa.table(
    "vacation_types",
    sa.column("id", sa.Integer),
    sa.column("vacation_type", sa.String),
)

def upgrade() -> None:
    op.bulk_insert(
        attendance_types,
        [
            {"id":0,"attendence_type": "present"},
            {"id":1,"attendence_type": "late"},
            {"id":2,"attendence_type": "vacation"},
            {"id":3,"attendence_type": "absent"},
            {"id":4,"attendence_type": "extra_work"}
        ],
    )
    op.bulk_insert(
        payment_types,
        [
            {"id":0,"payment_type": "payment"},
            {"id":1,"payment_type": "bonus"},
            {"id":2,"payment_type": "deduction"},
            {"id":3,"payment_type": "attendence"}
        ],
    )
    op.bulk_insert(
        salary_types,
        [
            {"id":0,"salary_type": "monthly"},
            {"id":1,"salary_type": "daily"},
            {"id":2,"salary_type": "hourly"}
        ],
    )
    op.bulk_insert(
        roles,
        [
            {"id":0,"role_name": "admine"},
            {"id":1,"role_name": "employee"},
        ],
    )
    op.bulk_insert(
        vacation_statuses,
        [
            {"id":0,"vacation_status": "pending"},
            {"id":1,"vacation_status": "proved"},
            {"id":2,"vacation_status": "rejected"},
            {"id":3,"vacation_status": "canceled"}
        ],
    )
    op.bulk_insert(
        vacation_types,
        [
            {"id":0,"vacation_type": "yearly_vacation"},
            {"id":1,"vacation_type": "sick_leave"},
            {"id":2,"vacation_type": "vacation"}
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
