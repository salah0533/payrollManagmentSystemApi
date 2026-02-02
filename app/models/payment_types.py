from sqlalchemy import Column,String,Integer
from app.db.base import Base
from sqlalchemy.orm import relationship

class PaymentTypes(Base):
    __tablename__ = "payment_types"
    id = Column(Integer,primary_key=True,index=True)
    payment_type = Column(String(25), nullable=False)
    
    payment_tab = relationship("Payments",back_populates="payment_types_tab")


# 0 - pyment
# 1 - reduction
# 2 - bonus
# 3 - attendence
