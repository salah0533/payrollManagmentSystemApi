from sqlalchemy import Column,String,Integer
from app.db.base import Base
from sqlalchemy.orm import relationship

class VacationStatus(Base):
    __tablename__ = "vacation_status"
    id = Column(Integer,primary_key=True,index=True)
    vacation_status = Column(String(25), nullable=False)

    vacation_tab = relationship("Vacation",back_populates="vacation_status_tab")

    
    # 0 - pending
    # 1 - aproved
    # 2 - canceled
    # 3 - rejected