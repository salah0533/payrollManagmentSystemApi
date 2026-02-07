from app.models.vacation_status import VacationStatus
from sqlalchemy import select


def get_payment_types_srv(db):
    return db.scalars(select(VacationStatus)).all()