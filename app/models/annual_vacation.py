from sqlalchemy import String,Integer,TIMESTAMP,Column,ForeignKey,Time,Date,DECIMAL
from sqlalchemy.orm import relationship
from app.db.base import Base

class AnnualVacations(Base):
    __tablename__ = "annual_vacations"
    year = Column(Integer,primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True)

    allowed_days = Column(Integer, nullable=False, default=0)
    
    employee_tab = relationship("Employees",back_populates="annualvacation_tab")
