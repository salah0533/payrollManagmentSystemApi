from app.db.base import Base
from sqlalchemy import Column,Time

class Settings(Base):
    entry_time = Column(Time,nullable=False)
    exit_time = Column(Time,nullable=False)
    