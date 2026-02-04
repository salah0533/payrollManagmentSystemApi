
from pydantic import BaseModel
from typing import Optional

class NewEmployeeBase(BaseModel):
    id :int
    fullname :str
    job_title : str
    phone : str
    email:Optional[str]=None
    dues : Optional[float]=0
    daly_work_hours : float
    extra_hours_price : float
    hour_price : float 
    day_price : Optional[float]=0
    month_price : Optional[float]=0
    vacation_days : int
    salary_type:int
    is_active:bool
    allowed_late:float
    min_extraTime:float

class UpdateEmployeeBase(BaseModel):
    id :Optional[int]=None
    fullname :Optional[str]=None
    job_title :Optional[str]=None
    phone :Optional[str]=None
    email:Optional[str]=None
    dues :Optional[float]=None
    daly_work_hours :Optional[int]=None
    extra_hours_price :Optional[float]=None
    hour_price :Optional[float]=None
    day_price :Optional[float]=None
    month_price :Optional[float]=None
    vacation_days :Optional[int]=None
    salary_type:Optional[int]=None
    is_active:Optional[bool]=None
    allowed_late:Optional[float]=None
    min_extraTime:Optional[float]=None
