# payrollManagmentSystemApi

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
DATABASE_URL = sqlite:///./app.db
```

You can also copy the value from `.env-example`.

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
uvicorn app.main:app --reload
```

## First-Run Command Order

Use this order on a fresh setup:

```bash
alembic upgrade head
python -m app.scripts.seed_initial_data
uvicorn app.main:app --reload
```

## Re-running the Seed

If you need to refresh missing default values later, run:

```bash
python -m app.scripts.seed_initial_data
```

It will create missing rows, reuse existing rows, and avoid duplicating seed data.
