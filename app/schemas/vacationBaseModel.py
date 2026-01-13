from pydantic import BaseModel
from datetime import date
from typing import Optional

class VacationBaseModel(BaseModel):
    employee_id:int
    start_date:date
    end_date:date
    vacation_type:int


class UpdateVacationBaseModel(BaseModel):
    id:int
    employee_id:int
    start_date:date
    end_date:date
    vacation_type:int
