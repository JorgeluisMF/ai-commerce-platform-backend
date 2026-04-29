"""Append-only audit trail. Failures never propagate to callers."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from starlette.requests import Request

from app.db.session import SessionLocal
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


def client_ip_from_request(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    if request.client:
        return request.client.host
    return None


def user_agent_from_request(request: Request) -> str | None:
    ua = request.headers.get("user-agent")
    return ua[:2000] if ua else None

def persist_audit_record(
    *,
    action: str,
    resource_type: str,
    resource_id: str = "",
    user_id: uuid.UUID | None = None,
    audit_metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Insert one row in a separate DB session (transactionally independent)."""
    db = SessionLocal()
    try:
        row = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id or "",
            audit_metadata=audit_metadata,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(row)
        db.commit()
    except Exception:
        logger.warning(
            "audit_log_persist_failed",
            exc_info=True,
            extra={"action": action, "resource_type": resource_type},
        )
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
