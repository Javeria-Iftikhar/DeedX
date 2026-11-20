"""
services/analytics_service.py — Natural-language → dashboard pipeline.

Delegates to unified NL execution (browse lists, admin-only mutations/actions,
and ORM-safe aggregate analytics).
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.analytics_schemas.dashboard import DashboardResponse
from app.services.unified_nl_service import process_unified_nl_query


def process_analytics_query(
    db: Session,
    user_id: int,
    role: str,
    query: str,
    conversation: Optional[List[Dict[str, Any]]] = None,
) -> DashboardResponse:
    return process_unified_nl_query(db, user_id, role, query, conversation=conversation)
