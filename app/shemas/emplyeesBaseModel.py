
from pydantic import BaseModel
from typing import Optional

class NewEmployeeBase(BaseModel):
    id :int
    name :str
    role_id : int
    job_title : str
    phone : str
    dues : float
    daly_work_hours : float
    extra_hours_price : float
    hour_price : float 
    day_price : float
    month_price : float
    vacation_days : int

class UpdateEmployeeBase(BaseModel):
    id :Optional[int]=None
    name :Optional[str]=None
    role_id :Optional[int]=None
    job_title :Optional[str]=None
    phone :Optional[str]=None
    dues :Optional[float]=None
    daly_work_hours :Optional[int]=None
    extra_hours_price :Optional[float]=None
    hour_price :Optional[float]=None
    day_price :Optional[float]=None
    month_price :Optional[float]=None
    vacation_days :Optional[int]=None

