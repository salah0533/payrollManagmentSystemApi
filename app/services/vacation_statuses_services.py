from app.core.localization import translate
from app.models.vacation_status import VacationStatus
from sqlalchemy import select


def get_payment_types_srv(db):
    rows = db.scalars(select(VacationStatus)).all()
    result = []
    for row in rows:
        code = (row.code or row.vacation_status or "").strip().lower()
        result.append(
            {
                "id": row.id,
                "code": code,
                "label": translate(f"labels.vacation_status.{code}", fallback=row.vacation_status),
                "vacation_status": row.vacation_status,
            }
        )
    return result


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
