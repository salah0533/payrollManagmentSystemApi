from pydantic import BaseModel
from datetime import date,time
from typing import Optional


class AttendenceBaseModel(BaseModel):
    employee_id: int
    date: date
    entry_time:time
    exit_time:Optional[time]=None