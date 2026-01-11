from app.db.base import Base
from sqlalchemy import String,Integer,Column,ForeignKey,DECIMAL,Boolean
from sqlalchemy.orm import relationship

class Employees(Base):
    __tablename__ = "employees"

    id = Column(Integer,primary_key=True,index=True)
    name = Column(String(50) , nullable=False)
    role_id = Column(Integer,ForeignKey("roles.id"),nullable=False)
    job_title = Column(String, nullable=False)
    phone = Column(String(14),nullable=False)
    dues = Column(DECIMAL, nullable=False)
    daly_work_hours = Column(Integer, nullable=False)
    extra_hours_price = Column(DECIMAL, nullable=False)
    hour_price = Column(DECIMAL, nullable=False)
    day_price = Column(DECIMAL, nullable=False)
    month_price = Column(DECIMAL, nullable=False)
    vacation_days = Column(Integer, nullable=False) #allowed yearly vacation days
    auto_attendence = Column(Boolean,nullable=False)
    is_active = Column(Boolean,nullable=False)
    
    roles_tab = relationship("Roles",back_populates="employee_tab")

    attendence_tab = relationship("Attendence",back_populates="attendence",
                             cascade="all, delete-orphan")
    
    payment_tab = relationship("Payments",back_populates="employee_tab",
                             cascade="all, delete-orphan")
    
    vacation_tab = relationship("Vacation",back_populates="employee_tab",
                             cascade="all, delete-orphan")

    
    def to_dict(self):
        return {
            "id":self.id,
            "name":self.name,
            "job_title":self.job_title,
            "phone":self.phone,
            "dues":self.dues,
            "role":self.roles_tab.role_name if self.roles_tab else None,
            "daly_work_hours":self.daly_work_hours,
            "extra_hours_price":self.extra_hours_price,
            "hour_price":self.hour_price,
            "day_price":self.day_price,
            "month_price":self.month_price,
            "vacation_days":self.vacation_days
        }