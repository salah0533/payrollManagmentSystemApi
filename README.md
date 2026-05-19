# payrollManagmentSystemApi

## Response and Error Handling

The API now uses centralized success and error response helpers, custom application exceptions, and global exception handlers. The response contract and manual verification checklist are documented in [docs/api_response_error_handling.md](docs/api_response_error_handling.md).

Run the automated response handling checks with:

```bash
python -m unittest discover -s tests -v
```

FastAPI + SQLAlchemy backend for employee management, attendance, vacations, and payroll.

## First-Time Setup

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root.

Example:

```env
DATABASE_URL=sqlite:///./app.db
JWT_SECRET_KEY=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_MINUTES=10080
DEFAULT_ADMIN_USERNAME=admin
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=admin
API_HOST=127.0.0.1
API_PORT=8000
API_WORKERS=1
CORS_ORIGINS=*
```

You can also copy the values from `.env.example`.

Environment variables:

- `DATABASE_URL`: SQLAlchemy connection string.
- `JWT_SECRET_KEY`: signing key for JWT tokens.
- `JWT_ALGORITHM`: JWT signing algorithm.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: access token lifetime in minutes.
- `REFRESH_TOKEN_EXPIRE_MINUTES`: refresh token lifetime in minutes.
- `DEFAULT_ADMIN_USERNAME`: seeded admin username.
- `DEFAULT_ADMIN_EMAIL`: seeded admin email.
- `DEFAULT_ADMIN_PASSWORD`: seeded admin password for first-run development.
- `API_HOST`: backend bind address for the backend launchers.
- `API_PORT`: backend bind port for the backend launchers.
- `API_WORKERS`: worker count used by `python -m app.run_prod`.
- `CORS_ORIGINS`: comma-separated allowed frontend origins, or `*` for unrestricted development.

### 4. Run database migrations

Alembic is used for schema changes such as tables, columns, indexes, and constraints.

```bash
alembic upgrade head
```

### 5. Seed initial/default data

Run the idempotent seed script after migrations.

```bash
python -m app.scripts.seed_initial_data
```

This seeds the default reference and setup data, including:

- salary types
- attendance types/status codes
- payment types
- vacation types and statuses
- default settings
- default work schedule
- default payroll policy

The seed is safe to run multiple times.

### 6. Start the development server

```bash
python -m app.run_dev
```

`python -m app.run` remains available as a compatibility alias for the same development launcher.

### 7. Start the production-style server

```bash
python -m app.run_prod
```

## First-Run Command Order

Use this order on a fresh setup:

```bash
alembic upgrade head
python -m app.scripts.seed_initial_data
python -m app.run_dev
```

## Re-running the Seed

If you need to refresh missing default values later, run:

```bash
python -m app.scripts.seed_initial_data
```

It will create missing rows, reuse existing rows, and avoid duplicating seed data.
