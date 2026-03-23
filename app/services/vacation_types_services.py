from app.models.vacation_types import VacationTypes
from sqlalchemy import select


def get_payment_types_srv(db):
    return db.scalars(select(VacationTypes)).all()


#    {
#       "id": 0,
#       "vacation_type": "yearly_vacation"
#     },
#     {
#       "id": 1,
#       "vacation_type": "sick_leave"
#     },
#     {
#       "id": 2,
#       "vacation_type": "vacation"
#     }