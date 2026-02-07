from app.models.payment_types import PaymentTypes
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_payment_types_srv(db:Session):
    return db.scalars(select(PaymentTypes)).all()