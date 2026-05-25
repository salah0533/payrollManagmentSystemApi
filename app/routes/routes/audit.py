from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.responses import api_success
from app.db.session import get_db
from app.dependencies.auth import require_permissions
from app.models.auth import User
from app.services.audit_service import get_audit_log_page


router = APIRouter()


@router.get("/")
def list_audit_logs(
    page: int = 1,
    page_size: int = 100,
    action: list[str] | None = None,
    entity_type: list[str] | None = None,
    actor_user_id: int | None = None,
    actor_role: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permissions("audit.read")),
):
    rows = get_audit_log_page(
        db,
        page=page,
        page_size=page_size,
        actions=action,
        entity_types=entity_type,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        search=search,
    )
    return api_success(rows)
