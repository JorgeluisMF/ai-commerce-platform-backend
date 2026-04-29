from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps.auth import require_role
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.admin import AdminDashboardResponse
from app.services.admin_service import get_dashboard_metrics

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=AdminDashboardResponse, summary="Admin dashboard metrics")
def admin_dashboard(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
) -> AdminDashboardResponse:
    return get_dashboard_metrics(db)
