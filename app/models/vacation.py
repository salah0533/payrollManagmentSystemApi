from app.db.base import Base
from sqlalchemy import Column,String,Integer,ForeignKey,Date,Boolean
from sqlalchemy.orm import relationship


class Vacation(Base):
    __tablename__ = "vacation"
    id = Column(Integer,primary_key=True,index=True)
    employee_id = Column(Integer,ForeignKey("employees.id",ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    vacation_type = Column(Integer,ForeignKey("vacation_types.id"), nullable=False)
    vacation_status = Column(Integer,ForeignKey("vacation_status.id"),nullable=False)
    is_paid = Column(Boolean,nullable=False)

    vacation_types_tab = relationship("VacationTypes",back_populates="vacation_tab")
    vacation_status_tab = relationship("VacationStatus",back_populates="vacation_tab")
    employee_tab = relationship("Employees",back_populates="vacation_tab")