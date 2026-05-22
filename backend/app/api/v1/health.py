import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["health"])


@router.get("", include_in_schema=False)
def health_root() -> dict:
    """API-namespaced alias for the root ``/health`` liveness probe.

    External monitors (Datadog synthetics, Uptime Robot, etc.) sometimes
    default to the API-prefixed path. Without this alias they hit a 404
    and add noise to the error-rate panel. Body shape matches ``/health``
    so a synthetic switching between the two doesn't see a behavior
    change.
    """
    return {"status": "ok"}


@router.get("/db")
def check_database(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    """Verify database connectivity. Admin-only to avoid exposing detail and
    provide anti-abuse cover for the connection.
    """
    try:
        result = db.execute(text("SELECT 1"))
        result.fetchone()
        return {"status": "ok", "database": "connected"}
    except SQLAlchemyError:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database connection failed"
        ) from None
