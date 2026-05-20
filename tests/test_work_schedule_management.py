import unittest
from datetime import time

import app.models  # noqa: F401
from app.db.base import Base
from app.exceptions.base_exception import BadRequestException
from app.models.attendance_payroll import WorkSchedule
from app.services.policy_service import (
    create_work_schedule,
    get_default_work_schedule,
    list_work_schedules,
    update_work_schedule,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


class WorkScheduleManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_list_work_schedules_creates_default_when_missing(self):
        schedules = list_work_schedules(self.db)

        self.assertEqual(len(schedules), 1)
        self.assertTrue(schedules[0].is_default)
        self.assertEqual(schedules[0].name, "Default Schedule")

    def test_creating_default_schedule_unsets_previous_default(self):
        original_default = get_default_work_schedule(self.db)

        created = create_work_schedule(
            self.db,
            name="Night Shift",
            start_time=time(10, 0),
            end_time=time(19, 0),
            break_start_time=time(14, 0),
            break_end_time=time(15, 0),
            break_minutes=60,
            weekly_off_days=["friday", "saturday"],
            timezone="UTC",
            is_default=True,
        )

        self.assertTrue(created.is_default)
        refreshed_original = self.db.get(WorkSchedule, original_default.id)
        self.assertFalse(refreshed_original.is_default)
        self.assertEqual(get_default_work_schedule(self.db).id, created.id)

    def test_updating_non_default_schedule_can_promote_it_to_default(self):
        get_default_work_schedule(self.db)
        created = create_work_schedule(
            self.db,
            name="Late Shift",
            start_time=time(11, 0),
            end_time=time(20, 0),
            break_start_time=time(15, 0),
            break_end_time=time(16, 0),
            break_minutes=60,
            weekly_off_days=["friday", "saturday"],
            timezone="UTC",
            is_default=False,
        )

        updated = update_work_schedule(
            created.id,
            self.db,
            name=created.name,
            start_time=created.start_time,
            end_time=created.end_time,
            break_start_time=created.break_start_time,
            break_end_time=created.break_end_time,
            break_minutes=created.break_minutes,
            weekly_off_days=created.weekly_off_days,
            timezone=created.timezone,
            is_default=True,
        )

        self.assertTrue(updated.is_default)
        default_ids = self.db.scalars(select(WorkSchedule.id).where(WorkSchedule.is_default.is_(True))).all()
        self.assertEqual(default_ids, [created.id])

    def test_cannot_unset_only_default_schedule(self):
        default_schedule = get_default_work_schedule(self.db)

        with self.assertRaises(BadRequestException):
            update_work_schedule(
                default_schedule.id,
                self.db,
                name=default_schedule.name,
                start_time=default_schedule.start_time,
                end_time=default_schedule.end_time,
                break_start_time=default_schedule.break_start_time,
                break_end_time=default_schedule.break_end_time,
                break_minutes=default_schedule.break_minutes,
                weekly_off_days=default_schedule.weekly_off_days,
                timezone=default_schedule.timezone,
                is_default=False,
            )


if __name__ == "__main__":
    unittest.main()
