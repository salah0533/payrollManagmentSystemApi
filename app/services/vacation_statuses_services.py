from app.models.vacation_status import VacationStatus
from sqlalchemy import select


def get_payment_types_srv(db):
    return db.scalars(select(VacationStatus)).all()


    # {
    #   "id": 0,
    #   "vacation_status": "pending"
    # },
    # {
    #   "id": 1,
    #   "vacation_status": "proved"
    # },
    # {
    #   "id": 2,
    #   "vacation_status": "rejected"
    # },
    # {
    #   "id": 3,
    #   "vacation_status": "canceled"
    # }