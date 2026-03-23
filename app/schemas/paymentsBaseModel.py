from pydantic import BaseModel
from datetime import date as d
from typing import Optional

class PaymentBaseModel(BaseModel):
    employee_id :int
    date:d
    payment_type:int
    amount:float
    description:str
    start:Optional[d]=None
    end:Optional[d]=None

class UpdatePaymentBaseModel(BaseModel):
    id:int
    employee_id :int
    date:Optional[d]
    payment_type:Optional[int]
    amount:Optional[float]
    description:Optional[str]