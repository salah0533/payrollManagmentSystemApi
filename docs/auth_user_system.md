# Auth User System

## Core Separation

- `User` is the authentication and security account.
- `User.language` stores the per-account UI language preference (`en`, `fr`, or `ar`).
- `Employee` is the HR, attendance, payroll, and vacation profile.
- A `User` may be linked to one `Employee` through `users.employee_id`.
- Employees can exist without login accounts.
- Admin accounts can exist without an employee profile.

## Role and Permission Model

- `Role` is a database-backed grouping of permissions.
- `Permission` is a stable action code such as `users.read` or `payroll.approve`.
- `UserRole` maps users to roles.
- `RolePermission` maps roles to permissions.
- `admin` is treated as a full-access role by the authorization dependency.

## Seeded Roles

- `admin`
- `hr`
- `employee`

## Seeded Permission Codes

- `users.read`
- `users.create`
- `users.update`
- `users.delete`
- `users.assign_roles`
- `employees.read`
- `employees.create`
- `employees.update`
- `employees.delete`
- `attendance.read_all`
- `attendance.read_own`
- `attendance.check_in_own`
- `attendance.correct`
- `attendance.recalculate`
- `payroll.read_all`
- `payroll.read_own`
- `payroll.calculate`
- `payroll.adjust`
- `payroll.approve`
- `payroll.mark_paid`
- `payroll.lock`
- `vacations.read_all`
- `vacations.read_own`
- `vacations.request_own`
- `vacations.approve`
- `vacations.reject`
- `settings.read`
- `settings.update`
- `audit.read`

## Default Role Permissions

- `admin`: all seeded permissions
- `hr`: `employees.read`, `employees.create`, `employees.update`, `attendance.read_all`, `attendance.correct`, `attendance.recalculate`, `payroll.read_all`, `payroll.calculate`, `payroll.adjust`, `vacations.read_all`, `vacations.approve`, `vacations.reject`, `settings.read`
- `employee`: `attendance.read_own`, `attendance.check_in_own`, `payroll.read_own`, `vacations.read_own`, `vacations.request_own`

## Auth Endpoints

- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me`
- `PATCH /auth/language`
- `POST /auth/change-password`
- `POST /auth/logout`

`/auth/login` accepts an `identifier` that can be either username or email.

JWT access tokens include:

- `user_id`
- `employee_id`
- `roles`

The backend still reloads the current user, roles, and permissions from the database and does not trust frontend-supplied role or employee data.

## Forced Password Change

If `users.must_change_password = true`, the account is limited to:

- `GET /auth/me`
- `POST /auth/change-password`
- `POST /auth/logout`

This is enforced in the authorization dependency layer.

## `/me` Self-Service Routes

- `GET /me/profile`
- `GET /me/attendance`
- `GET /me/payroll`
- `GET /me/vacations`
- `POST /me/vacations/request`
- `POST /me/attendance/check-in`
- `POST /me/attendance/break-start`
- `POST /me/attendance/break-end`
- `POST /me/attendance/check-out`

These routes derive the employee context from `current_user.employee_id` and do not trust an `employee_id` sent by the frontend.

## Admin and HR Routes

- Admin user management is exposed under `/users`.
- HR and Admin management of employees, attendance, payroll, vacations, and settings stays on the existing domain routes and is permission-protected.
- Admin-only protections include:
  - user creation and updates
  - role assignment and removal
  - password resets
  - preventing the last active admin from being deactivated
  - preventing the last active admin role from being removed

## Default Admin

Seed command:

```bash
python -m app.scripts.seed_initial_data
```

Default development credentials:

- username: `admin`
- email: `admin@example.com`
- password: `admin`

Environment variable overrides:

- `DEFAULT_ADMIN_USERNAME`
- `DEFAULT_ADMIN_EMAIL`
- `DEFAULT_ADMIN_PASSWORD`

Important:

- The default password is only intended for local or development setup.
- The seeded admin account is created with `must_change_password = true`.
- Change the password immediately after first login.

## Manual Test Checklist

Authentication:

- Login with the seeded admin account.
- Confirm `users.password_hash` is not plain text.
- Confirm `must_change_password` blocks `/users` and other protected routes.
- Change the admin password through `POST /auth/change-password`.
- Confirm inactive users cannot log in.

Authorization:

- Confirm admin can access `/users`.
- Confirm HR cannot access `/users`.
- Confirm employee users can access `/me/profile`.
- Confirm employee users can check in through `/me/attendance/check-in`.
- Confirm employee users cannot read another employee's payroll or attendance through protected routes.

Seed behavior:

- Run `python -m app.scripts.seed_initial_data` once.
- Run it a second time.
- Confirm no duplicate roles, permissions, or role mappings are created.
- Confirm only one default admin is created.

Security and admin safety:

- Confirm the last active admin cannot be deactivated.
- Confirm the last admin role cannot be removed from the last active admin.
- Confirm invalid role IDs are rejected.
- Confirm an `employee` role cannot be assigned to a user without an employee link.
