from sqlalchemy import Column,String,Integer
from app.db.base import Base
from sqlalchemy.orm import relationship

class AttendenceTypes(Base):
    __tablename__ = "attendence_types"
    id = Column(Integer,primary_key=True,index=True)
    attendence_type = Column(String(25), nullable=False)

    attendence_tab = relationship("Attendence",back_populates="attendence_types_tab")

# 0 - present
# 1 - late
# 2 - absent
# 3 - extratime
    