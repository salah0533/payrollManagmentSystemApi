from app.db.base import Base
from app.core.security import utc_now
from sqlalchemy import String,Integer,Column,ForeignKey,DECIMAL,Boolean,Date,DateTime
from sqlalchemy.orm import relationship

class Employees(Base):
    __tablename__ = "employees"

    id = Column(Integer,primary_key=True,index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    fullname = Column(String(100) , nullable=False)
    job_title = Column(String, nullable=False)
    phone = Column(String(14),nullable=False)
    email = Column(String(255))
    department_id = Column(Integer, nullable=True, index=True)
    position_id = Column(Integer, nullable=True, index=True)
    position = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    hire_date = Column(Date, nullable=True)
    dues = Column(DECIMAL, nullable=False)
    salary_type = Column(Integer,ForeignKey("salary_type.id"),nullable=False)
    monthly_price = Column(DECIMAL, nullable=False)
    day_price = Column(DECIMAL, nullable=False)
    hour_price = Column(DECIMAL, nullable=False)
    extra_hours_price = Column(DECIMAL, nullable=False)
    daily_work_hours = Column(Integer, nullable=False)
    vacation_days = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean,nullable=False)
    allowed_late = Column(DECIMAL,nullable=False)
    min_extraTime = Column(DECIMAL,nullable=False) # not paid
    joined = Column(Date,nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    

    attendence_tab = relationship("Attendence",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    
    annualvacation_tab = relationship("AnnualVacations",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    
    payment_tab = relationship("Payments",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    
    vacation_tab = relationship("Vacation",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    salary_type_tab = relationship("SalaryType",back_populates="employee_tab")
    user_account = relationship("User", back_populates="employee", uselist=False)

    
    def to_dict(self):
        return {
            "id":self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "fullname":self.fullname,
            "department_id": self.department_id,
            "position_id": self.position_id,
            "position": self.position,
            "status": self.status,
            "hire_date": self.hire_date,
            "job_title":self.job_title,
            "phone":self.phone,
            "email":self.email,
            "dues":self.dues,
            "salary_type":self.salary_type,
            "daily_work_hours":self.daily_work_hours,
            "extra_hours_price":self.extra_hours_price,
            "vacation_days": self.vacation_days,
            "hour_price":self.hour_price,
            "day_price":self.day_price,
            "monthly_price":self.monthly_price,
            "is_active":self.is_active,
            "allowed_late":self.allowed_late,
            "min_extraTime":self.min_extraTime,
            "joined": self.joined,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
            
        }
