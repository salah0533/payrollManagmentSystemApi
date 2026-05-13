from pydantic import BaseModel,model_validator



class AnnualVacationModel(BaseModel):
    emp_id: int
    year: int
    allowed_days:int


class DeleteAnnualVacationModel(BaseModel):
    emp_id: int
    year: int