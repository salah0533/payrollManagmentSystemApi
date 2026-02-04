from app.db.base import Base
from sqlalchemy import String,Integer,Column,ForeignKey,DECIMAL,Boolean
from sqlalchemy.orm import relationship

class Employees(Base):
    __tablename__ = "employees"

    id = Column(Integer,primary_key=True,index=True)
    fullname = Column(String(50) , nullable=False)
    job_title = Column(String, nullable=False)
    phone = Column(String(14),nullable=False)
    email = Column(String(50))
    dues = Column(DECIMAL, nullable=False)
    salary_type = Column(Integer,ForeignKey("salary_type.id"),nullable=False)
    monthly_price = Column(DECIMAL, nullable=False)
    day_price = Column(DECIMAL, nullable=False)
    hour_price = Column(DECIMAL, nullable=False)
    extra_hours_price = Column(DECIMAL, nullable=False)
    daily_work_hours = Column(Integer, nullable=False)
    vacation_days = Column(Integer, nullable=False) #allowed yearly vacation days
    is_active = Column(Boolean,nullable=False)
    allowed_late = Column(DECIMAL,nullable=False)
    min_extraTime = Column(DECIMAL,nullable=False) # not paid
    

    attendence_tab = relationship("Attendence",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    
    payment_tab = relationship("Payments",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    
    vacation_tab = relationship("Vacation",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    salary_type_tab = relationship("SalaryType",back_populates="employee_tab")

    
    def to_dict(self):
        return {
            "id":self.id,
            "fullname":self.fullname,
            "job_title":self.job_title,
            "phone":self.phone,
            "email":self.email,
            "dues":self.dues,
            "salary_type":self.salary_type,
            "daly_work_hours":self.daly_work_hours,
            "extra_hours_price":self.extra_hours_price,
            "hour_price":self.hour_price,
            "day_price":self.day_price,
            "monthly_price":self.month_price,
            "vacation_days":self.vacation_days,
            "is_active":self.is_active,
            "allowed_late":self.allowed_late,
            "min_extratime":self.min_extraTime
            
        }