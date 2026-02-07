from app.models.vacation_types import VacationTypes
from sqlalchemy import select


def get_payment_types_srv(db):
    return db.scalars(select(VacationTypes)).all()