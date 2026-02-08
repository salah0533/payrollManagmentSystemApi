
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class NewEmployeeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fullname :str
    job_title : str
    phone : str
    email:Optional[str]=None
    dues : Optional[float]=0
    daily_work_hours : float = Field(..., alias="daly_work_hours")
    extra_hours_price : float
    hour_price : float 
    day_price : Optional[float]=0
    monthly_price : Optional[float]=Field(0, alias="month_price")
    vacation_days : int
    salary_type:int
    is_active:bool
    allowed_late:float
    min_extraTime:float

class UpdateEmployeeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id :int
    fullname :Optional[str]=None
    job_title :Optional[str]=None
    phone :Optional[str]=None
    email:Optional[str]=None
    dues :Optional[float]=None
    daily_work_hours :Optional[int]=Field(None, alias="daly_work_hours")
    extra_hours_price :Optional[float]=None
    hour_price :Optional[float]=None
    day_price :Optional[float]=None
    monthly_price :Optional[float]=Field(None, alias="month_price")
    vacation_days :Optional[int]=None
    salary_type:Optional[int]=None
    is_active:Optional[bool]=None
    allowed_late:Optional[float]=None
    min_extraTime:Optional[float]=None
