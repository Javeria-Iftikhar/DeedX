"""
services/dashboard_service.py — Retrieves analytics query history from AuditLog.

The analytics router delegates history lookups here; this keeps DB access
out of the router layer.
"""

from typing import List
from sqlalchemy.orm import Session

from app import models
from app.analytics_schemas.dashboard import AnalyticsQueryHistoryItem, AnalyticsHistoryResponse

_ANALYTICS_ENTITY = "AnalyticsQuery"


def get_query_history(
    db: Session,
    user_id: int,
    role: str,
    page: int = 1,
    page_size: int = 20,
) -> AnalyticsHistoryResponse:
    """
    Return paginated analytics query audit history.

    - Admin: sees all analytics query logs.
    - Others: see only their own.
    """
    page_size = min(max(page_size, 1), 100)
    page      = max(page, 1)
    offset    = (page - 1) * page_size

    base_q = db.query(models.AuditLog).filter(
        models.AuditLog.entity_affected == _ANALYTICS_ENTITY
    )

    if role != "admin":
        base_q = base_q.filter(models.AuditLog.user_id == user_id)

    total = base_q.count()
    rows  = (
        base_q.order_by(models.AuditLog.log_timestamp.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = []
    for r in rows:
        # action format: "ANALYTICS:<module>|<query>|success=True"
        parts  = r.action.split("|")
        module = parts[0].replace("ANALYTICS:", "").strip() if parts else "unknown"
        q_text = parts[1].strip() if len(parts) > 1 else ""
        success = "success=True" in r.action

        items.append(AnalyticsQueryHistoryItem(
            log_id=r.log_id,
            user_id=r.user_id,
            query=q_text,
            module=module,
            success=success,
            timestamp=str(r.log_timestamp),
        ))

    return AnalyticsHistoryResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
