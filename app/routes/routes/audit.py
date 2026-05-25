from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_permissions
from app.models.auth import User
from app.services.audit_service import list_audit_logs as list_audit_logs_service


router = APIRouter()


@router.get("/")
def list_audit_logs(
    limit: int = 100,
    action: list[str] | None = Query(default=None),
    entity_type: list[str] | None = Query(default=None),
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("audit.read")),
):
    rows = list_audit_logs_service(
        db,
        limit=limit,
        actions=action,
        entity_types=entity_type,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
    )
    return api_success(rows)
