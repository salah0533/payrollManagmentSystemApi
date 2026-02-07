from sqlalchemy import Column,String,Integer
from app.db.base import Base
from sqlalchemy.orm import relationship

class SalaryType(Base):
    __tablename__ = "salary_type"
    id = Column(Integer,primary_key=True,index=True)
    salary_type = Column(String(25), nullable=False)

    employee_tab = relationship("Employees",back_populates="salary_type_tab")

# 0 - monthly
# 1 - daily
# 2 - hourly
