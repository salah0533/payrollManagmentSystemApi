import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.services.auto_attendance_service import ensure_employee_auto_attendance_schema


class AutoAttendanceSchemaRepairTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE employees (
                        id INTEGER PRIMARY KEY,
                        first_name VARCHAR(50) NOT NULL,
                        last_name VARCHAR(50) NOT NULL,
                        fullname VARCHAR(100) NOT NULL,
                        job_title VARCHAR NOT NULL,
                        phone VARCHAR(14) NOT NULL,
                        email VARCHAR(255) NULL,
                        department_id INTEGER NULL,
                        position_id INTEGER NULL,
                        position VARCHAR(100) NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'active',
                        hire_date DATE NULL,
                        dues NUMERIC NOT NULL DEFAULT 0,
                        salary_type INTEGER NOT NULL DEFAULT 1,
                        monthly_price NUMERIC NOT NULL DEFAULT 0,
                        day_price NUMERIC NOT NULL DEFAULT 0,
                        hour_price NUMERIC NOT NULL DEFAULT 0,
                        extra_hours_price NUMERIC NOT NULL DEFAULT 0,
                        daily_work_hours INTEGER NOT NULL DEFAULT 8,
                        vacation_days INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        allowed_late NUMERIC NOT NULL DEFAULT 0,
                        min_extraTime NUMERIC NOT NULL DEFAULT 0,
                        joined DATE NOT NULL DEFAULT CURRENT_DATE,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        deleted_at DATETIME NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO employees (
                        id,
                        first_name,
                        last_name,
                        fullname,
                        job_title,
                        phone,
                        email,
                        dues,
                        salary_type,
                        monthly_price,
                        day_price,
                        hour_price,
                        extra_hours_price,
                        daily_work_hours,
                        is_active,
                        allowed_late,
                        min_extraTime,
                        joined,
                        created_at,
                        updated_at
                    ) VALUES (
                        1,
                        'Legacy',
                        'Employee',
                        'Legacy Employee',
                        'Operator',
                        '0000000000',
                        'legacy@example.com',
                        0,
                        1,
                        0,
                        0,
                        0,
                        0,
                        8,
                        1,
                        0,
                        0,
                        CURRENT_DATE,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    """
                )
            )

    def tearDown(self):
        self.engine.dispose()

    def test_schema_helper_repairs_legacy_sqlite_table(self):
        session = self.SessionLocal()
        try:
            ensure_employee_auto_attendance_schema(session)
            session.commit()

            columns = {column["name"] for column in inspect(self.engine).get_columns("employees")}
            self.assertIn("auto_attendance_enabled", columns)
            self.assertIn("auto_attendance_effective_from", columns)

            stored_value = session.execute(
                text("SELECT auto_attendance_enabled FROM employees WHERE id = 1")
            ).scalar_one()
            self.assertEqual(stored_value, 0)
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
