from app.core.localization import translate
from app.models.salary_type import SalaryType
from sqlalchemy import select


def get_payment_types_srv(db):
    rows = db.scalars(select(SalaryType)).all()
    return [
        {
            "id": row.id,
            "code": (row.code or row.salary_type or "").strip().lower(),
            "label": translate(f"labels.salary_type.{(row.code or row.salary_type or '').strip().lower()}", fallback=row.salary_type),
            "salary_type": row.salary_type,
        }
        for row in rows
    ]
