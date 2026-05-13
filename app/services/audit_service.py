from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.models.attendance_payroll import AuditLog


def serialize_model(instance, *, fields: Iterable[str] | None = None) -> dict:
    mapper = sa_inspect(instance.__class__)
    allowed = set(fields) if fields else None
    payload: dict = {}
    for column in mapper.columns:
        if allowed is not None and column.key not in allowed:
            continue
        value = getattr(instance, column.key)
        if isinstance(value, Decimal):
            payload[column.key] = str(value)
        elif hasattr(value, "value"):
            payload[column.key] = value.value
        elif hasattr(value, "isoformat"):
            payload[column.key] = value.isoformat()
        else:
            payload[column.key] = value
    return payload


def save_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    old_data_json: dict | None = None,
    new_data_json: dict | None = None,
    user_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_data_json=old_data_json,
        new_data_json=new_data_json,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.flush()
    return log
