from app.core.localization import translate
from app.models.vacation_types import VacationTypes
from sqlalchemy import select
from sqlalchemy.orm import Session


HOLIDAY_VACATION_TYPE_CODE = "holiday"
DEFAULT_VACATION_TYPES = (
    {"id": 0, "code": "paid", "vacation_type": "paid"},
    {"id": 1, "code": "unpaid", "vacation_type": "unpaid"},
    {"id": 2, "code": "sick", "vacation_type": "sick"},
    {"id": 3, "code": "emergency", "vacation_type": "emergency"},
    {"id": 4, "code": HOLIDAY_VACATION_TYPE_CODE, "vacation_type": HOLIDAY_VACATION_TYPE_CODE},
)


def ensure_default_vacation_types(db: Session) -> None:
    existing = {
        (str(row.code or "").strip().lower(), str(row.vacation_type or "").strip().lower()): row
        for row in db.scalars(select(VacationTypes)).all()
    }
    for row in DEFAULT_VACATION_TYPES:
        key = (row["code"], row["vacation_type"])
        if key in existing:
            continue
        db.add(VacationTypes(id=row["id"], code=row["code"], vacation_type=row["vacation_type"]))
    db.flush()


def get_vacation_type_ids_by_codes(db: Session, *codes: str) -> set[int]:
    ensure_default_vacation_types(db)
    normalized_codes = {code.strip().lower() for code in codes if code and code.strip()}
    if not normalized_codes:
        return set()
    rows = db.execute(select(VacationTypes.id, VacationTypes.code, VacationTypes.vacation_type)).all()
    result: set[int] = set()
    for type_id, code, label in rows:
        normalized_code = str(code or "").strip().lower()
        normalized_label = str(label or "").strip().lower()
        if normalized_code in normalized_codes or normalized_label in normalized_codes:
            result.add(int(type_id))
    return result


def get_payment_types_srv(db):
    ensure_default_vacation_types(db)
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
