from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.exceptions.base_exception import ConflictException
from app.models.employee_reference import Department, Position
from app.schemas.user import DepartmentRead, EmployeeReferenceCreateRequest, PositionRead


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split())


def _ensure_unique_name(model, name: str, db: Session) -> None:
    existing = db.scalar(select(model.id).where(func.lower(model.name) == name.lower()))
    if existing:
        raise ConflictException(
            f"{model.__name__} already exists",
            code=f"{model.__tablename__}_already_exists",
            message_key="errors.conflict",
        )


def list_departments(db: Session) -> list[DepartmentRead]:
    rows = db.scalars(select(Department).where(Department.is_active.is_(True)).order_by(Department.name.asc())).all()
    return [DepartmentRead(id=row.id, name=row.name, is_active=row.is_active) for row in rows]


def create_department(payload: EmployeeReferenceCreateRequest, db: Session) -> DepartmentRead:
    name = _normalize_name(payload.name)
    _ensure_unique_name(Department, name, db)
    department = Department(name=name, is_active=True)
    db.add(department)
    db.commit()
    db.refresh(department)
    return DepartmentRead(id=department.id, name=department.name, is_active=department.is_active)


def list_positions(db: Session) -> list[PositionRead]:
    rows = db.scalars(select(Position).where(Position.is_active.is_(True)).order_by(Position.name.asc())).all()
    return [PositionRead(id=row.id, name=row.name, is_active=row.is_active) for row in rows]


def create_position(payload: EmployeeReferenceCreateRequest, db: Session) -> PositionRead:
    name = _normalize_name(payload.name)
    _ensure_unique_name(Position, name, db)
    position = Position(name=name, is_active=True)
    db.add(position)
    db.commit()
    db.refresh(position)
    return PositionRead(id=position.id, name=position.name, is_active=position.is_active)
