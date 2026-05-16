import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services.policy_service import get_or_create_payroll_policy


class PayrollPolicySchemaRepairTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()
        self.db.execute(
            text(
                """
                CREATE TABLE payroll_policy (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    payroll_cycle VARCHAR(20) NOT NULL,
                    minimum_overtime_minutes INTEGER NOT NULL,
                    allowed_late_minutes INTEGER NOT NULL,
                    default_currency VARCHAR(10) NOT NULL,
                    significant_change_threshold NUMERIC(12, 2) NOT NULL,
                    paid_vacation_counts_for_daily BOOLEAN NOT NULL,
                    overtime_enabled BOOLEAN NOT NULL,
                    late_makeup_enabled BOOLEAN NOT NULL,
                    late_deduction_enabled BOOLEAN NOT NULL,
                    auto_recalculate_draft_payroll BOOLEAN NOT NULL,
                    lock_payroll_after_payment BOOLEAN NOT NULL,
                    holidays_json JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        self.db.execute(
            text(
                """
                INSERT INTO payroll_policy (
                    id,
                    name,
                    payroll_cycle,
                    minimum_overtime_minutes,
                    allowed_late_minutes,
                    default_currency,
                    significant_change_threshold,
                    paid_vacation_counts_for_daily,
                    overtime_enabled,
                    late_makeup_enabled,
                    late_deduction_enabled,
                    auto_recalculate_draft_payroll,
                    lock_payroll_after_payment,
                    holidays_json,
                    created_at,
                    updated_at
                ) VALUES (
                    1,
                    'default',
                    'monthly',
                    30,
                    0,
                    'DZD',
                    1.00,
                    1,
                    1,
                    1,
                    0,
                    1,
                    1,
                    '[]',
                    '2026-05-16T00:00:00+00:00',
                    '2026-05-16T00:00:00+00:00'
                )
                """
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_repairs_missing_minimum_auto_pay_minutes_column(self):
        policy = get_or_create_payroll_policy(self.db)

        self.assertEqual(policy.minimum_auto_pay_minutes, 0)

        columns = self.db.execute(text("PRAGMA table_info(payroll_policy)")).fetchall()
        self.assertIn("minimum_auto_pay_minutes", [row[1] for row in columns])


if __name__ == "__main__":
    unittest.main()
