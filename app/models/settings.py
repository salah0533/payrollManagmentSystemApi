from app.db.base import Base
from sqlalchemy import Column,Time,Integer

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer,primary_key=True,index=True)
    entry_time = Column(Time)
    exit_time = Column(Time)

    