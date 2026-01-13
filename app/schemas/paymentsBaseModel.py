from pydantic import BaseModel
from datetime import date
from typing import Optional

class PaymentBaseModel(BaseModel):
    employee_id :int
    date:date
    payment_type:int
    amount:float
    description:str

class UpdatePaymentBaseModel(BaseModel):
    id:int
    employee_id :int
    date:Optional[date]
    payment_type:Optional[int]
    amount:Optional[float]
    description:Optional[str]