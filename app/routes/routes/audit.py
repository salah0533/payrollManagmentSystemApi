from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import require_permissions
from app.models.attendance_payroll import AuditLog
from app.models.auth import User
from app.schemas.attendance_payroll import AuditLogRead


router = APIRouter()


@router.get("/")
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("audit.read")),
):
    rows = db.scalars(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(max(1, min(limit, 500)))
    ).all()
    return {"message": "", "data": [AuditLogRead.model_validate(row) for row in rows], "status": True}
