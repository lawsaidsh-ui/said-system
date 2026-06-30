from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.services.audit import recent_audit_logs
from app.services.auth import ensure_role, get_current_user
from app.templating import templates

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def audit_index(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ensure_role(user, {"admin"})
    return templates.TemplateResponse(
        "audit/index.html",
        {
            "request": request,
            "user": user,
            "audit_logs": recent_audit_logs(db, limit=100),
        },
    )
