from app.db.base import Base
from sqlalchemy import Column,String,Integer,ForeignKey,TIMESTAMP,DECIMAL
from sqlalchemy.orm import relationship

class Payments(Base):
    __tablename__ = "payments"
    id = Column(Integer,primary_key=True,index=True)
    employee_id = Column(Integer,ForeignKey("employees.id",ondelete="CASCADE"), nullable=False)
    date = Column(TIMESTAMP, nullable=False)
    amount = Column(DECIMAL, nullable=False)
    payment_type = Column(Integer,ForeignKey("payment_types.id"), nullable=False)
    description = Column(String, nullable=False)

    payment_types_tab = relationship("PaymentTypes",back_populates="payment_tab")
    employee_tab = relationship("Employees",back_populates="payment_tab")