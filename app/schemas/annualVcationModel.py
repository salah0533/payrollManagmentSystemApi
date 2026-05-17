from pydantic import BaseModel, Field



class AnnualVacationModel(BaseModel):
    emp_id: int
    year: int = Field(..., ge=1900, le=3000)
    allowed_days: int = Field(..., gt=0)


class DeleteAnnualVacationModel(BaseModel):
    emp_id: int
    year: int = Field(..., ge=1900, le=3000)
