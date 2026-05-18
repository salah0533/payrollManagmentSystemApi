from app.core.localization import translate
from app.models.vacation_types import VacationTypes
from sqlalchemy import select


def get_payment_types_srv(db):
    rows = db.scalars(select(VacationTypes)).all()
    result = []
    for row in rows:
        code = (row.code or row.vacation_type or "").strip().lower()
        result.append(
            {
                "id": row.id,
                "code": code,
                "label": translate(f"labels.vacation_type.{code}", fallback=row.vacation_type),
                "vacation_type": row.vacation_type,
            }
        )
    return result


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
