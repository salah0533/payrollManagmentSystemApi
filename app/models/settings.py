from app.db.base import Base
from sqlalchemy import Column,Time,DECIMAL

class Settings(Base):
    entry_time = Column(Time)
    exit_time = Column(Time)

    