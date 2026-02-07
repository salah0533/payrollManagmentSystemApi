from app.models.salary_type import SalaryType
from sqlalchemy import select


def get_payment_types_srv(db):
    return db.scalars(select(SalaryType)).all()