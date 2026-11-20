"""
audit.py — Centralized, generic audit logging utility.

Usage in any router:
    from app.audit import write_audit_log
    write_audit_log(db, user_id=current_user.user_id, action="Created currency USD", entity="Currency")

Rules:
  • Append-only: records are never updated or deleted by this module.
  • Completely generic: no assumptions about which actions exist.
  • Thread-safe log_id: uses max(log_id)+1 within a DB transaction.
"""

from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


def write_audit_log(
    db: Session,
    user_id: int,
    action: str,
    entity: str,
) -> models.AuditLog:
    """
    Append a single audit log record.

    Args:
        db:       Active SQLAlchemy session.
        user_id:  The authenticated user who performed the action.
        action:   Free-text description of the action performed.
        entity:   Name of the entity/table affected (e.g. "Currency", "Loan").

    Returns:
        The newly created AuditLog ORM instance.
    """
    max_id: int = (
        db.query(func.max(models.AuditLog.log_id))
        .filter(models.AuditLog.user_id == user_id)
        .scalar() or 0
    )
    log = models.AuditLog(
        user_id=user_id,
        log_id=max_id + 1,
        action=action,
        log_timestamp=datetime.now(timezone.utc),
        entity_affected=entity,
    )
    db.add(log)
    db.commit()
    return log
