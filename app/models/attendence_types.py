from sqlalchemy import Column,String,Integer
from app.db.base import Base
from sqlalchemy.orm import relationship

class AttendenceTypes(Base):
    __tablename__ = "attendence_types"
    id = Column(Integer,primary_key=True,index=True)
    code = Column(String(50), nullable=True, unique=True)
    attendence_type = Column(String(25), nullable=False)

    attendence_tab = relationship("Attendence",back_populates="attendence_types_tab")


    # {
    #   "attendence_type": "present",
    #   "id": 0
    # },
    # {
    #   "attendence_type": "late",
    #   "id": 1
    # },
    # {
    #   "attendence_type": "vacation",
    #   "id": 2
    # },
    # {
    #   "attendence_type": "absent",
    #   "id": 3
    # },
    # {
    #   "attendence_type": "extra_work",
    #   "id": 4
    # }
# 0 - present
# 1 - late
# 2 - absent
# 3 - extratime
# 4 - paid vacation
# 5 - not paid vacation
# 6 - sickleave
