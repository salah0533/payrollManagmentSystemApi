from sqlalchemy import String,Integer,TIMESTAMP,Column,ForeignKey,Time,Date,DECIMAL
from sqlalchemy.orm import relationship
from app.db.base import Base

class Attendence(Base):
    __tablename__ = "attendence"
    id = Column(Integer,primary_key=True,index=True)
    employee_id = Column(Integer,ForeignKey("employees.id",ondelete="CASCADE"), nullable=False)
    entry_time = Column(Time, nullable=False)
    exit_time = Column(Time, nullable=True)
    date = Column(Date, nullable=False)
    attendence_type = Column(Integer,ForeignKey("attendence_types.id"), nullable=False)
    att_hours = Column(DECIMAL,nullable=False)
    
    attendence_types_tab = relationship("AttendenceTypes",back_populates="attendence_tab")
    employee_tab = relationship("Employees",back_populates="attendence_tab")

    #attendence types
    #0 work
    #1 auto attendence
    #2 vacation