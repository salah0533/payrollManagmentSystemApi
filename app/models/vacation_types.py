from sqlalchemy import Column,String,Integer
from app.db.base import Base
from sqlalchemy.orm import relationship

class VacationTypes(Base):
    __tablename__ = "vacation_types"
    id = Column(Integer,primary_key=True,index=True)
    vacation_type = Column(String(25), nullable=False)

    vacation_tab = relationship("Vacation",back_populates="vacation_types_tab")

    
    