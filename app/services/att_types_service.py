from app.models.attendence_types import AttendenceTypes
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_att_types_srv(db:Session):
    return db.scalars(select(AttendenceTypes)).all()