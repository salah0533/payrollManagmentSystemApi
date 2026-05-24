from sqlalchemy import Column,String,Integer
from app.db.base import Base

class PaymentTypes(Base):
    __tablename__ = "payment_types"
    id = Column(Integer,primary_key=True,index=True)
    code = Column(String(50), nullable=True, unique=True)
    payment_type = Column(String(25), nullable=False)


# 0 - pyment
# 1 - reduction
# 2 - bonus
# 3 - attendence
