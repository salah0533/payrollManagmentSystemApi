from pydantic import BaseModel,model_validator
from datetime import date,time
from typing import Optional


class AttendenceBaseModel(BaseModel):
    employee_id: int
    date: date
    entry_time:time
    exit_time:Optional[time]=None
    attendence_type:Optional[int]=None

    @model_validator(mode="after")
    def check_dates(self):
        if self.exit_time and self.entry_time >= self.exit_time:
            raise ValueError("exit time must be grater then entry time")
        
        return self

class DataRange(BaseModel):
    start:date
    end:date

    @model_validator(mode="after")
    def check_range(self):
        if self.start > self.end:
            raise ValueError("start date must be less than or equal to end date")
        
        return self
        
