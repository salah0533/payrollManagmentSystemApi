from pydantic import BaseModel, field_validator
from datetime import datetime, date as d
from typing import Optional

class PaymentBaseModel(BaseModel):
    employee_id :int
    date:d
    payment_type:int
    amount:float
    description:str
    year_month:Optional[str]=None

class UpdatePaymentBaseModel(BaseModel):
    id:int
    employee_id :int
    date:Optional[d]
    payment_type:Optional[int]
    amount:Optional[float]
    description:Optional[str]

class MonthInput(BaseModel):
    month: str

    @field_validator("month")
    def validate_month(cls, v):
        try:
            datetime.strptime(v, "%Y-%m")
        except ValueError:
            raise ValueError("Invalid format. Use YYYY-MM")
        return v