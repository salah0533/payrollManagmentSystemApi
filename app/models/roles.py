from sqlalchemy import Column,String,Integer
from app.db.base import Base
from sqlalchemy.orm import relationship

class Roles(Base):
    __tablename__ = "roles"
    id = Column(Integer,primary_key=True,index=True)
    role_name = Column(String(25), nullable=False, nullable=False)

    employee_tab = relationship("Employees",back_populates="roles_tab")


    