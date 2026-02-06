from pydantic import BaseModel
from datetime import date
from typing import Optional

class VacationBaseModel(BaseModel):
    employee_id:int
    start_date:date
    end_date:date
    vacation_type:int
    vacation_status:int
    is_paid:bool

class UpdateVacationBaseModel(BaseModel):
    id:int
    employee_id:Optional[int]=None
    start_date:Optional[date]=None
    end_date:Optional[date]=None
    vacation_type:Optional[int]=None
    vacation_status:Optional[int]=None
    is_paid:Optional[bool]=None