# Initial Database Setup

## What Alembic Does

Alembic is responsible for database schema changes:

- tables
- columns
- indexes
- relationships
- constraints

Run schema changes with:

```bash
alembic upgrade head
```

## What `seed_initial_data.py` Does

The seed script inserts and normalizes initial reference/default data after the schema exists.

It is idempotent:

- if a row does not exist, it is created
- if a row already exists, it is reused
- if a row exists but its seeded fields differ, it is updated

Run the seed with:

```bash
python -m app.scripts.seed_initial_data
```

It also seeds:

- roles
- permissions
- role-permission mappings
- a default admin account when no admin exists
- default settings, work schedule, and payroll policy rows

## First-Run Commands

```bash
alembic upgrade head
python -m app.scripts.seed_initial_data
uvicorn app.main:app --reload
```

## Safe Rerun

You can rerun the seed safely at any time:

```bash
python -m app.scripts.seed_initial_data
```

It will not intentionally create duplicate lookup/default rows.

## Default Values Created

Database-seeded defaults:

- `salary_type`: `monthly`, `daily`, `hourly`
- `payment_types`: `payment`, `bonus`, `deduction`, `attendance`
- `attendence_types`: `present`, `late`, `absent`, `overtime`, `paid_vacation`, `unpaid_vacation`, `sick_leave`, `incomplete`, `weekly_off`, `holiday`, `manually_corrected`
- `vacation_types`: `paid`, `unpaid`, `sick`, `emergency`
- `vacation_status`: `pending`, `approved`, `cancelled`, `rejected`
- legacy `settings` row with `08:00` to `17:00`
- default `work_schedule` with `08:00` to `17:00`, `60` break minutes, weekly off `["friday", "saturday"]`, timezone `Africa/Algiers`
- default `payroll_policy`

Code-constant reference values used by the modern attendance/payroll layer:

- attendance event types: `check_in`, `break_start`, `break_end`, `check_out`, `manual_event`
- attendance day statuses: `present`, `late`, `absent`, `incomplete`, `weekly_off`, `holiday`, `paid_vacation`, `unpaid_vacation`, `sick_leave`, `manually_corrected`
- payroll period statuses: `draft`, `reviewed`, `approved`, `paid`, `locked`, `cancelled`
- employee payroll statuses: `draft`, `needs_review`, `approved`, `paid`, `locked`
- payroll adjustment types: `bonus`, `deduction`, `correction`
- payroll discrepancy types: `missing_checkout`, `missing_checkin`, `attendance_changed_after_approval`, `overtime_conflict`, `vacation_overlap`, `missing_attendance`
- payroll discrepancy statuses: `open`, `resolved`, `ignored`
- role codes: `admin`, `hr`, `employee`

## Default Admin

Default development credentials:

- username: `admin`
- password: `admin`

Important:

- The default admin is created only if no admin account exists.
- The password is hashed before being stored.
- The account is seeded with `must_change_password = true`.
- Change the default admin password immediately after first login.
